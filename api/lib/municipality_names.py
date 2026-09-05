"""Municipality-name pattern helpers shared by the municipality and feed routes.

York County publishes two spellings of the same jurisdiction: the parcel and
tax files use the short county form ("CARROLL TWP", "DELTA BORO") while
extracted municipal events carry the public body's own name ("Carroll
Township", "Delta Borough"). Routes that match either spelling use these
helpers so one filter works across both record families.
"""


def muni_name_to_pattern(name: str) -> str:
    """Convert a municipality short name to a LIKE pattern matching tax districts.

    'CARROLL TWP'  -> 'CARROLL TOWNSHIP%'
    'YORK CITY'    -> 'YORK CITY%'
    'DELTA BORO'   -> 'DELTA BOROUGH%'
    'YORKANA BORO' -> 'YORKANA BOROUGH%'
    """
    upper = name.upper()
    if upper.endswith(" TWP"):
        return name[:-4] + " TOWNSHIP%"
    if upper.endswith(" BORO"):
        return name[:-5] + " BOROUGH%"
    return name + "%"


def municipality_event_patterns(name: str) -> list[str]:
    """LIKE patterns that match both the short county spelling and the long one."""
    base = name.strip()
    patterns = {base + "%", muni_name_to_pattern(base)}
    upper = base.upper()
    if upper.endswith(" TOWNSHIP"):
        patterns.add(base[:-9] + " TWP%")
    if upper.endswith(" BOROUGH"):
        patterns.add(base[:-8] + " BORO%")
    return sorted(patterns)
