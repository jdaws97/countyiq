"""Parser for ArcGIS Roads FeatureServer response.

Maps ArcGIS field names to staging.roads column names.
"""

FIELD_MAP = {
    "RCL_NGUID": "rcl_nguid",
    "StreetName": "street_name",
    "St_PreDir": "st_pre_dir",
    "St_PreTyp": "st_pre_typ",
    "St_PosTyp": "st_pos_typ",
    "St_PosDir": "st_pos_dir",
    "RoadClass": "road_class",
    "SpeedLimit": "speed_limit",
    "OneWay": "one_way",
    "RTE_NUM": "rte_num",
    "FromAddr_L": "from_addr_l",
    "ToAddr_L": "to_addr_l",
    "FromAddr_R": "from_addr_r",
    "ToAddr_R": "to_addr_r",
    "IncMuni_L": "inc_muni_l",
    "IncMuni_R": "inc_muni_r",
    "PostCode_L": "post_code_l",
    "PostCode_R": "post_code_r",
}

# Fields that should stay as integers, not stringified
INT_FIELDS = {"speed_limit", "from_addr_l", "to_addr_l", "from_addr_r", "to_addr_r"}


def parse_roads_features(raw_features: list[dict]) -> list[dict]:
    """Parse ArcGIS Roads features into staging.roads records.

    Args:
        raw_features: ArcGIS feature dicts with 'attributes' key.

    Returns:
        List of flat dicts with staging.roads column names.
    """
    records = []
    for feat in raw_features:
        attrs = feat.get("attributes", {})
        rcl_nguid = attrs.get("RCL_NGUID")
        if not rcl_nguid:
            continue

        record = {}
        for src, dest in FIELD_MAP.items():
            val = attrs.get(src)
            if val is None or val == "":
                record[dest] = None
            elif dest in INT_FIELDS:
                record[dest] = val
            else:
                record[dest] = str(val)

        records.append(record)

    return records
