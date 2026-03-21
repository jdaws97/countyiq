"""Parser for ArcGIS Zoning FeatureServer response.

Maps ArcGIS field names to staging.zoning column names.
"""

from datetime import datetime, timezone


FIELD_MAP = {
    "ZRECID": "zrecid",
    "MUNI_NAME": "muni_name",
    "DISTRICT": "district",
    "ZCODE": "zcode",
    "ZNAME": "zname",
    "ZTYPE": "ztype",
    "GEN_ZCODE": "gen_zcode",
    "GEN_ZNAME": "gen_zname",
    "CHANGETYPE": "changetype",
    "PRJ_NUM": "prj_num",
    "MUNI_ORD": "muni_ord",
    "PREV_ZCODE": "prev_zcode",
    "PREV_ZNAME": "prev_zname",
}


def parse_zoning_features(raw_features: list[dict]) -> list[dict]:
    """Parse ArcGIS Zoning features into staging.zoning records.

    Args:
        raw_features: ArcGIS feature dicts with 'attributes' key.

    Returns:
        List of flat dicts with staging.zoning column names.
    """
    records = []
    for feat in raw_features:
        attrs = feat.get("attributes", {})
        zrecid = attrs.get("ZRECID")
        if zrecid is None:
            continue

        record = {}
        for src, dest in FIELD_MAP.items():
            val = attrs.get(src)
            record[dest] = str(val) if val is not None and val != "" else None

        # Keep zrecid as int (not string)
        record["zrecid"] = zrecid

        # ADPT_DATE comes as epoch milliseconds from ArcGIS
        adpt_raw = attrs.get("ADPT_DATE")
        if adpt_raw and isinstance(adpt_raw, (int, float)):
            record["adpt_date"] = datetime.fromtimestamp(adpt_raw / 1000, tz=timezone.utc).isoformat()
        else:
            record["adpt_date"] = None

        records.append(record)

    return records
