"""Parser for PennDOT PA Projects MapServer response.

Maps ArcGIS field names to staging.penndot_projects column names.
Stores key fields as top-level columns and all other fields in JSONB data column.
"""

from datetime import date


FIELD_MAP = {
    "PROJ_ID": "project_id",
    "PROJECT_TITLE": "project_name",
    "IMPROVEMENT_CODE_DESC": "description",
    "PROJ_STATUS_DESC": "status",
    "PROJ_CLASS": "project_type",
    "PHS_EST_COST_AM": "cost",
    "MUNICIPAL_CODE": "municipality",
    "COUNTY_NAME": "county",
}

DATE_FIELDS = {
    "NTP_DATE": "start_date",
    "COMPLETION_DATE": "end_date",
}

# Fields to exclude from JSONB overflow (already mapped above + geometry/OID)
EXCLUDE_FROM_DATA = (
    set(FIELD_MAP.keys()) | set(DATE_FIELDS.keys()) | {"OBJECTID", "Shape"}
)


def _parse_date(val) -> date | None:
    """Parse a date string from PennDOT (format varies: MM/DD/YYYY or YYYYMMDD)."""
    if not val or val == "":
        return None
    val = str(val).strip()
    # Try MM/DD/YYYY
    if "/" in val:
        parts = val.split("/")
        if len(parts) == 3:
            try:
                return date(int(parts[2]), int(parts[0]), int(parts[1]))
            except (ValueError, IndexError):
                return None
    # Try YYYYMMDD
    if len(val) == 8 and val.isdigit():
        try:
            return date(int(val[:4]), int(val[4:6]), int(val[6:8]))
        except ValueError:
            return None
    return None


def parse_penndot_projects_features(raw_features: list[dict]) -> list[dict]:
    """Parse PennDOT project features into staging.penndot_projects records.

    Args:
        raw_features: ArcGIS feature dicts with 'attributes' key.

    Returns:
        List of flat dicts with staging.penndot_projects column names.
    """
    seen_ids = set()
    records = []
    for feat in raw_features:
        attrs = feat.get("attributes", {})
        # Under Construction Points uses PROJECT_ID; other selected categories
        # use PROJ_ID. Both are the publisher's project identifier, not OBJECTID.
        proj_id = attrs.get("PROJ_ID", attrs.get("PROJECT_ID"))
        if proj_id is None:
            continue

        proj_id_str = str(proj_id)
        # Deduplicate — same project can appear in multiple layers
        if proj_id_str in seen_ids:
            continue
        seen_ids.add(proj_id_str)

        record = {"project_id": proj_id_str}

        for src, dest in FIELD_MAP.items():
            if src == "PROJ_ID":
                continue  # already handled
            val = attrs.get(src)
            if src == "PROJ_CLASS" and src not in attrs:
                val = attrs.get("PROJECT_CLASS")
            if val is None or val == "":
                record[dest] = None
            elif dest == "cost":
                record[dest] = val  # keep as numeric
            else:
                record[dest] = str(val)

        for src, dest in DATE_FIELDS.items():
            record[dest] = _parse_date(attrs.get(src))

        # Overflow: all remaining fields go into data JSONB
        data = {}
        for key, val in attrs.items():
            if key not in EXCLUDE_FROM_DATA and val is not None and val != "":
                data[key] = val
        record["data"] = data if data else None

        records.append(record)

    return records
