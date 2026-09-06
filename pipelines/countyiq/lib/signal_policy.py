"""Which source signals warrant interpretation rather than factual display."""

# Screens, measurements and constraints remain available as source context.
# A missing footprint cannot establish vacancy, occupancy or availability.
CONTEXT_ONLY_SIGNALS = frozenset(
    {
        "nearby_subdivision",
        "economic_development_park",
        "tax_distress",
        "penndot_project",
        "growth_area",
        "development_overlay",
        "local_traffic_activity",
        "soil_constraint",
        "zoning_constraint",
        "flood_zone",
        "environmental_diligence",
        "conservation_easement",
        "ag_security",
        "vacancy",
    }
)

INTERPRETIVE_SIGNAL_KEYS = (
    "active_subdivision",
    "municipal_action",
    "ownership_change",
    "assemblage",
    "entity_assemblage",
    "zoning_mismatch",
)

# Only these code-owned constants are interpolated into query definitions.
CONTEXT_ONLY_SIGNALS_SQL = ", ".join(f"'{key}'" for key in sorted(CONTEXT_ONLY_SIGNALS))
INTERPRETIVE_SIGNAL_KEYS_SQL = ", ".join(f"'{key}'" for key in INTERPRETIVE_SIGNAL_KEYS)
