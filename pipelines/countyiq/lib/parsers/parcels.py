"""Parser for ArcGIS Parcels FeatureServer response.

Extracts attribute fields from raw ArcGIS features into flat dicts
matching the staging.parcels table schema.
"""


# Map ArcGIS field names → staging.parcels column names
FIELD_MAP = {
    "PIDN": "pidn",
    "DISTRICT": "district",
    "BLOCK": "block",
    "MAP": "map",
    "PARCEL": "parcel",
    "DEED_BK": "deed_bk",
    "DEED_PG": "deed_pg",
    "PROPADR": "propadr",
    "OWNER_FULL": "owner_full",
    "OWN_NAME1": "own_name1",
    "OWN_NAME2": "own_name2",
    "MAIL_ADDR_FULL": "mail_addr_full",
    "PREV_OWNER": "prev_owner",
    "CLASS": "class",
    "LUC": "luc",
    "ACRES": "acres",
    "STYLE": "style",
    "NUM_STORIE": "num_stories",
    "RES_LIVING_AREA": "res_living_area",
    "YRBLT": "yrblt",
    "CLEAN_GREEN": "clean_green",
    "HEATSYS": "heatsys",
    "FUEL": "fuel",
    "APRLAND": "aprland",
    "APRBLDG": "aprbldg",
    "APRTOTAL": "aprtotal",
    "SALEDT": "saledt",
    "PRICE": "price",
    "PREV_PRICE": "prev_price",
    "SCHOOL_DIS": "school_dis",
    "COMM_STRUC": "comm_struc",
    "COMM_YEAR_BUILT": "comm_year_built",
    "COMM_BUILDING_SQ_FT": "comm_building_sq_ft",
    "GRADE": "grade",
    "CDU": "cdu",
}

# Municipality is stored in a separate field depending on the ArcGIS layer config
MUNICIPALITY_FIELDS = ["MUNICIPALITY", "MUNI", "MUN_NAME", "MUNI_NAME"]


def parse_parcels_features(raw_features: list[dict]) -> list[dict]:
    """Parse ArcGIS feature dicts into staging.parcels records.

    Args:
        raw_features: List of ArcGIS feature dicts with 'attributes' key.

    Returns:
        List of flat dicts with staging.parcels column names.
    """
    records = []
    for feat in raw_features:
        attrs = feat.get("attributes", {})
        pidn = attrs.get("PIDN")
        if not pidn:
            continue

        record = {}
        for src_field, dest_col in FIELD_MAP.items():
            val = attrs.get(src_field)
            if val is not None:
                record[dest_col] = str(val) if val != "" else None
            else:
                record[dest_col] = None

        # Try multiple possible municipality field names
        municipality = None
        for muni_field in MUNICIPALITY_FIELDS:
            municipality = attrs.get(muni_field)
            if municipality:
                break
        record["municipality"] = str(municipality) if municipality else None

        records.append(record)

    return records
