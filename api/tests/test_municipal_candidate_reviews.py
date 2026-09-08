"""Integration coverage for source-bound candidate retrieval reviews."""

import json
import os
import subprocess

import psycopg2

from api.tests.conftest import DB_ENV, PIPELINES_DIR
from api.tests.test_municipal_evidence import writer
from api.tests.test_municipal_evidence_workflow import (
    add_source as add_source_fixture,  # noqa: F401
)


def _review(packet):
    result = subprocess.run(
        [
            str(PIPELINES_DIR / ".venv/bin/python"),
            "scripts/review_municipal_candidates.py",
            "-",
        ],
        cwd=PIPELINES_DIR,
        env={**os.environ, **DB_ENV, "PYTHONPATH": str(PIPELINES_DIR)},
        input=json.dumps(packet),
        capture_output=True,
        text=True,
        check=False,
    )
    return result


def _members(proceeding_ids):
    with psycopg2.connect(DB_ENV["DATABASE_URL"]) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT input.event_key, input.source_fingerprint "
            "FROM public.current_municipal_matter_inputs input "
            "JOIN public.current_municipal_matter_scopes scopes USING (event_key) "
            "WHERE scopes.candidate_scope LIKE 'selection:%%' "
            "AND input.proceeding_id = ANY(%s::bigint[]) ORDER BY input.event_key",
            (proceeding_ids,),
        )
        return dict(cur.fetchall())


def _scopes(event_keys):
    with psycopg2.connect(DB_ENV["DATABASE_URL"]) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT event_key, candidate_scope FROM public.current_municipal_matter_scopes "
            "WHERE event_key = ANY(%s) ORDER BY event_key",
            (list(event_keys),),
        )
        return dict(cur.fetchall())


def _current_source(source):
    script = """
import json
import sys
from countyiq.lib.municipal_matters import current_matter_source
from countyiq.resources.database import make_database_resource

database = make_database_resource()
database.setup_for_execution(None)
try:
    with database.transaction() as cursor:
        print(json.dumps(current_matter_source(cursor, json.load(sys.stdin))))
finally:
    database.teardown_after_execution(None)
"""
    result = subprocess.run(
        [str(PIPELINES_DIR / ".venv/bin/python"), "-c", script],
        cwd=PIPELINES_DIR,
        env={**os.environ, **DB_ENV, "PYTHONPATH": str(PIPELINES_DIR)},
        input=json.dumps(source),
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_candidate_review_groups_releases_and_fails_closed(
    add_source_fixture,  # noqa: F811
):
    first, _, _ = add_source_fixture("A planning review for a civic site.")
    second, _, _ = add_source_fixture("A later review of the civic site plan.")
    third, _, _ = add_source_fixture("A separate application for a library.")
    members = _members([first, second])
    third_members = _members([third])
    assert len(members) == 2
    event_keys = set(members)
    with psycopg2.connect(DB_ENV["DATABASE_URL"]) as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM meta.municipal_candidate_reviews")
        initial_review_count = cur.fetchone()[0]
        cur.execute(
            "SELECT record_key, matter_key FROM meta.municipal_matter_aliases "
            "WHERE record_key = ANY(%s)",
            (list(event_keys),),
        )
        initial_aliases = dict(cur.fetchall())
        cur.execute(
            "SELECT source FROM public.current_municipal_matter_sources "
            "WHERE source->>'candidate_scope' = %s",
            ("selection:" + next(iter(members)),),
        )
        original_source = cur.fetchone()[0]
    packet = {
        "members": members,
        "reviewer": "test AI source review",
        "rationale": "The reviewed sources should be retrieved together.",
        "decision_origin": "auto_resolution",
    }

    grouped = _review(packet)
    assert grouped.returncode == 0, grouped.stderr
    candidate_key = json.loads(grouped.stdout)["candidate_key"]
    assert set(_scopes(event_keys).values()) == {candidate_key}
    assert _current_source(original_source) is None
    with writer() as cur:
        cur.execute(
            "SELECT source FROM public.current_municipal_matter_sources "
            "WHERE source->>'candidate_scope' = %s",
            (candidate_key,),
        )
        source = cur.fetchone()[0]
        assert {
            row["key"]: row["source_fingerprint"] for row in source["records"]
        } == members
        assert {row["record_key"] for row in source["sources"]} == event_keys
        cur.execute(
            "SELECT source FROM public.municipal_matter_source(%s)",
            (source["subject_key"],),
        )
        assert cur.fetchone()[0] == source
        cur.execute(
            "SELECT record_key, matter_key FROM meta.municipal_matter_aliases "
            "WHERE record_key = ANY(%s)",
            (list(event_keys),),
        )
        assert dict(cur.fetchall()) == initial_aliases

    first_key = next(iter(members))
    partial = _review(
        {**packet, "members": {first_key: members[first_key], **third_members}}
    )
    assert partial.returncode != 0
    assert "cover every record in affected bundles" in partial.stderr

    released = _review({**packet, "action": "release"})
    assert released.returncode == 0, released.stderr
    assert all(scope.startswith("selection:") for scope in _scopes(event_keys).values())
    assert _current_source(original_source) == original_source

    stale = _review({**packet, "members": {**members, next(iter(event_keys)): "stale"}})
    assert stale.returncode != 0
    with psycopg2.connect(DB_ENV["DATABASE_URL"]) as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM meta.municipal_candidate_reviews")
        review_count = cur.fetchone()[0]
    assert review_count == initial_review_count + 2

    regrouped = _review(packet)
    assert regrouped.returncode == 0, regrouped.stderr
    changed_key = next(iter(event_keys))
    with writer() as cur:
        cur.execute(
            "UPDATE staging.public_proceedings SET raw_text = raw_text || ' changed' "
            "WHERE id = (SELECT proceeding_id FROM public.current_municipal_matter_inputs "
            "WHERE event_key = %s)",
            (changed_key,),
        )
    remaining = _scopes(event_keys)
    assert len(remaining) == 1
    assert all(scope.startswith("selection:") for scope in remaining.values())
