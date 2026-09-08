"""Focused guards for explicit municipal matter identity review proposals."""

from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
from countyiq.lib.intelligence_integrity import content_hash
from countyiq.lib.intelligence_resolution import (
    ContradictionResolutionError,
    resolve_contradiction,
)
from countyiq.lib.municipal_matters import (
    check_identity_review_state,
    persist_matters,
    reviewed_matter_keys,
)

from tests.test_intelligence_integrity_schema import _connect, _DatabaseAdapter
from tests.test_municipal_matters import _matter, _source

SOURCE = {
    "subject_key": "municipal:bundle",
    "records": [{"key": "one"}, {"key": "two"}],
    "sources": [],
}
MATTERS = [{"record_keys": ["one"]}, {"record_keys": ["two"]}]
KNOWN = {"one": "matter:one", "two": "matter:two"}


def review(**changes):
    value = {
        "source_hash": content_hash(SOURCE),
        "expected_aliases": KNOWN,
        "proposed_aliases": KNOWN,
        "decision_origin": "human_resolution",
        "reviewer": "operator@example.test",
        "rationale": "The source distinguishes these two applications.",
    }
    value.update(changes)
    return value


def test_reviewed_keys_preserve_an_explicit_split_without_changing_aliases():
    resolved = reviewed_matter_keys(MATTERS, SOURCE, KNOWN, review())

    assert [matter["key"] for matter in resolved] == ["matter:one", "matter:two"]


@pytest.mark.parametrize(
    "changes,error",
    [
        ({"source_hash": "stale"}, "current source"),
        ({"expected_aliases": {"one": "matter:one"}}, "aliases changed"),
        ({"proposed_aliases": {"one": "matter:one"}}, "complete source bundle"),
        (
            {"proposed_aliases": {"one": "matter:outside", "two": "matter:two"}},
            "unrelated",
        ),
    ],
)
def test_reviewed_keys_fail_closed_for_stale_or_outside_identity(changes, error):
    with pytest.raises(ValueError, match=error):
        reviewed_matter_keys(MATTERS, SOURCE, KNOWN, review(**changes))


class Cursor:
    def __init__(self, responses):
        self.responses = iter(responses)

    def execute(self, *_args):
        pass

    def fetchall(self):
        return next(self.responses)

    def fetchone(self):
        return next(self.responses)


def test_review_state_blocks_outside_bundle_aliases():
    cursor = Cursor([list(KNOWN.items()), ("outside",), None])

    with pytest.raises(ValueError, match="outside this bundle"):
        check_identity_review_state(cursor, SOURCE, review())


def test_review_state_blocks_watch_added_before_resolution():
    cursor = Cursor([list(KNOWN.items()), None, (1,)])

    with pytest.raises(ValueError, match="watch migration"):
        check_identity_review_state(cursor, SOURCE, review())


class SourceCursor:
    """Supply a synthetic current source; all ledger/alias/watch SQL is real."""

    def __init__(self, cursor, source, dict_rows):
        self.cursor = cursor
        self.source = source
        self.dict_rows = dict_rows
        self.source_query = False

    def execute(self, sql, params=None):
        self.source_query = sql.startswith(
            "SELECT source FROM public.current_municipal_matter_sources "
        )
        if self.source_query:
            assert params == (self.source["subject_key"],)
        else:
            self.cursor.execute(sql, params)

    def fetchone(self):
        if self.source_query:
            return {"source": self.source} if self.dict_rows else (self.source,)
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()


class MatterDatabase(_DatabaseAdapter):
    def __init__(self, connection, source):
        super().__init__(connection)
        self.source = source

    @contextmanager
    def transaction(self, *, dict_rows=False):
        with super().transaction(dict_rows=dict_rows) as cursor:
            yield SourceCursor(cursor, self.source, dict_rows)


@pytest.mark.integration
@pytest.mark.parametrize("decision", ["accept_challenger", "accept_prior"])
def test_split_requires_review_and_resolves_atomically_with_watch_guard(decision):
    suffix = uuid4().hex
    first, second = f"R{suffix}1", f"R{suffix}2"
    source = _source(
        (first, "2026-01-01", f"P{suffix}1", "Use and parking relief requested."),
        (
            second,
            "2026-02-01",
            f"P{suffix}2",
            "A separate application requests relief.",
        ),
    )
    source["subject_key"] = f"municipal-bundle:test-{suffix}"
    connection = _connect()
    database = MatterDatabase(connection, source)
    config = SimpleNamespace(model_path="test/matter-author")
    initial = {"matters": [_matter([first, second])]}
    split = {"matters": [_matter([first]), _matter([second])]}
    try:
        prior = persist_matters(database, source, initial, config)
        assert prior.accepted
        original_key = "matter:" + content_hash(first)[:24]
        new_key = "matter:" + content_hash(second)[:24]
        expected = {first: original_key, second: original_key}
        proposed = {first: original_key, second: new_key}
        packet = {
            "source_hash": content_hash(source),
            "expected_prior_inference_id": prior.inference_id,
            "expected_aliases": expected,
            "proposed_aliases": proposed,
            "decision_origin": "auto_resolution",
            "reviewer": "test AI source review",
            "rationale": "The supplied sources document separate applications.",
        }
        with pytest.raises(ValueError, match="would split"):
            persist_matters(database, source, split, config)
        stale = {**packet, "expected_prior_inference_id": prior.inference_id + 1000}
        with pytest.raises(ValueError, match="current accepted source version"):
            persist_matters(database, source, split, config, identity_review=stale)
        challenger = persist_matters(
            database, source, split, config, identity_review=packet
        )
        assert not challenger.accepted
        assert challenger.contradiction_id is not None

        def aliases():
            return dict(
                database.execute(
                    "SELECT record_key, matter_key FROM meta.municipal_matter_aliases "
                    "WHERE record_key = ANY(%s::text[])",
                    ([first, second],),
                )
            )

        assert aliases() == expected
        arguments = {
            "contradiction_id": challenger.contradiction_id,
            "resolution": decision,
            "resolved_by": "test AI source review",
            "rationale": "Both original sources and the proposed partition were reviewed.",
            "expected_source_hash": content_hash(source),
            "decision_origin": "auto_resolution",
        }
        database.source = {**source, "changed_source": True}
        with pytest.raises(
            ContradictionResolutionError, match="current source evidence"
        ):
            resolve_contradiction(database, **arguments)
        database.source = source
        assert aliases() == expected
        if decision == "accept_challenger":
            workspace = str(uuid4())
            database.execute(
                "INSERT INTO public.watchspaces(workspace_id, token_hash) VALUES (%s, %s)",
                (workspace, suffix),
            )
            database.execute(
                "INSERT INTO public.watch_items(workspace_id,kind,subject_key,label) "
                "VALUES (%s,'project',%s,'Test matter')",
                (workspace, original_key),
            )
            with pytest.raises(ValueError, match="watch migration"):
                resolve_contradiction(database, **arguments)
            assert aliases() == expected
            assert database.execute(
                "SELECT COUNT(*) FROM meta.intelligence_contradiction_resolutions "
                "WHERE contradiction_id = %s",
                (challenger.contradiction_id,),
            ) == [(0,)]
            database.execute(
                "DELETE FROM public.watchspaces WHERE workspace_id = %s", (workspace,)
            )
        result = resolve_contradiction(database, **arguments)
        assert aliases() == (proposed if decision == "accept_challenger" else expected)
        ledger = database.execute(
            "SELECT decision_origin, resolution_source_inference_id, payload "
            "FROM meta.intelligence_inference_history WHERE inference_id = %s",
            (result.resolved_inference_id,),
        )[0]
        assert ledger[0] == "auto_resolution"
        assert ledger[1] == (
            challenger.inference_id
            if decision == "accept_challenger"
            else prior.inference_id
        )
        assert len(ledger[2]["matters"]) == (
            2 if decision == "accept_challenger" else 1
        )
    finally:
        connection.close()
