"""Synthetic attribution cases only; transaction rolled back after each test."""
import os
import psycopg2
from psycopg2.extras import Json
import pytest

pytestmark=pytest.mark.integration
BODY="West Manchester Twp Planning Commission"

@pytest.fixture
def cur():
    c=psycopg2.connect(os.environ.get("TEST_DATABASE_URL","postgresql://dagster_admin:localtest@localhost:5433/countyiq_test"))
    assert c.info.dbname=="countyiq_test"
    try:
        with c.cursor() as q:
            q.execute("UPDATE meta.municipality_source_rights SET derived_product_allowed=TRUE WHERE body_name=%s",(BODY,))
            for pidn,address,muni in [
                ("99000AA000100","ORWIG RD","WEST MANCHESTER TWP"),
                ("99000AA000200","ORWIG RD","WEST MANCHESTER TWP"),
                ("99000AA000300","123 N MAIN ST","WEST MANCHESTER TWP"),
                ("99000AA000400","127 N WEST ST","WEST MANCHESTER TWP"),
                ("99000AA000500","127 N WEST ST","WEST MANCHESTER TWP"),
                ("99000AA000600","123 N MAIN ST","YORK CITY"),
            ]:
                q.execute("INSERT INTO staging.parcels(pidn,propadr,municipality) VALUES (%s,%s,%s)",(pidn,address,muni))
            yield q
    finally:
        c.rollback()
        c.close()

def matches(cur,refs):
    cur.execute("SELECT pidn,match_method FROM public.proceeding_parcel_matches(%s::jsonb,%s) ORDER BY pidn",(Json(refs),BODY))
    return cur.fetchall()

@pytest.mark.parametrize("refs", [["Orwig Road"],["North Main Street"],["127 North West Street"],
    ["123-127 North Main Street"],["123 & 127 North Main Street"],["North Main Street and Orwig Road"]])
def test_ambiguous_and_street_only_references_do_not_attach_parcels(cur,refs):
    assert matches(cur,refs)==[]

def test_address_with_city_and_map_annotation_is_specific_and_municipality_scoped(cur):
    assert matches(cur,["123 North Main Street, York PA; Tax Map AA Parcel 3"])==[("99000AA000300","address")]

def test_multiple_explicit_pidns_and_unknown_id(cur):
    assert matches(cur,["99-000-AA-0001.00-00000","99-000-AA-0002.00-00000","99-000-AA-9999.00-00000"])==[
        ("99000AA000100","pidn"),("99000AA000200","pidn")]

def test_explicit_id_in_other_municipality_rejected(cur):
    assert matches(cur,["99-000-AA-0006.00-00000"])==[]

def test_ids_take_precedence_over_incidental_street_addresses(cur):
    assert matches(cur,["99-000-AA-0001.00-00000","123 North Main Street"])==[("99000AA000100","pidn")]


def test_municipal_signal_keeps_structured_id_match_method(cur):
    from countyiq.assets.enrichment.development_signals import _SIGNALS

    cur.execute("""
        INSERT INTO staging.public_proceedings
            (body_name,meeting_date,proceeding_type,raw_text,source_url,content_hash,metadata_quality)
        VALUES (%s,CURRENT_DATE,'planning_commission','Fixture only','https://example.test',
                'structured-method-fixture','{"status":"ready"}') RETURNING id
    """,(BODY,))
    proceeding_id=cur.fetchone()[0]
    cur.execute("""
        INSERT INTO staging.proceeding_extractions
            (proceeding_id,extraction_type,parcel_reference,supporting_text,
             extraction_confidence,model_used,source_url,extraction_details)
        VALUES (%s,'subdivision_plan','Multiple parcels in application','Fixture only',
                0.9,'fixture','https://example.test',%s) RETURNING id
    """,(proceeding_id,Json({"parcel_references":["99000AA000100","99000AA000200"]})))
    extraction_id=cur.fetchone()[0]
    cur.execute(dict(_SIGNALS)["municipal_action"])
    cur.execute("""
        SELECT pidn,evidence->>'match_method' FROM public.development_signals
        WHERE signal_key='municipal_action' AND source_id=%s ORDER BY pidn
    """,(str(extraction_id),))
    assert cur.fetchall()==[("99000AA000100","pidn"),("99000AA000200","pidn")]


@pytest.mark.parametrize("contract_version", [2, 3])
def test_native_projection_persists_spans_and_event_date(cur, contract_version, monkeypatch):
    from contextlib import contextmanager
    from countyiq.assets.enrichment.proceeding_extraction import _write_proceeding_extractions
    from countyiq.lib.intelligence_integrity import record_inference_decision,pass0_semantic_decision
    from countyiq.lib.proceeding_contract import details_for
    from countyiq.lib.intelligence_events import build_development_event
    from countyiq.assets.enrichment.intelligence_events import _INSERT_SQL,_insert_tuple

    class DB:
        @contextmanager
        def transaction(self):
            yield cur
    quote="The board approved Synthetic Applicant LLC application ZHB 2026-99 at 123 North Main Street on July 20, 2026."
    extraction=dict(extraction_type="variance_request", applicant_name="Synthetic Applicant LLC",
        parcel_reference="123 North Main Street",current_zoning=None,proposed_zoning=None,
        decision="approved",conditions=[],event_tags=["approval"],project_name="Synthetic variance",
        related_entities=[],what_happened=quote,why_it_matters=None,what_happens_next=None,
        upcoming_date=None,confidence="high",supporting_text=quote,
        evidence_spans=[dict(quote=quote,fields=["what_happened","decision","application_ids","event_date_text","applicant_name","parcel_references"])],
        record_status="decision",event_date="2026-07-20",event_date_text="July 20, 2026",
        upcoming_date_iso=None,application_ids=["ZHB 2026-99"],project_reference=None,
        parcel_references=["123 North Main Street"],matter_category="minor_property")
    if contract_version == 3:
        from tests.test_proceeding_claims import payload, SOURCE
        from countyiq.lib.proceeding_claims import hydrate_claims
        quote = SOURCE
        wire = payload()
        wire["extractions"][0]["extraction_type"] = "variance_request"
        extraction = hydrate_claims(wire, quote)[0]
    cur.execute("""INSERT INTO staging.public_proceedings(body_name,meeting_date,proceeding_type,raw_text,content_hash,source_url)
                   VALUES (%s,'2026-08-05','planning_commission',%s,'synthetic','https://example.test/synthetic') RETURNING id""",(BODY,quote))
    proceeding_id=cur.fetchone()[0]
    gate=record_inference_decision(DB(),subject_key=f"proceeding:{proceeding_id}",pass_number=0,
        output_kind="proceeding_extraction",decision_key="document",source_hash="synthetic",
        input_hash="synthetic",requested_model="synthetic/test",prompt_version="synthetic",
        payload={"extractions":[extraction]},semantic_decision=pass0_semantic_decision([extraction]))
    _write_proceeding_extractions(DB(),proceeding_id=proceeding_id,extractions=[extraction],
                                 model_used="synthetic/test",inference_id=gate.inference_id)
    cur.execute("SELECT id,extraction_details FROM staging.proceeding_extractions WHERE proceeding_id=%s AND extraction_type='variance_request'",(proceeding_id,))
    extraction_id,details=cur.fetchone()
    assert details==details_for(extraction)
    # The explicit resolution projection must preserve the same fields too.
    from countyiq.lib.intelligence_resolution import _project_proceeding
    _project_proceeding(cur, {"subject_key": f"proceeding:{proceeding_id}"},
                       {"requested_model": "synthetic/test"}, {"extractions": [extraction]},
                       gate.inference_id)
    cur.execute("SELECT id,extraction_details FROM staging.proceeding_extractions WHERE proceeding_id=%s AND extraction_type='variance_request'", (proceeding_id,))
    extraction_id, details = cur.fetchone()
    assert details == details_for(extraction)
    event=build_development_event(dict(id=extraction_id,proceeding_id=proceeding_id,body_name=BODY,
        meeting_date="2026-08-05",extracted_at="2026-08-06T00:00:00Z",extraction_details=details,**extraction))
    cur.execute(_INSERT_SQL,_insert_tuple(event))
    cur.execute("SELECT event_date,source_evidence FROM public.intelligence_events WHERE event_key=%s",(event["event_key"],))
    event_date,evidence=cur.fetchone()
    assert event_date.isoformat()=="2026-07-20"
    assert evidence[0]["details"]["record_status"]=="decision"
    assert evidence[0]["excerpt"]==quote
    if contract_version == 3:
        assert evidence[0]["details"]["decision_scope"] == "bond"
        assert evidence[0]["details"]["discovery_eligible"] is False
        assert len(evidence[0]["details"]["milestones"]) == 2
        assert "milestone:1" in evidence[0]["details"]["supports"]
        from countyiq.assets.enrichment.development_signals import _SIGNALS
        cur.execute(dict(_SIGNALS)["municipal_action"])
        cur.execute("SELECT count(*) FROM public.development_signals WHERE signal_key='municipal_action' AND source_id=%s", (str(extraction_id),))
        assert cur.fetchone()[0] == 0


def test_county_narrative_context_uses_conservative_attribution(cur):
    from countyiq.assets.enrichment.county_narratives import PROCEEDINGS_FOR_PIDNS_QUERY, ZHB_DECISIONS_QUERY
    cur.execute("""
        INSERT INTO staging.public_proceedings
            (body_name,meeting_date,proceeding_type,raw_text,source_url,content_hash)
        VALUES (%s,CURRENT_DATE,'planning_commission','Fixture only',
                'https://example.test/narrative','narrative-fixture') RETURNING id
    """, (BODY,))
    proceeding_id = cur.fetchone()[0]
    for reference, decision in [("Orwig Road", "denied"), ("123 North Main Street", "approved")]:
        cur.execute("""
            INSERT INTO staging.proceeding_extractions
                (proceeding_id,extraction_type,parcel_reference,decision,supporting_text,
                 extraction_confidence,model_used,extraction_details)
            VALUES (%s,'zoning_change',%s,%s,'Fixture only',0.9,'fixture',%s)
        """, (proceeding_id, reference, decision, Json({"parcel_references": [reference]})))
    cur.execute(PROCEEDINGS_FOR_PIDNS_QUERY, {"pidns": ["99000AA000100", "99000AA000300"]})
    assert [row[2] for row in cur.fetchall()] == ["approved"]
    cur.execute(ZHB_DECISIONS_QUERY, {"municipality": "WEST MANCHESTER TWP"})
    assert cur.fetchall() == [("approved", 1)]


def test_structured_only_event_retains_more_than_twenty_explicit_parcels(cur):
    from countyiq.assets.enrichment.intelligence_events import _DEVELOPMENT_EVENTS_SQL
    from countyiq.assets.enrichment.development_signals import _SIGNALS
    pidns=[f"99000AB{i:05d}" for i in range(21)]
    for pidn in pidns:
        cur.execute("INSERT INTO staging.parcels(pidn,propadr,municipality) VALUES (%s,'FIXTURE RD','WEST MANCHESTER TWP')",(pidn,))
    cur.execute("UPDATE meta.source_rights SET rights_status='conditional',derived_product_allowed=TRUE,review_due_on=CURRENT_DATE+30 WHERE source_key='public_proceedings'")
    cur.execute("UPDATE meta.municipality_source_rights SET rights_status='conditional',review_due_on=CURRENT_DATE+30 WHERE body_name=%s",(BODY,))
    cur.execute("""
        INSERT INTO staging.public_proceedings
            (body_name,meeting_date,proceeding_type,raw_text,source_url,content_hash,metadata_quality)
        VALUES (%s,CURRENT_DATE,'planning_commission','Fixture only','https://example.test',
                'structured-only-many-parcels','{"status":"ready"}') RETURNING id
    """,(BODY,))
    proceeding_id=cur.fetchone()[0]
    cur.execute("""
        INSERT INTO staging.proceeding_extractions
            (proceeding_id,extraction_type,parcel_reference,supporting_text,
             extraction_confidence,model_used,extraction_details)
        VALUES (%s,'subdivision_plan',NULL,'Fixture only',0.9,'fixture',%s) RETURNING id
    """,(proceeding_id,Json({"parcel_references":pidns})))
    extraction_id=cur.fetchone()[0]
    cur.execute(_DEVELOPMENT_EVENTS_SQL)
    columns=[column.name for column in cur.description]
    event=next(dict(zip(columns,row)) for row in cur.fetchall() if row[0]==extraction_id)
    assert event['related_pidns']==pidns
    cur.execute(dict(_SIGNALS)['municipal_action'])
    cur.execute("SELECT pidn FROM public.development_signals WHERE signal_key='municipal_action' AND source_id=%s ORDER BY pidn",(str(extraction_id),))
    assert [row[0] for row in cur.fetchall()]==pidns
