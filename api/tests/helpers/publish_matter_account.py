import json
import sys

PIDN = sys.argv[1]
SPLIT = sys.argv[2] == "true"
READINESS = sys.argv[3] if len(sys.argv) > 3 else "ready"
MATTER_CATEGORY = sys.argv[4] if len(sys.argv) > 4 else "development"
from countyiq.assets.enrichment.intelligence_events import _INSERT_SQL, _insert_tuple
from countyiq.lib.llm_harness import HarnessConfig
from countyiq.lib.municipal_matters import build_matter_event, persist_matters
from countyiq.resources.database import make_database_resource

database = make_database_resource()
database.setup_for_execution(None)
with database.dict_cursor() as cur:
    cur.execute(
        "SELECT source FROM public.current_municipal_matter_sources WHERE source->>'candidate_scope' = %s",
        ("property:" + PIDN,),
    )
    source = cur.fetchone()["source"]
records = source["records"]
groups = [records[:-1], records[-1:]] if SPLIT else [records]
matters = []
for members in groups:
    identifiers = [
        identifier for member in members for identifier in member["source_ids"]
    ]
    citations = " ".join(
        "[Evidence:source:" + identifier + "]" for identifier in identifiers
    )
    account = {
        "presentation_language": "en",
        "source_presentations": [
            {"source_id": identifier, "language": "en", "english_text": None}
            for identifier in identifiers
        ],
        "headline": "Board approves store use and parking relief",
        "summary": "The board approved the store's use and parking request. "
        + citations,
        "request": "A store requests use and parking variances. " + citations,
        "why_it_matters": "The relief concerns operating the proposed store with fewer parking spaces. "
        + citations,
        "next_step": None,
        "citations": identifiers,
        "record": {
            "event_type": "approval",
            "event_tags": ["approval"],
            "record_status": "decision",
            "matter_category": MATTER_CATEGORY,
            "decision_scope": None,
            "dates": [],
        },
        "readiness": READINESS,
        "outcome": "approved",
        "outcome_summary": "The board approved the requested relief. " + citations,
        "connection": "The records identify the same store and relief request. "
        + citations
        if len(members) > 1
        else None,
        "conditions": [],
        "history": [
            {
                "record_key": member["key"],
                "record_status": "decision"
                if member["document_kind"] == "minutes"
                else "proposed",
                "summary": "The record addresses the store request. [Evidence:source:"
                + member["source_ids"][0]
                + "]",
            }
            for member in members
        ],
    }
    matters.append(
        {"record_keys": [member["key"] for member in members], "account": account}
    )
result = persist_matters(
    database, source, {"matters": matters}, HarnessConfig(model_path="test-model")
)
assert result.accepted
with database.dict_cursor() as cur:
    cur.execute(
        "SELECT * FROM public.current_municipal_matter_accounts WHERE bundle_key=%s",
        (source["subject_key"],),
    )
    events = [build_matter_event(dict(row)) for row in cur.fetchall()]
with database.transaction() as cur:
    for event in events:
        cur.execute(
            "DELETE FROM public.intelligence_events WHERE event_key=%s",
            (event["event_key"],),
        )
        cur.execute(_INSERT_SQL, _insert_tuple(event))
database.teardown_after_execution(None)
print(json.dumps([event["event_key"] for event in events]))
