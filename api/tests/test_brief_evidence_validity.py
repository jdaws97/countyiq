"""Cached narratives cannot outlive their directly cited validated signals."""
import psycopg2
import pytest
from api.tests.conftest import DB_ENV, TEST_PIDN, _bind_contract_brief_versions, _contract_owner_context_ref, _contract_brief_payload

@pytest.fixture(autouse=True)
def isolated_read_limit(monkeypatch):
    from api.lib import rate_limit
    monkeypatch.setattr(rate_limit, "sensitive_read_limiter",
                        rate_limit.PerClientRateLimiter(rate_per_minute=30, burst=10))


@pytest.mark.parametrize("state", ["rejected", "missing"])
def test_cached_briefs_hide_when_cited_signal_is_unavailable(client, state):
    parcel_url = f"/api/parcels/{TEST_PIDN}"
    with psycopg2.connect(DB_ENV["DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT owner_id FROM public.owners WHERE canonical_name='Alpha Holdings LLC'")
            owner_id = cursor.fetchone()[0]
    owner_url = f"/api/owners/{owner_id}"
    baseline = client.get(parcel_url)
    assert baseline.status_code == 200, baseline.text
    assert baseline.json()["parcel_brief"]
    assert client.get(owner_url).json()["brief"]
    with psycopg2.connect(DB_ENV["DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT validation_status FROM public.evidence WHERE pidn=%s AND signal_key='growth_area'", (TEST_PIDN,))
            previous = cursor.fetchone()[0]
            if state == "missing":
                cursor.execute("UPDATE public.evidence SET signal_key='review_temporarily_unavailable' WHERE pidn=%s AND signal_key='growth_area'", (TEST_PIDN,))
            else:
                cursor.execute("UPDATE public.evidence SET validation_status='rejected' WHERE pidn=%s AND signal_key='growth_area'", (TEST_PIDN,))
    try:
        parcel = client.get(parcel_url)
        owner = client.get(owner_url)
        assert parcel.status_code == owner.status_code == 200
        assert parcel.json()["parcel_brief"] is None
        assert owner.json()["brief"] is None
    finally:
        with psycopg2.connect(DB_ENV["DATABASE_URL"]) as connection:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE public.evidence SET signal_key='growth_area',validation_status=%s WHERE pidn=%s AND signal_key=%s",
                               (previous, TEST_PIDN, "review_temporarily_unavailable" if state == "missing" else "growth_area"))
    assert client.get(parcel_url).json()["parcel_brief"]
    assert client.get(owner_url).json()["brief"]


@pytest.mark.parametrize("state", ["paused", "retired", "unreviewed", "replaced", "retracted", "internal", "quarantined_extraction", "wrong_extraction_kind", "wrong_extraction_subject", "wrong_signal_kind", "wrong_signal_subject"])
def test_cached_briefs_follow_recorded_proceeding_dependencies(client, state):
    from psycopg2.extras import Json

    def insert_history(cursor, refs, *, kind='signal_validation', disposition='accepted', subject=TEST_PIDN):
        cursor.execute("""
            INSERT INTO meta.intelligence_inference_history
                (subject_key,pass_number,output_kind,decision_key,source_hash,
                 input_hash,requested_model,prompt_version,output_hash,
                 decision_fingerprint,payload,evidence_refs,disposition)
            VALUES (%s,%s,%s,'provenance-test','test','test',
                    'fixture','fixture','test','test','{}',%s,%s)
            RETURNING inference_id
        """, (subject, 0 if kind == "proceeding_extraction" else 2, kind, Json(refs), disposition))
        return cursor.fetchone()[0]

    with psycopg2.connect(DB_ENV["DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT owner_id FROM public.owners WHERE canonical_name='Alpha Holdings LLC'")
            owner_id = cursor.fetchone()[0]
            cursor.execute("""
                SELECT pe.id,pp.id,pe.active_inference_id,pe.extraction_type,
                       pp.valid_to,pp.metadata_quality
                FROM staging.proceeding_extractions pe
                JOIN staging.public_proceedings pp ON pp.id=pe.proceeding_id
                WHERE pp.body_name='Hanover Borough Council' ORDER BY pe.id LIMIT 1
            """)
            extraction_id, proceeding_id, prior_extraction_inference, extraction_type, valid_to, quality = cursor.fetchone()
            cursor.execute("SELECT active_inference_id FROM public.evidence WHERE pidn=%s AND signal_key='growth_area'", (TEST_PIDN,))
            prior_signal_inference = cursor.fetchone()[0]
            cursor.execute("SELECT rights_status FROM meta.municipality_source_rights WHERE source_key='hanover_borough_council'")
            policy_status = cursor.fetchone()[0]
            extraction_inference = insert_history(cursor, [], kind='proceeding_extraction', subject=f'proceeding:{proceeding_id}')
            history_id = insert_history(cursor, [
                f"extraction:{extraction_id}", f"proceeding:{proceeding_id}",
                f"inference:{extraction_inference}",
            ])
            cursor.execute("UPDATE staging.proceeding_extractions SET active_inference_id=%s WHERE id=%s", (extraction_inference, extraction_id))
            cursor.execute("UPDATE public.evidence SET active_inference_id=%s WHERE pidn=%s AND signal_key='growth_area'", (history_id, TEST_PIDN))
            _bind_contract_brief_versions(cursor)
    urls = [(f"/api/parcels/{TEST_PIDN}", "parcel_brief"), (f"/api/owners/{owner_id}", "brief")]
    try:
        for url, key in urls:
            baseline = client.get(url)
            assert baseline.status_code == 200, baseline.text
            assert baseline.json()[key]
        with psycopg2.connect(DB_ENV["DATABASE_URL"]) as connection:
            with connection.cursor() as cursor:
                if state == "paused":
                    cursor.execute("UPDATE meta.municipality_source_rights SET rights_status='paused' WHERE source_key='hanover_borough_council'")
                elif state == "retired":
                    cursor.execute("UPDATE staging.public_proceedings SET valid_to=NOW() WHERE id=%s", (proceeding_id,))
                elif state == "unreviewed":
                    cursor.execute("UPDATE staging.public_proceedings SET metadata_quality=%s WHERE id=%s", (Json({"status":"unreviewed"}), proceeding_id))
                elif state == "retracted":
                    cursor.execute("UPDATE staging.proceeding_extractions SET active_inference_id=NULL WHERE id=%s", (extraction_id,))
                elif state == "replaced":
                    replacement = insert_history(cursor, [])
                    cursor.execute("UPDATE staging.proceeding_extractions SET active_inference_id=%s WHERE id=%s", (replacement, extraction_id))
                elif state in {"quarantined_extraction", "wrong_extraction_kind", "wrong_extraction_subject", "wrong_signal_kind", "wrong_signal_subject"}:
                    replacement = insert_history(
                        cursor, [],
                        kind="entity_verification" if state == "wrong_extraction_kind" else "proceeding_extraction",
                        disposition="quarantined" if state == "quarantined_extraction" else "accepted",
                        subject="proceeding:unrelated" if state == "wrong_extraction_subject" else f"proceeding:{proceeding_id}",
                    )
                    # Deliberately keep recorded references and projection IDs
                    # consistent: identity equality alone must not authorize use.
                    replacement_signal = insert_history(
                        cursor, [f"extraction:{extraction_id}", f"proceeding:{proceeding_id}", f"inference:{replacement}"],
                        kind="entity_verification" if state == "wrong_signal_kind" else "signal_validation",
                        subject="unrelated-parcel" if state == "wrong_signal_subject" else TEST_PIDN,
                    )
                    cursor.execute("UPDATE staging.proceeding_extractions SET active_inference_id=%s WHERE id=%s", (replacement, extraction_id))
                    cursor.execute("UPDATE public.evidence SET active_inference_id=%s WHERE pidn=%s AND signal_key='growth_area'", (replacement_signal, TEST_PIDN))
                    _bind_contract_brief_versions(cursor)
                else:
                    cursor.execute("UPDATE staging.proceeding_extractions SET extraction_type='_review' WHERE id=%s", (extraction_id,))
        for url, key in urls:
            response = client.get(url)
            assert response.status_code == 200, response.text
            assert response.json()[key] is None
    finally:
        with psycopg2.connect(DB_ENV["DATABASE_URL"]) as connection:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE public.evidence SET active_inference_id=%s WHERE pidn=%s AND signal_key='growth_area'", (prior_signal_inference, TEST_PIDN))
                cursor.execute("UPDATE staging.proceeding_extractions SET active_inference_id=%s,extraction_type=%s WHERE id=%s", (prior_extraction_inference,extraction_type,extraction_id))
                cursor.execute("UPDATE staging.public_proceedings SET valid_to=%s,metadata_quality=%s WHERE id=%s", (valid_to,Json(quality),proceeding_id))
                cursor.execute("UPDATE meta.municipality_source_rights SET rights_status=%s WHERE source_key='hanover_borough_council'", (policy_status,))
                _bind_contract_brief_versions(cursor)
    for url, key in urls:
        assert client.get(url).json()[key]


def test_briefs_bind_original_signal_version_even_when_key_and_text_match(client):
    import hashlib
    owner_subject = "owner_brief:" + hashlib.sha256(b"Alpha Holdings LLC").hexdigest()[:20]
    from psycopg2.extras import Json

    with psycopg2.connect(DB_ENV["DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT owner_id FROM public.owners WHERE canonical_name='Alpha Holdings LLC'")
            owner_id = cursor.fetchone()[0]
            cursor.execute("SELECT active_inference_id FROM public.evidence WHERE pidn=%s AND signal_key='growth_area'", (TEST_PIDN,))
            original_signal = cursor.fetchone()[0]
            cursor.execute("SELECT active_inference_id FROM public.parcel_briefs WHERE pidn=%s", (TEST_PIDN,))
            original_parcel = cursor.fetchone()[0]
            cursor.execute("SELECT active_inference_id FROM public.owner_briefs WHERE canonical_name='Alpha Holdings LLC'")
            original_owner = cursor.fetchone()[0]
            ids = []
            for kind in ("signal_validation", "signal_validation", "parcel_brief", "owner_brief"):
                refs = [f"signal-version:{TEST_PIDN}:growth_area:{ids[0]}"] if len(ids) >= 2 else []
                if kind == "owner_brief":
                    refs.append(_contract_owner_context_ref(cursor))
                elif kind == "parcel_brief":
                    cursor.execute("SELECT meta.parcel_brief_source_fingerprint(%s)", (TEST_PIDN,))
                    refs.append("parcel-context:v1:" + cursor.fetchone()[0])
                cursor.execute("""
                    INSERT INTO meta.intelligence_inference_history
                        (subject_key,pass_number,output_kind,decision_key,source_hash,
                         input_hash,requested_model,prompt_version,output_hash,
                         decision_fingerprint,payload,evidence_refs,disposition)
                    VALUES (%s,%s,%s,'version-test','same','same','fixture','fixture',
                            'same','same',%s,%s,'accepted')
                    RETURNING inference_id
                """, (owner_subject if kind == "owner_brief" else TEST_PIDN, 2 if kind == "signal_validation" else 3, kind, Json(_contract_brief_payload(cursor, kind) if kind.endswith("brief") else {}), Json(refs)))
                ids.append(cursor.fetchone()[0])
            cursor.execute("UPDATE public.evidence SET active_inference_id=%s WHERE pidn=%s AND signal_key='growth_area'", (ids[0],TEST_PIDN))
            cursor.execute("UPDATE public.parcel_briefs SET active_inference_id=%s WHERE pidn=%s", (ids[2],TEST_PIDN))
            cursor.execute("UPDATE public.owner_briefs SET active_inference_id=%s WHERE canonical_name='Alpha Holdings LLC'", (ids[3],))
    urls = [(f"/api/parcels/{TEST_PIDN}", "parcel_brief"), (f"/api/owners/{owner_id}", "brief")]
    try:
        for url, key in urls:
            response = client.get(url)
            assert response.status_code == 200, response.text
            assert response.json()[key]
        with psycopg2.connect(DB_ENV["DATABASE_URL"]) as connection:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE public.evidence SET active_inference_id=%s WHERE pidn=%s AND signal_key='growth_area'", (ids[1],TEST_PIDN))
        for url, key in urls:
            response = client.get(url)
            assert response.status_code == 200, response.text
            assert response.json()[key] is None
    finally:
        with psycopg2.connect(DB_ENV["DATABASE_URL"]) as connection:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE public.evidence SET active_inference_id=%s WHERE pidn=%s AND signal_key='growth_area'", (original_signal,TEST_PIDN))
                cursor.execute("UPDATE public.parcel_briefs SET active_inference_id=%s WHERE pidn=%s", (original_parcel,TEST_PIDN))
                cursor.execute("UPDATE public.owner_briefs SET active_inference_id=%s WHERE canonical_name='Alpha Holdings LLC'", (original_owner,))


@pytest.mark.parametrize("state", ["missing_history", "empty_refs", "signal_keys_only"])
def test_legacy_briefs_are_retained_but_not_served(client, state):
    import hashlib
    owner_subject = "owner_brief:" + hashlib.sha256(b"Alpha Holdings LLC").hexdigest()[:20]
    from psycopg2.extras import Json

    originals = {}
    with psycopg2.connect(DB_ENV["DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT owner_id FROM public.owners WHERE canonical_name='Alpha Holdings LLC'")
            owner_id = cursor.fetchone()[0]
            for table, kind in (("parcel_briefs", "parcel_brief"), ("owner_briefs", "owner_brief")):
                cursor.execute(f"SELECT active_inference_id,brief_text FROM public.{table}")
                originals[table] = cursor.fetchone()
                legacy_id = None
                if state != "missing_history":
                    refs = ["signal:growth_area"] if state == "signal_keys_only" else []
                    if kind == "owner_brief":
                        refs.append(_contract_owner_context_ref(cursor))
                    else:
                        cursor.execute("SELECT meta.parcel_brief_source_fingerprint(%s)", (TEST_PIDN,))
                        refs.append("parcel-context:v1:" + cursor.fetchone()[0])
                    cursor.execute("""
                        INSERT INTO meta.intelligence_inference_history
                          (subject_key,pass_number,output_kind,decision_key,source_hash,input_hash,
                           requested_model,prompt_version,output_hash,decision_fingerprint,
                           payload,evidence_refs,disposition)
                        VALUES (%s,3,%s,'legacy-test','fixture','fixture','fixture',
                                'fixture','fixture','fixture','{}',%s,'accepted')
                        RETURNING inference_id
                    """, (owner_subject if kind == "owner_brief" else TEST_PIDN,kind,Json(refs)))
                    legacy_id = cursor.fetchone()[0]
                cursor.execute(f"UPDATE public.{table} SET active_inference_id=%s", (legacy_id,))
    try:
        for url, key in ((f"/api/parcels/{TEST_PIDN}", "parcel_brief"), (f"/api/owners/{owner_id}", "brief")):
            response = client.get(url)
            assert response.status_code == 200, response.text
            assert response.json()[key] is None
        with psycopg2.connect(DB_ENV["DATABASE_URL"]) as connection:
            with connection.cursor() as cursor:
                for table, (_, original_text) in originals.items():
                    cursor.execute(f"SELECT brief_text FROM public.{table}")
                    assert cursor.fetchone()[0] == original_text
    finally:
        with psycopg2.connect(DB_ENV["DATABASE_URL"]) as connection:
            with connection.cursor() as cursor:
                for table, (original_id, _) in originals.items():
                    cursor.execute(f"UPDATE public.{table} SET active_inference_id=%s", (original_id,))
    assert client.get(f"/api/parcels/{TEST_PIDN}").json()["parcel_brief"]
    assert client.get(f"/api/owners/{owner_id}").json()["brief"]


@pytest.mark.parametrize("table,key", [("parcel_briefs","parcel_brief"), ("owner_briefs","brief")])
@pytest.mark.parametrize("mismatch", ["subject", "kind"])
def test_brief_history_must_describe_this_output(client, table, key, mismatch):
    with psycopg2.connect(DB_ENV["DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT owner_id FROM public.owners WHERE canonical_name='Alpha Holdings LLC'")
            owner_id = cursor.fetchone()[0]
            cursor.execute(f"SELECT active_inference_id FROM public.{table}")
            original_id = cursor.fetchone()[0]
            cursor.execute("""
                INSERT INTO meta.intelligence_inference_history
                  (subject_key,pass_number,output_kind,decision_key,source_hash,input_hash,
                   requested_model,prompt_version,output_hash,decision_fingerprint,
                   payload,evidence_refs,disposition)
                SELECT CASE WHEN %s='subject' THEN 'unrelated-subject' ELSE subject_key END,
                       pass_number,
                       CASE WHEN %s='kind' THEN
                         CASE WHEN output_kind='parcel_brief' THEN 'owner_brief' ELSE 'parcel_brief' END
                         ELSE output_kind END,
                       decision_key,source_hash,input_hash,requested_model,prompt_version,
                       output_hash,decision_fingerprint,payload,evidence_refs,disposition
                FROM meta.intelligence_inference_history WHERE inference_id=%s
                RETURNING inference_id
            """, (mismatch,mismatch,original_id))
            wrong_id = cursor.fetchone()[0]
            cursor.execute(f"UPDATE public.{table} SET active_inference_id=%s", (wrong_id,))
    url = f"/api/parcels/{TEST_PIDN}" if table == "parcel_briefs" else f"/api/owners/{owner_id}"
    try:
        response = client.get(url)
        assert response.status_code == 200, response.text
        assert response.json()[key] is None
    finally:
        with psycopg2.connect(DB_ENV["DATABASE_URL"]) as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"UPDATE public.{table} SET active_inference_id=%s", (original_id,))
    assert client.get(url).json()[key]


@pytest.mark.parametrize("change", ["entity_type", "membership", "count"])
def test_owner_brief_expires_when_owner_context_changes(client, change):
    with psycopg2.connect(DB_ENV["DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT owner_id,entity_type FROM public.owners WHERE canonical_name='Alpha Holdings LLC'")
            owner_id, original_type = cursor.fetchone()
    url = f"/api/owners/{owner_id}"
    assert client.get(url).json()["brief"]
    with psycopg2.connect(DB_ENV["DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            if change == "entity_type":
                cursor.execute("UPDATE public.owners SET entity_type='trust' WHERE owner_id=%s", (owner_id,))
            elif change == "membership":
                # Same portfolio size, same signal IDs, different owned parcel.
                cursor.execute("UPDATE public.owner_source_links SET source_id='review-other-parcel' WHERE owner_id=%s AND source_type='parcel' AND source_id=%s", (owner_id,TEST_PIDN))
            else:
                cursor.execute("""
                    INSERT INTO public.owner_source_links
                      (owner_id,source_type,source_id,source_name,confidence,match_tier)
                    VALUES (%s,'parcel','review-other-parcel','Alpha Holdings LLC',1.0,'exact_name')
                """, (owner_id,))
    try:
        response = client.get(url)
        assert response.status_code == 200, response.text
        assert response.json()["brief"] is None
        # Changing the owner's portfolio does not revoke the property's own brief.
        assert client.get(f"/api/parcels/{TEST_PIDN}").json()["parcel_brief"]
    finally:
        with psycopg2.connect(DB_ENV["DATABASE_URL"]) as connection:
            with connection.cursor() as cursor:
                if change == "entity_type":
                    cursor.execute("UPDATE public.owners SET entity_type=%s WHERE owner_id=%s", (original_type,owner_id))
                elif change == "membership":
                    cursor.execute("UPDATE public.owner_source_links SET source_id=%s WHERE owner_id=%s AND source_type='parcel' AND source_id='review-other-parcel'", (TEST_PIDN,owner_id))
                else:
                    cursor.execute("DELETE FROM public.owner_source_links WHERE owner_id=%s AND source_type='parcel' AND source_id='review-other-parcel'", (owner_id,))
    assert client.get(url).json()["brief"]


def test_owner_brief_expires_when_signal_parcel_municipality_is_corrected(client):
    with psycopg2.connect(DB_ENV["DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT owner_id FROM public.owners WHERE canonical_name='Alpha Holdings LLC'")
            owner_id = cursor.fetchone()[0]
            cursor.execute("SELECT municipality FROM staging.parcels WHERE pidn=%s AND valid_to IS NULL", (TEST_PIDN,))
            municipality = cursor.fetchone()[0]
    url = f"/api/owners/{owner_id}"
    assert client.get(url).json()["brief"]
    with psycopg2.connect(DB_ENV["DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE staging.parcels SET municipality='Corrected fixture municipality' WHERE pidn=%s AND valid_to IS NULL", (TEST_PIDN,))
    try:
        response = client.get(url)
        assert response.status_code == 200, response.text
        assert response.json()["brief"] is None
    finally:
        with psycopg2.connect(DB_ENV["DATABASE_URL"]) as connection:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE staging.parcels SET municipality=%s WHERE pidn=%s AND valid_to IS NULL", (municipality,TEST_PIDN))
    assert client.get(url).json()["brief"]


@pytest.mark.parametrize("source", ["property", "entity", "aliases", "portfolio", "tax"])
def test_parcel_brief_expires_when_non_signal_context_changes(client, source):
    from api.tests.conftest import SECOND_PIDN
    cases = {
        "property": (
            "SELECT aprtotal FROM staging.parcels WHERE pidn=%s AND valid_to IS NULL",
            "UPDATE staging.parcels SET aprtotal=%s WHERE pidn=%s AND valid_to IS NULL",
            TEST_PIDN, 987654,
        ),
        "entity": (
            "SELECT entity_type FROM public.entity_graph WHERE canonical_name=%s",
            "UPDATE public.entity_graph SET entity_type=%s WHERE canonical_name=%s",
            "Alpha Holdings LLC", "trust",
        ),
        "aliases": (
            "SELECT aliases FROM public.owners WHERE canonical_name=%s",
            "UPDATE public.owners SET aliases=%s WHERE canonical_name=%s",
            "Alpha Holdings LLC", ["Alpha Holdings LLC", "Beta Investments LLC"],
        ),
        "portfolio": (
            "SELECT owner_full FROM staging.parcels WHERE pidn=%s AND valid_to IS NULL",
            "UPDATE staging.parcels SET owner_full=%s WHERE pidn=%s AND valid_to IS NULL",
            SECOND_PIDN, "Alpha Holdings LLC",
        ),
        "tax": (
            "SELECT total FROM staging.tax_claims WHERE pidn=%s AND valid_to IS NULL",
            "UPDATE staging.tax_claims SET total=%s WHERE pidn=%s AND valid_to IS NULL",
            TEST_PIDN, 9876,
        ),
    }
    select, update, subject, changed = cases[source]
    url = f"/api/parcels/{TEST_PIDN}"
    assert client.get(url).json()["parcel_brief"]
    with psycopg2.connect(DB_ENV["DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            cursor.execute(select, (subject,))
            original = cursor.fetchone()[0]
            cursor.execute(update, (changed,subject))
    try:
        response = client.get(url)
        assert response.status_code == 200, response.text
        assert response.json()["parcel_brief"] is None
    finally:
        with psycopg2.connect(DB_ENV["DATABASE_URL"]) as connection:
            with connection.cursor() as cursor:
                cursor.execute(update, (original,subject))
    assert client.get(url).json()["parcel_brief"]


def test_briefs_hide_when_supporting_signal_has_no_validation_history(client):
    with psycopg2.connect(DB_ENV["DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT owner_id FROM public.owners WHERE canonical_name='Alpha Holdings LLC'")
            owner_id=cursor.fetchone()[0]
            cursor.execute("SELECT active_inference_id FROM public.evidence WHERE pidn=%s AND signal_key='growth_area'",(TEST_PIDN,))
            original=cursor.fetchone()[0]
    urls=[(f"/api/parcels/{TEST_PIDN}",'parcel_brief'),(f"/api/owners/{owner_id}",'brief')]
    for url,field in urls:
        response=client.get(url)
        assert response.status_code==200,response.text
        assert response.json()[field]
    with psycopg2.connect(DB_ENV["DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE public.evidence SET active_inference_id=NULL WHERE pidn=%s AND signal_key='growth_area'",(TEST_PIDN,))
    try:
        for url,field in urls:
            response=client.get(url)
            assert response.status_code==200,response.text
            assert response.json()[field] is None
        with psycopg2.connect(DB_ENV["DATABASE_URL"]) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT brief_text FROM public.parcel_briefs WHERE pidn=%s",(TEST_PIDN,))
                assert cursor.fetchone()[0]
                cursor.execute("SELECT validation_status FROM public.evidence WHERE pidn=%s AND signal_key='growth_area'",(TEST_PIDN,))
                assert cursor.fetchone()[0] in ('confirmed','upgraded','downgraded')
    finally:
        with psycopg2.connect(DB_ENV["DATABASE_URL"]) as connection:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE public.evidence SET active_inference_id=%s WHERE pidn=%s AND signal_key='growth_area'",(original,TEST_PIDN))
    for url,field in urls:
        assert client.get(url).json()[field]


@pytest.mark.parametrize("change",["missing_signal","missing_history","changed_status","changed_summary","changed_input"])
def test_cross_signal_summary_requires_current_accepted_validation_set(client, change):
    url=f"/api/parcels/{TEST_PIDN}"
    baseline=client.get(url)
    assert baseline.status_code==200,baseline.text
    assert baseline.json()['intelligence_summary']['cross_signal_insight']
    with psycopg2.connect(DB_ENV['DATABASE_URL']) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT active_inference_id,validation_status FROM public.evidence WHERE pidn=%s AND signal_key='growth_area'",(TEST_PIDN,))
            signal=cursor.fetchone()
            cursor.execute("SELECT cross_signal_insight,input_hash FROM meta.intelligence_passes WHERE pidn=%s AND pass_number=2",(TEST_PIDN,))
            summary=cursor.fetchone()
            if change=='missing_signal':
                cursor.execute("UPDATE public.evidence SET signal_key='review_removed_growth' WHERE pidn=%s AND signal_key='growth_area'",(TEST_PIDN,))
            elif change=='missing_history':
                cursor.execute("UPDATE public.evidence SET active_inference_id=NULL WHERE pidn=%s AND signal_key='growth_area'",(TEST_PIDN,))
            elif change=='changed_status':
                cursor.execute("UPDATE public.evidence SET validation_status='rejected' WHERE pidn=%s AND signal_key='growth_area'",(TEST_PIDN,))
            elif change=='changed_summary':
                cursor.execute("UPDATE meta.intelligence_passes SET cross_signal_insight='Unbound review text' WHERE pidn=%s AND pass_number=2",(TEST_PIDN,))
            else:
                cursor.execute("UPDATE meta.intelligence_passes SET input_hash='different-input' WHERE pidn=%s AND pass_number=2",(TEST_PIDN,))
    try:
        response=client.get(url)
        assert response.status_code==200,response.text
        assert response.json()['intelligence_summary'] is None
    finally:
        with psycopg2.connect(DB_ENV['DATABASE_URL']) as connection:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE public.evidence SET signal_key='growth_area',active_inference_id=%s,validation_status=%s WHERE pidn=%s AND signal_key=%s",(*signal,TEST_PIDN,'review_removed_growth' if change=='missing_signal' else 'growth_area'))
                cursor.execute("UPDATE meta.intelligence_passes SET cross_signal_insight=%s,input_hash=%s WHERE pidn=%s AND pass_number=2",(*summary,TEST_PIDN))
    assert client.get(url).json()['intelligence_summary']==baseline.json()['intelligence_summary']


@pytest.mark.parametrize("table,field,key", [
    ("parcel_briefs", "brief_text", "parcel_brief"),
    ("parcel_briefs", "assessment_reasoning", "parcel_brief"),
    ("owner_briefs", "brief_text", "brief"),
    ("owner_briefs", "concentration_notes", "brief"),
])
def test_cached_claims_must_match_accepted_output(client, table, field, key):
    from psycopg2 import sql
    with psycopg2.connect(DB_ENV["DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT owner_id FROM public.owners WHERE canonical_name='Alpha Holdings LLC'")
            owner_id = cursor.fetchone()[0]
            query = sql.SQL("SELECT {} FROM public.{}").format(sql.Identifier(field), sql.Identifier(table))
            cursor.execute(query)
            original = cursor.fetchone()[0]
    url = f"/api/parcels/{TEST_PIDN}" if table == "parcel_briefs" else f"/api/owners/{owner_id}"
    assert client.get(url).json()[key]
    update = sql.SQL("UPDATE public.{} SET {}=%s").format(sql.Identifier(table), sql.Identifier(field))
    try:
        with psycopg2.connect(DB_ENV["DATABASE_URL"]) as connection:
            with connection.cursor() as cursor:
                cursor.execute(update, ("Changed claim absent from accepted inference",))
        response = client.get(url)
        assert response.status_code == 200
        assert response.json()[key] is None
    finally:
        with psycopg2.connect(DB_ENV["DATABASE_URL"]) as connection:
            with connection.cursor() as cursor:
                cursor.execute(update, (original,))
    assert client.get(url).json()[key]
