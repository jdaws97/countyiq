"""Only a named reference bound to the selected subject can group agendas."""

# Shared fixture is requested by pytest by name.
# ruff: noqa: F811

import json

import pytest

from api.tests.test_municipal_evidence import append_read, writer
from api.tests.test_municipal_evidence_workflow import add_source  # noqa: F401


@pytest.mark.parametrize(
    "title,subject,context,expected",
    [
        (
            "Moratorium on Data Center Applications",
            "12) NEW BUSINESS:\na) Resolution 2026-13: Moratorium on Data Center Applications\n",
            "",
            "resolution-2026-13",
        ),
        (
            "Moratorium on Data Center Applications",
            "a) Consider the moratorium on data center applications.",
            "Resolution 2026-13: Moratorium on Data Center Applications",
            None,
        ),
        (
            "Canal Road Betterment Program Agreement",
            "a) Resolution 2026-13: Moratorium on Data Center Applications\nc) Canal Road Betterment Program Agreement",
            "",
            None,
        ),
        (
            "Moratorium on Data Center Applications",
            "Resolution 2026-13: Moratorium on Data Center Applications\nResolution 2026-14: Moratorium on Data Center Applications",
            "",
            None,
        ),
        ("LD 2026-02 Preliminary Plan", "", "", "ld2026-02"),
        ("SD 2026-02 Preliminary Plan", "", "", "sd2026-02"),
    ],
)
def test_case_reference_requires_own_named_subject(title, subject, context, expected):
    card = {
        "title": title,
        "subject_passages": [{"text": subject}],
        "passages": [{"text": subject}, {"text": context}],
    }
    with writer() as cur:
        cur.execute(
            "SELECT public.municipal_card_case_reference(%s::jsonb)",
            (json.dumps(card),),
        )
        assert cur.fetchone()[0] == expected


def test_original_and_amended_agendas_share_the_named_resolution_scope(add_source):
    ids = []
    title = "Moratorium on Data Center Applications"
    for heading in ("Agenda", "Agenda amended at meeting"):
        source_id, _, payload = add_source(
            f"{heading}\na) Resolution 2026-13: {title}\n"
        )
        payload["cards"][0]["title"] = title
        with writer() as cur:
            append_read(cur, source_id, payload)
        ids.append(source_id)
    with writer() as cur:
        cur.execute(
            "SELECT bundle_key, candidate_scope, event_key "
            "FROM public.current_municipal_matter_scopes "
            "WHERE proceeding_id = ANY(%s)",
            (ids,),
        )
        rows = cur.fetchall()
        cur.execute(
            "SELECT source FROM public.current_municipal_matter_sources "
            "WHERE bundle_key = %s",
            (rows[0][0],),
        )
        source = cur.fetchone()[0]
    assert len(rows) == 2
    assert len({row[0] for row in rows}) == 1
    assert {row[1] for row in rows} == {"case:resolution-2026-13"}
    assert len({row[2] for row in rows}) == 2
    assert {record["key"] for record in source["records"]} == {row[2] for row in rows}
    assert len(source["records"]) == 2
