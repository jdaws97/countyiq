"""Planning subdivision records from ArcGIS REST API -> staging.planning_subdivisions.

Records: ~26,000 point features
Schedule: Weekly via radar job

Memory-optimized: streams ArcGIS pages directly into DB temp table
instead of materializing all 26K features in Python memory.
"""

import json

from psycopg2.extras import execute_batch
from dagster import (
    asset,
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
)

from countyiq.lib.arcgis_client import iterate_feature_pages
from countyiq.lib.checks import make_row_count_check
from countyiq.lib.county_config import county_open_data_source_key, get_county_config
from countyiq.lib.parsers.planning_subdivisions import (
    parse_planning_subdivision_features,
)
from countyiq.lib.source_rights import authorize_source, require_source_use
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource

KEY_COLUMNS = ["sequ_num"]

VALUE_COLUMNS = [
    "mcd",
    "date_rcvd",
    "plan_title",
    "pt_prelim",
    "pt_final",
    "pt_land_dev",
    "pt_subdiv",
    "pt_bldg_add",
    "cap",
    "com",
    "st_length",
    "water",
    "sewer",
    "ag_use",
    "com_use",
    "ind_use",
    "mf_use",
    "mhp_use",
    "sr_use",
    "sf_use",
    "other_use",
    "total_acres",
    "exist_lots",
    "prop_lots",
    "bldg_lots",
    "dev_lots",
    "exist_du",
    "prop_du",
    "prop_bldg_add_sqft",
    "prop_new_bldg_sqft",
    "watershed",
    "consistent",
    "notes",
    "engineer",
    "source_url",
]

ALL_COLUMNS = KEY_COLUMNS + VALUE_COLUMNS


@asset(
    group_name="radar",
    description=f"{get_county_config().name} planning subdivisions from ArcGIS REST API -> staging.planning_subdivisions",
    kinds={"postgres", "arcgis"},
)
def planning_subdivisions_arcgis(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    """Stream planning subdivision pages from ArcGIS directly into DB. Memory-efficient."""
    county = get_county_config()
    authorization = authorize_source(
        database,
        source_key=county_open_data_source_key(),
        acquisition_method="arcgis_rest",
        asset_key="planning_subdivisions_arcgis",
        dagster_run_id=context.run_id,
    )
    require_source_use(authorization, "derived_product")
    require_source_use(authorization, "raw_retention")
    context.log.info(
        f"Querying ArcGIS planning subdivisions for {county.name}: {county.arcgis_planning_subdivisions_url}"
    )

    cur = database.cursor()
    conn = cur.connection
    was_autocommit = conn.autocommit
    if was_autocommit:
        conn.autocommit = False

    try:
        cur.execute("DROP TABLE IF EXISTS _tmp_planning_subdivisions")
        cur.execute(
            "CREATE TEMP TABLE _tmp_planning_subdivisions (LIKE staging.planning_subdivisions INCLUDING DEFAULTS)"
        )

        # Stream pages into temp table with geometry
        total_staged = 0
        raw_feature_count = 0
        all_raw_features = []

        insert_sql = f"""
            INSERT INTO _tmp_planning_subdivisions ({", ".join(ALL_COLUMNS)}, geom)
            VALUES ({", ".join(["%s"] * len(ALL_COLUMNS))},
                    CASE WHEN %s IS NOT NULL
                         THEN ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)
                         ELSE NULL END)
        """

        for page_features in iterate_feature_pages(
            url=county.arcgis_planning_subdivisions_url,
            where="1=1",
            out_fields="*",
            out_sr=4326,
            batch_size=2000,
        ):
            raw_feature_count += len(page_features)
            all_raw_features.extend(page_features)

            records = parse_planning_subdivision_features(page_features)

            batch = []
            for rec in records:
                rec["source_url"] = county.arcgis_planning_subdivisions_url
                row = [rec.get(c) for c in ALL_COLUMNS]

                # Point geometry: {"x": lon, "y": lat} -> GeoJSON Point
                geom_json = None
                feat_match = _find_feature_by_sequ_num(page_features, rec["sequ_num"])
                if feat_match:
                    geom = feat_match.get("geometry")
                    if geom and geom.get("x") is not None and geom.get("y") is not None:
                        geom_json = json.dumps(
                            {"type": "Point", "coordinates": [geom["x"], geom["y"]]}
                        )

                row.extend([geom_json, geom_json])
                batch.append(row)

            execute_batch(cur, insert_sql, batch, page_size=500)
            total_staged += len(batch)
            context.log.info(
                f"  Staged {total_staged} records ({raw_feature_count} raw features)"
            )

        context.log.info(f"Total staged: {total_staged}")

        # Archive raw features to S3
        s3.archive(f"{county.s3_prefix}/arcgis/planning_subdivisions", all_raw_features)

        # Truncation guard
        if total_staged < county.arcgis_planning_subdivisions_min_records:
            raise RuntimeError(
                f"Only {total_staged} planning subdivision records "
                f"(expected >= {county.arcgis_planning_subdivisions_min_records}). "
                f"Possible truncated response - aborting."
            )

        if total_staged == 0:
            cur.execute("DROP TABLE IF EXISTS _tmp_planning_subdivisions")
            conn.commit()
            return MaterializeResult(metadata={"record_count": MetadataValue.int(0)})

        # Index temp table for fast SCD2 expire query
        cur.execute("CREATE INDEX ON _tmp_planning_subdivisions (sequ_num)")
        context.log.info("Temp table indexed")

        # SCD2 expire + insert
        key_join = "c.sequ_num = t.sequ_num"
        value_diff = " OR ".join(
            f"c.{v}::text IS DISTINCT FROM t.{v}::text" for v in VALUE_COLUMNS
        )

        # Expire changed/deleted
        cur.execute(f"""
            UPDATE staging.planning_subdivisions c SET valid_to = NOW()
            WHERE c.valid_to IS NULL
            AND (
                EXISTS (SELECT 1 FROM _tmp_planning_subdivisions t WHERE {key_join} AND ({value_diff}))
                OR NOT EXISTS (SELECT 1 FROM _tmp_planning_subdivisions t WHERE {key_join})
            )
        """)
        expired = cur.rowcount
        context.log.info(f"Expired {expired} records")

        # Insert new/changed
        col_list = ", ".join(ALL_COLUMNS)
        cur.execute(f"""
            INSERT INTO staging.planning_subdivisions ({col_list}, geom, valid_from)
            SELECT {", ".join(f"t.{c}" for c in ALL_COLUMNS)}, t.geom, NOW()
            FROM _tmp_planning_subdivisions t
            WHERE NOT EXISTS (
                SELECT 1 FROM staging.planning_subdivisions c WHERE c.valid_to IS NULL AND {key_join}
            )
        """)
        inserted = cur.rowcount
        context.log.info(f"Inserted {inserted} records")

        cur.execute("DROP TABLE IF EXISTS _tmp_planning_subdivisions")
        conn.commit()

    except Exception:
        conn.rollback()
        raise
    finally:
        if was_autocommit:
            conn.autocommit = True
        cur.close()

    return MaterializeResult(
        metadata={
            "record_count": MetadataValue.int(total_staged),
            "raw_feature_count": MetadataValue.int(raw_feature_count),
            "inserted": MetadataValue.int(inserted),
            "expired": MetadataValue.int(expired),
            "unchanged": MetadataValue.int(total_staged - inserted),
        }
    )


def _find_feature_by_sequ_num(features: list[dict], sequ_num) -> dict | None:
    """Find the raw feature matching a parsed sequ_num for geometry extraction."""
    for feat in features:
        if feat.get("attributes", {}).get("SEQU_NUM") == sequ_num:
            return feat
    return None


planning_subdivisions_record_count = make_row_count_check(
    planning_subdivisions_arcgis,
    table="planning_subdivisions",
    threshold_fn=lambda: get_county_config().arcgis_planning_subdivisions_min_records,
    name="planning_subdivisions_record_count",
    description="Verify staging.planning_subdivisions has records above threshold.",
)
