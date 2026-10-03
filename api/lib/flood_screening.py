"""Bounded parcel flood screening; missing mapping never establishes clearance."""

from datetime import UTC, datetime, timedelta

from api.lib.evidence import NFHL_FLOOD_HAZARD_LAYER, evidence_item, with_arcgis_layer


def parcel_flood_screening(cur, pidn: str) -> dict:
    cur.execute(
        """
        WITH parcel AS (
            SELECT ST_CollectionExtract(ST_MakeValid(geom), 3) AS geom
            FROM staging.parcels WHERE pidn = %(pidn)s AND valid_to IS NULL
        ), clips AS (
            SELECT f.fld_ar_id, f.fld_zone, f.sfha_tf, f.source_url, f.valid_from,
                   ST_CollectionExtract(ST_Intersection(
                       ST_CollectionExtract(ST_MakeValid(f.geom), 3), p.geom
                   ), 3) AS geom
            FROM staging.flood_zones f CROSS JOIN parcel p
            WHERE f.valid_to IS NULL AND f.geom && p.geom
        ), positive AS (
            SELECT * FROM clips WHERE NOT ST_IsEmpty(geom) AND ST_Area(geom) > 0
        ), coverage AS (
            SELECT ST_UnaryUnion(ST_Collect(geom)) AS mapped,
                   BOOL_OR(NOT COALESCE(sfha_tf = 'T' OR
                       (sfha_tf = 'F' AND UPPER(TRIM(fld_zone)) IN ('X', 'B', 'C')),
                       FALSE)) AS unclassified,
                   ST_UnaryUnion(ST_Collect(geom) FILTER (WHERE sfha_tf = 'T')) AS sfha,
                   ST_UnaryUnion(ST_Collect(geom) FILTER (
                       WHERE sfha_tf = 'F' AND UPPER(TRIM(fld_zone)) IN ('X', 'B', 'C')
                   )) AS known_non_sfha,
                   ARRAY_AGG(DISTINCT fld_ar_id) AS ids,
                   ARRAY_AGG(DISTINCT fld_zone) AS zones,
                   (ARRAY_AGG(fld_zone ORDER BY (sfha_tf = 'T') DESC NULLS LAST,
                       ST_Area(geom) DESC))[1] AS zone,
                   MIN(source_url) AS source_url, MAX(valid_from) AS observed_at
            FROM positive
        )
        SELECT p.geom IS NOT NULL AND NOT ST_IsEmpty(p.geom)
                   AND ST_Area(p.geom) > 0 AS usable_parcel,
               COALESCE(ST_Area(c.sfha) > 0, FALSE) AS has_overlap,
               COALESCE(ST_Covers(c.known_non_sfha, p.geom), FALSE)
                   AND NOT COALESCE(c.unclassified, FALSE) AS complete_negative,
               LEAST(100.0, 100 * ST_Area(ST_Transform(c.mapped, 32618))
                   / NULLIF(ST_Area(ST_Transform(p.geom, 32618)), 0)) AS coverage_pct,
               LEAST(100.0, 100 * ST_Area(ST_Transform(c.sfha, 32618))
                   / NULLIF(ST_Area(ST_Transform(p.geom, 32618)), 0)) AS overlap_pct,
               c.ids, c.zones, c.zone, c.source_url, c.observed_at
        FROM parcel p CROSS JOIN coverage c
        """,
        {"pidn": pidn},
    )
    row = cur.fetchone()
    status = "unknown"
    reason = "Mapped coverage is missing, incomplete, or includes undetermined zones."
    if not row or not row["usable_parcel"]:
        reason = "Usable parcel geometry is unavailable."
    elif row["has_overlap"]:
        status, reason = "overlap", None
    elif row["complete_negative"]:
        status, reason = "no_overlap", None

    cur.execute(
        """SELECT status, last_success_at FROM meta.asset_refresh_status
        WHERE asset_key = 'fema_flood_zones'"""
    )
    run = cur.fetchone()
    last_success = run["last_success_at"] if run else None
    freshness = "unknown"
    if last_success:
        freshness = (
            "current"
            if run["status"] == "success"
            and last_success >= datetime.now(UTC) - timedelta(days=8)
            else "stale"
        )
    coverage = (
        round(float(row["coverage_pct"]), 1)
        if row and row["coverage_pct"] is not None
        else None
    )
    overlap = None
    if status == "overlap":
        overlap = round(float(row["overlap_pct"]), 1)
    elif status == "no_overlap":
        overlap = 0.0
    receipt = None
    if row and row["ids"]:
        ids = [value for value in row["ids"] if value]
        receipt = evidence_item(
            scope=f"parcel:{pidn}",
            citation_key=f"flood:{pidn}",
            label="FEMA National Flood Hazard Layer",
            source_kind="official_flood_layer",
            source_record_id=",".join(ids) or pidn,
            url=with_arcgis_layer(row["source_url"], NFHL_FLOOD_HAZARD_LAYER),
            record_query=("FLD_AR_ID", ids),
            details={
                "screening_status": status,
                "zones": row["zones"],
                "mapped_coverage_pct": coverage,
                "parcel_overlap_pct": overlap,
                "freshness": freshness,
                "last_successful_run_at": last_success.isoformat()
                if last_success
                else None,
            },
            effective_at=None,
            observed_at=row["observed_at"],
            method="CountyIQ clips and unions current loaded FEMA polygons within this parcel. A negative result requires complete coverage by explicitly classified non-SFHA zones X, B or C. Boundary contact alone is not overlap.",
            caveat="This is screening of the loaded mapping, not a flood determination. Refresh time is not the map-effective date. Verify the effective FEMA map for the site.",
        )
    return {
        "in_flood_zone": status == "overlap",
        "zone": row["zone"] if row else None,
        "sfha": status == "overlap",
        "overlap_pct": overlap,
        "status": status,
        "mapped_coverage_pct": coverage,
        "reason": reason,
        "evidence": receipt,
        "freshness": {
            "status": freshness,
            "last_successful_run_at": last_success.isoformat()
            if last_success
            else None,
        },
    }
