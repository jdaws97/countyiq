"""Parser for ArcGIS Planning Subdivisions FeatureServer response.

Maps ArcGIS field names to staging.planning_subdivisions column names.
"""

from datetime import datetime, timezone


FIELD_MAP = {
    "SEQU_NUM": "sequ_num",
    "MCD": "mcd",
    "PLAN_TITLE": "plan_title",
    "PT_PRELIM": "pt_prelim",
    "PT_FINAL": "pt_final",
    "PT_LAND_DEV": "pt_land_dev",
    "PT_SUBDIV": "pt_subdiv",
    "PT_BLDG_ADD": "pt_bldg_add",
    "CAP": "cap",
    "COM": "com",
    "ST_LENGTH": "st_length",
    "WATER": "water",
    "SEWER": "sewer",
    "AG_USE": "ag_use",
    "COM_USE": "com_use",
    "IND_USE": "ind_use",
    "MF_USE": "mf_use",
    "MHP_USE": "mhp_use",
    "SR_USE": "sr_use",
    "SF_USE": "sf_use",
    "OTHER_USE": "other_use",
    "TOTAL_ACRES": "total_acres",
    "EXIST_LOTS": "exist_lots",
    "PROP_LOTS": "prop_lots",
    "BLDG_LOTS": "bldg_lots",
    "DEV_LOTS": "dev_lots",
    "EXIST_DU": "exist_du",
    "PROP_DU": "prop_du",
    "PROP_BLDG_ADD_SQFT": "prop_bldg_add_sqft",
    "PROP_NEW_BLDG_SQFT": "prop_new_bldg_sqft",
    "WATERSHED": "watershed",
    "CONSISTENT": "consistent",
    "NOTES": "notes",
    "ENGINEER": "engineer",
    "OBJECTID": "objectid",
}


def parse_planning_subdivision_features(features: list[dict]) -> list[dict]:
    """Parse ArcGIS Planning Subdivision features into staging records.

    Args:
        features: ArcGIS feature dicts with 'attributes' key.

    Returns:
        List of flat dicts with staging.planning_subdivisions column names.
    """
    records = []
    for feat in features:
        attrs = feat.get("attributes", {})
        sequ_num = attrs.get("SEQU_NUM")
        if sequ_num is None:
            continue

        record = {}
        for src, dest in FIELD_MAP.items():
            val = attrs.get(src)
            record[dest] = val if val is not None and val != "" else None

        # Keep sequ_num as-is (not stringified)
        record["sequ_num"] = sequ_num

        # DATE_RCVD comes as epoch milliseconds from ArcGIS
        date_rcvd_raw = attrs.get("DATE_RCVD")
        if date_rcvd_raw is not None and isinstance(date_rcvd_raw, (int, float)):
            record["date_rcvd"] = datetime.fromtimestamp(
                date_rcvd_raw / 1000, tz=timezone.utc
            )
        else:
            record["date_rcvd"] = None

        records.append(record)

    return records
