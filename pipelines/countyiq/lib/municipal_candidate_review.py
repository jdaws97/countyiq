"""Record source-bound candidate retrieval reviews without changing matter aliases."""

from __future__ import annotations

import json

from countyiq.lib.intelligence_integrity import content_hash


def review_candidate_group(
    database,
    *,
    members: dict[str, str],
    reviewer: str,
    rationale: str,
    decision_origin: str,
    action: str = "group",
) -> dict:
    """Group complete current selections after an explicit original-source review.

    This only broadens the candidate source bundle. Accepted matter identities
    still require their existing source/alias/watch and contradiction checks.
    A later release review restores the normal candidate rules for every member.
    """
    if len(members) < 2 or action not in {"group", "release"}:
        raise ValueError("A candidate review needs at least two complete members")
    if decision_origin not in {"human_resolution", "auto_resolution"}:
        raise ValueError("Candidate review must identify its decision origin")
    if not reviewer.strip() or len(rationale.strip()) < 12:
        raise ValueError("Candidate review requires a reviewer and source rationale")
    with database.transaction() as cur:
        cur.execute(
            "LOCK TABLE meta.municipal_matter_aliases IN SHARE ROW EXCLUSIVE MODE"
        )
        cur.execute(
            "LOCK TABLE meta.municipal_candidate_reviews IN SHARE ROW EXCLUSIVE MODE"
        )
        cur.execute(
            "SELECT input.event_key, input.source_fingerprint, input.municipality, "
            "scopes.candidate_scope, scopes.bundle_key "
            "FROM public.current_municipal_matter_inputs input "
            "JOIN public.current_municipal_matter_scopes scopes USING (event_key) "
            "WHERE input.event_key = ANY(%s::text[])",
            (sorted(members),),
        )
        rows = cur.fetchall()
        if {row[0]: row[1] for row in rows} != members:
            raise ValueError(
                "Candidate review does not match current source fingerprints"
            )
        if len({row[2] for row in rows}) != 1:
            raise ValueError("Candidate review cannot cross municipality boundaries")
        if any(not row[3].startswith(("selection:", "reviewed:")) for row in rows):
            raise ValueError(
                "Candidate review cannot override a property or formal case scope"
            )
        cur.execute(
            "SELECT event_key FROM public.current_municipal_matter_scopes "
            "WHERE bundle_key = ANY(%s::text[])",
            (sorted({row[4] for row in rows}),),
        )
        if {row[0] for row in cur.fetchall()} != set(members):
            raise ValueError(
                "Candidate review must cover every record in affected bundles"
            )
        candidate_key = "reviewed:" + content_hash(
            {"municipality": rows[0][2], "members": members}
        )
        cur.execute(
            "INSERT INTO meta.municipal_candidate_reviews "
            "(candidate_key, action, members, reviewer, rationale, decision_origin) "
            "VALUES (%s, %s, %s::jsonb, %s, %s, %s) RETURNING review_id",
            (
                candidate_key,
                action,
                json.dumps(members),
                reviewer,
                rationale,
                decision_origin,
            ),
        )
        return {
            "review_id": cur.fetchone()[0],
            "candidate_key": candidate_key,
            "action": action,
        }
