"""Narrow current property evidence reads without changing source packets."""

from alembic import op

revision = "083"
down_revision = "082"
branch_labels = None
depends_on = None


ORIGINAL_PREDICATE = "WHERE parcel_id = ANY(evidence.related_pidns)"
INDEXED_PREDICATE = """WHERE evidence.inference_id IN (
                    SELECT link.inference_id
                    FROM public.municipal_evidence_links link
                    WHERE link.pidn = parcel_id
                ) AND parcel_id = ANY(evidence.related_pidns)"""


def _replace_property_predicate(previous: str, replacement: str) -> None:
    connection = op.get_bind()
    definition = connection.exec_driver_sql(
        "SELECT pg_get_functiondef("
        "'public.property_explanation_source(text,text,integer,integer)'::regprocedure)"
    ).scalar_one()
    if definition.count(previous) != 1:
        raise RuntimeError(
            "Unexpected property evidence function; review before migration"
        )
    connection.exec_driver_sql(definition.replace(previous, replacement))


def upgrade() -> None:
    # ST_DWithin uses geography for meter distances. The existing geometry
    # index cannot support this expression, causing a full scan per parcel.
    op.execute("""
        CREATE INDEX idx_planning_subdivisions_current_geography
        ON staging.planning_subdivisions USING gist ((geom::geography))
        WHERE valid_to IS NULL;
    """)
    # Every related PIDN necessarily has a link for this inference. Use those
    # indexed candidates before decoding county-wide municipal evidence; keep
    # the final relationship predicate and all currentness/rights guards.
    _replace_property_predicate(ORIGINAL_PREDICATE, INDEXED_PREDICATE)


def downgrade() -> None:
    _replace_property_predicate(INDEXED_PREDICATE, ORIGINAL_PREDICATE)
    op.execute("DROP INDEX staging.idx_planning_subdivisions_current_geography")
