"""Safety contracts for the county-sized streaming structures loader."""

import inspect

from countyiq.assets.arcgis.structures import structures_arcgis


def test_raw_structure_payload_is_archived_before_scd2_mutation():
    source = inspect.getsource(structures_arcgis.node_def.compute_fn.decorated_fn)

    assert 'require_source_use(authorization, "raw_retention")' in source
    assert "archive_file.write(json.dumps(feat, default=str))" in source
    assert "ANALYZE _tmp_structures" in source
    archive_position = source.index("s3.archive_file(")
    update_position = source.index("UPDATE staging.structures")
    assert archive_position < update_position
