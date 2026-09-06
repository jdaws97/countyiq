"""Guard: every field the parcels parser extracts must be persisted.

The 2026-08 source audit found the asset persisted only 10 of the ~35 parsed
fields — deed references, prev_owner, and the land/building value split were
fetched weekly and discarded, which also left development_signals'
ownership_change evidence permanently NULL. parcel_events now derives
transfer/value/structure events from these columns, so silently dropping one
again would blind that derivation.
"""

import inspect

from countyiq.assets.arcgis.parcels import (
    ALL_COLUMNS,
    KEY_COLUMNS,
    PARCEL_GEOMETRY_DIFF_SQL,
    PARCEL_GEOMETRY_SELECT_SQL,
    VALUE_COLUMNS,
    parcels_arcgis,
)
from countyiq.lib.parsers.arcgis_parcels import FIELD_MAP


def test_every_parsed_field_is_persisted():
    parsed_columns = set(FIELD_MAP.values()) | {"municipality"}
    persisted = set(ALL_COLUMNS)
    missing = parsed_columns - persisted
    assert not missing, (
        f"Parser extracts {sorted(missing)} but the asset never persists them "
        "— add them to VALUE_COLUMNS in assets/arcgis/parcels.py"
    )


def test_column_lists_are_consistent():
    assert ALL_COLUMNS == KEY_COLUMNS + VALUE_COLUMNS
    assert len(ALL_COLUMNS) == len(set(ALL_COLUMNS)), "duplicate column"
    assert "source_url" in VALUE_COLUMNS


def test_geometry_changes_are_versioned_and_missing_source_geometry_is_preserved():
    assert "ST_Equals(c.geom, t.geom)" in PARCEL_GEOMETRY_DIFF_SQL
    assert "t.geom IS NOT NULL" in PARCEL_GEOMETRY_DIFF_SQL
    assert PARCEL_GEOMETRY_SELECT_SQL == "COALESCE(t.geom, prev.geom)"


def test_event_source_fields_are_persisted():
    # The exact columns parcel_events classification depends on.
    for col in (
        "deed_bk",
        "deed_pg",
        "saledt",
        "price",
        "owner_full",
        "prev_owner",
        "mail_addr_full",
        "aprland",
        "aprbldg",
        "aprtotal",
        "yrblt",
        "res_living_area",
        "num_stories",
        "comm_struc",
        "comm_year_built",
        "comm_building_sq_ft",
    ):
        assert col in VALUE_COLUMNS, f"parcel_events needs {col} persisted"


def test_raw_parcel_payload_is_archived_before_scd2_mutation():
    source = inspect.getsource(parcels_arcgis.node_def.compute_fn.decorated_fn)

    assert 'require_source_use(authorization, "raw_retention")' in source
    assert "archive_file.write(json.dumps(feature, default=str))" in source
    assert "ANALYZE _tmp_parcels" in source
    index_position = source.index("idx_tmp_parcels_pidn")
    geometry_update_position = source.index("_flush_geometries(")
    assert index_position < geometry_update_position
    assert "if existing_count == 0:" in source
    archive_position = source.index("s3.archive_file(")
    update_position = source.index("UPDATE staging.parcels")
    assert archive_position < update_position
