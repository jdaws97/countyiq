"""Evaluate current municipal scope inputs once for each emerging feed read."""

from alembic import op

revision = "084"
down_revision = "083"
branch_labels = None
depends_on = None

INPUT_TYPE = "public.current_municipal_matter_scoped_inputs[]"


def _definition(signature: str) -> str:
    return (
        op.get_bind()
        .exec_driver_sql("SELECT pg_get_functiondef(%s::regprocedure)", (signature,))
        .scalar_one()
    )


def _replace(definition: str, before: str, after: str, *, count: int = 1) -> str:
    if definition.count(before) != count:
        raise RuntimeError("Unexpected emerging source definition; review migration")
    return definition.replace(before, after)


def _create_input_helpers() -> None:
    # Reuse the exact canonical source builders. Typed rows preserve all fields
    # and ordering; only the source of their already-current scope inputs changes.
    matter = _definition("public.municipal_matter_source(text)")
    matter = _replace(
        matter,
        "public.municipal_matter_source(requested_bundle text)",
        "public.municipal_matter_source_from_inputs("
        f"requested_bundle text, scoped_inputs {INPUT_TYPE})",
    )
    matter = _replace(
        matter,
        "FROM public.current_municipal_matter_scoped_inputs current",
        "FROM unnest(scoped_inputs) current",
    )
    op.get_bind().exec_driver_sql(matter)

    scope = _definition(
        "public.emerging_scope_source(text,text,integer,integer,integer)"
    )
    scope = _replace(
        scope,
        "public.emerging_scope_source(",
        "public.emerging_scope_source_from_inputs(",
    )
    scope = _replace(
        scope,
        "neighbor_limit integer)",
        f"neighbor_limit integer, scoped_inputs {INPUT_TYPE})",
    )
    scope = _replace(
        scope,
        "public.municipal_matter_source(requested_bundle)",
        "public.municipal_matter_source_from_inputs(requested_bundle, scoped_inputs)",
    )
    scope = _replace(
        scope,
        "public.municipal_matter_source(selected.bundle_key)",
        "public.municipal_matter_source_from_inputs(selected.bundle_key, scoped_inputs)",
    )
    scope = _replace(
        scope,
        "FROM public.current_municipal_matter_scoped_inputs input",
        "FROM unnest(scoped_inputs) input",
        count=2,
    )
    op.get_bind().exec_driver_sql(scope)


def _create_current_view(*, shared: bool) -> None:
    shared_inputs = (
        """,
        scoped AS MATERIALIZED (
            SELECT array_agg(input) AS rows
            FROM public.current_municipal_matter_scoped_inputs input
            WHERE EXISTS (SELECT 1 FROM published)
        )"""
        if shared
        else ""
    )
    source_function = (
        "public.emerging_scope_source_from_inputs"
        if shared
        else "public.emerging_scope_source"
    )
    join = "CROSS JOIN scoped" if shared else ""
    extra_argument = ", scoped.rows" if shared else ""
    op.execute(f"""
        CREATE OR REPLACE VIEW public.current_emerging_analyses AS
        WITH latest AS MATERIALIZED (
            SELECT DISTINCT ON (subject_key) history.*
            FROM meta.intelligence_inference_history history
            WHERE output_kind = 'emerging_analysis' AND disposition = 'accepted'
            ORDER BY subject_key, inference_id DESC
        ), published AS MATERIALIZED (
            SELECT latest.* FROM latest
            JOIN LATERAL (
                SELECT action FROM meta.emerging_intelligence_publications publication
                WHERE publication.inference_id = latest.inference_id
                ORDER BY publication_id DESC LIMIT 1
            ) publication ON publication.action = 'publish'
            WHERE latest.payload->>'contract_version' = '1'
                AND latest.payload->'packet'->>'temporal_mode' = 'current'
        ){shared_inputs}
        SELECT published.inference_id, published.subject_key, published.created_at,
            published.payload
        FROM published {join}
        WHERE published.payload->'packet'->'source' = {source_function}(
            published.payload->'packet'->'source'->>'seed_bundle',
            published.payload->'packet'->'source'->'settings'->>'open_data_key',
            (published.payload->'packet'->'source'->'settings'->>'planning_radius_m')::integer,
            (published.payload->'packet'->'source'->'settings'->>'environmental_radius_m')::integer,
            (published.payload->'packet'->'source'->'settings'->>'neighbor_limit')::integer
            {extra_argument}
        );
    """)


def upgrade() -> None:
    _create_input_helpers()
    _create_current_view(shared=True)


def downgrade() -> None:
    _create_current_view(shared=False)
    op.execute(
        "DROP FUNCTION public.emerging_scope_source_from_inputs("
        f"text,text,integer,integer,integer,{INPUT_TYPE})"
    )
    op.execute(
        f"DROP FUNCTION public.municipal_matter_source_from_inputs(text,{INPUT_TYPE})"
    )
