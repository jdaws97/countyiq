"""Cleanup transaction tests against the isolated countyiq_test database only."""
from datetime import date
import os

import psycopg2
from psycopg2.extras import RealDictCursor
import pytest

from countyiq.lib.county_config import CountyConfig
from scripts.review_proceeding_metadata import apply_plan, build_plan

pytestmark = pytest.mark.integration


@pytest.fixture
def db():
    dsn = os.environ.get("TEST_DATABASE_URL",
                        "postgresql://dagster_admin:localtest@localhost:5433/countyiq_test")
    connection = psycopg2.connect(dsn)
    if connection.info.dbname != "countyiq_test":
        connection.close()
        raise RuntimeError("Metadata integration tests require countyiq_test")
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()


def seed(cur, *, wrong=False):
    text = "Hanover Borough Council\nJuly 23, 2026\nRoll call\n" + "Meeting business. " * 40
    source = "https://wrong.test/minutes" if wrong else "https://example.test/minutes"
    cur.execute("""
        INSERT INTO staging.public_proceedings
            (body_name,meeting_date,proceeding_type,source_url,document_url,content_hash,raw_text,valid_from)
        VALUES ('Hanover Borough Council','2026-07-01','council',%s,
                'https://example.test/July_2026.pdf','test-source-bytes',%s,NOW())
        RETURNING *
    """, (source, text))
    return dict(cur.fetchone())


def plan_for(rows, *, baseline=()):
    county = CountyConfig(name="Test County", s3_prefix="test",
        rejected_proceeding_domains=("wrong.test",), municipality_websites=(
            ("Hanover Borough Council", "https://example.test/minutes", "borough_council"),))
    return build_plan(rows, {"hanover_borough_council": dict(
        rights_status="conditional", derived_product_allowed=True, allowed_origins=["https://example.test"],
        review_due_on=date(2026,11,1))}, county, today=date(2026,9,4), baseline=baseline)


def test_correction_versions_metadata_and_preserves_all_source_evidence(db):
    with db.cursor(cursor_factory=RealDictCursor) as cur:
        source = seed(cur)
        plan = plan_for([source])
        assert apply_plan(cur, [source], plan) == 1
        cur.execute("SELECT * FROM staging.public_proceedings WHERE id=%s", (source["id"],))
        old = cur.fetchone()
        assert old["valid_to"] is not None
        for key in ("body_name","meeting_date","proceeding_type","raw_text","source_url",
                    "document_url","content_hash","valid_from"):
            assert old[key] == source[key]
        cur.execute("SELECT * FROM meta.proceeding_metadata_reviews WHERE proceeding_id=%s",
                    (source["id"],))
        audit = cur.fetchone()
        assert audit["action"] == "superseded"
        cur.execute("SELECT * FROM staging.public_proceedings WHERE id=%s", (audit["replacement_id"],))
        new = cur.fetchone()
        assert new["meeting_date"] == date(2026,7,23)
        assert new["metadata_quality"]["status"] == "ready"
        assert new["valid_to"] is None
        for key in ("raw_text","document_url","source_url","content_hash"):
            assert new[key] == source[key]


def test_quarantine_retires_without_replacement_or_content_loss(db):
    with db.cursor(cursor_factory=RealDictCursor) as cur:
        source = seed(cur, wrong=True)
        apply_plan(cur, [source], plan_for([source]))
        cur.execute("SELECT * FROM staging.public_proceedings WHERE id=%s", (source["id"],))
        old = cur.fetchone()
        assert old["raw_text"] == source["raw_text"]
        assert old["meeting_date"] == source["meeting_date"]
        assert old["valid_to"] is not None
        cur.execute("SELECT * FROM meta.proceeding_metadata_reviews WHERE proceeding_id=%s", (source["id"],))
        audit = cur.fetchone()
        assert audit["replacement_id"] is None
        assert audit["review"]["issues"] == ["wrong_jurisdiction_source"]


def test_review_ledger_is_append_only(db):
    with db.cursor(cursor_factory=RealDictCursor) as cur:
        source = seed(cur)
        apply_plan(cur, [source], plan_for([source]))
        cur.execute("SAVEPOINT immutable_check")
        with pytest.raises(psycopg2.Error, match="append-only"):
            cur.execute("UPDATE meta.proceeding_metadata_reviews SET action='annotated' WHERE proceeding_id=%s",
                        (source["id"],))
        cur.execute("ROLLBACK TO SAVEPOINT immutable_check")


def test_rejects_cleanup_with_existing_extractions(db):
    with db.cursor(cursor_factory=RealDictCursor) as cur:
        source = seed(cur)
        cur.execute("""
            INSERT INTO staging.proceeding_extractions
                (proceeding_id,extraction_type,extraction_confidence,model_used,page_number)
            VALUES (%s,'_no_landuse_terms',1,'deterministic-prefilter',0)
        """, (source["id"],))
        with pytest.raises(RuntimeError, match="derived extractions"):
            apply_plan(cur, [source], plan_for([source]))
        cur.execute("SELECT valid_to FROM staging.public_proceedings WHERE id=%s", (source["id"],))
        assert cur.fetchone()["valid_to"] is None


def test_nine_retired_sources_are_paused(db):
    with db.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT source_key,acquisition_allowed,derived_product_allowed,allowed_methods
            FROM meta.municipality_source_rights
            WHERE source_key = ANY(%s)
        """, ([
            "penn_twp_board_of_supervisors","penn_twp_planning_commission","penn_twp_zoning_hearing_board",
            "paradise_twp_board_of_supervisors","paradise_twp_planning_commission","paradise_twp_zoning_hearing_board",
            "windsor_twp_board_of_supervisors","windsor_twp_planning_commission","jackson_twp_board_of_supervisors",
        ],))
        rows = cur.fetchall()
        assert len(rows) == 9
        assert all(not row["acquisition_allowed"] and not row["derived_product_allowed"]
                   and row["allowed_methods"] == [] for row in rows)


def test_later_batch_deduplicates_against_current_reviewed_replacement(db):
    from scripts.review_proceeding_metadata import load_inputs
    with db.cursor(cursor_factory=RealDictCursor) as cur:
        original = seed(cur)
        apply_plan(cur, [original], plan_for([original]))
        cur.execute("SELECT replacement_id FROM meta.proceeding_metadata_reviews WHERE proceeding_id=%s", (original["id"],))
        retained_id = cur.fetchone()["replacement_id"]
        later = seed(cur)
        rows, _, baseline = load_inputs(cur, lock=True)
        assert later["id"] in {row["id"] for row in rows}
        assert retained_id not in {row["id"] for row in rows}
        assert retained_id in {row["id"] for row in baseline}
        plan = plan_for([later], baseline=baseline)
        assert plan["items"][0]["review"]["duplicate_of"] == retained_id
        apply_plan(cur, [later], plan)
        cur.execute("SELECT valid_to FROM staging.public_proceedings WHERE id=%s", (later["id"],))
        assert cur.fetchone()["valid_to"] is not None
        cur.execute("SELECT valid_to FROM staging.public_proceedings WHERE id=%s", (retained_id,))
        assert cur.fetchone()["valid_to"] is None


def test_extraction_query_excludes_future_and_unreviewed_documents(db):
    from psycopg2.extras import Json
    from countyiq.assets.enrichment.proceeding_extraction import PENDING_PROCEEDINGS_QUERY
    with db.cursor(cursor_factory=RealDictCursor) as cur:
        ids = []
        for future, issues, status in [
            (False, [], "ready"),
            (True, [], "ready"),
            (False, ["primary_board_unverified"], "review_required"),
            (False, [], "unreviewed"),
        ]:
            source = seed(cur)
            ids.append(source["id"])
            cur.execute("""
                UPDATE staging.public_proceedings
                SET meeting_date = CURRENT_DATE + %s,
                    metadata_quality = %s
                WHERE id = %s
            """, (1 if future else -1, Json({"status": status, "issues": issues}), source["id"]))
        cur.execute(PENDING_PROCEEDINGS_QUERY)
        selected = {row["id"] for row in cur.fetchall()}
        assert ids[0] in selected
        assert not selected.intersection(ids[1:])


def test_plan_detects_changed_review_annotation_and_preserves_previous_review(db):
    from psycopg2.extras import Json
    from scripts.review_proceeding_metadata import load_inputs

    with db.cursor(cursor_factory=RealDictCursor) as cur:
        source = seed(cur)
        original_plan = plan_for([source])
        prior = {"version": "older-review", "status": "review_required",
                 "issues": ["manual_source_check"], "note": "Confirm board identity"}
        cur.execute("UPDATE staging.public_proceedings SET metadata_quality=%s WHERE id=%s",
                    (Json(prior), source["id"]))
        rows, _, _ = load_inputs(cur, lock=True)
        changed_source = next(row for row in rows if row["id"] == source["id"])
        updated_plan = plan_for([changed_source])
        # main() compares the entire freshly locked plan before applying it.
        assert updated_plan != original_plan
        assert updated_plan["items"][0]["prior_metadata_quality"] == prior
        apply_plan(cur, [changed_source], updated_plan)
        cur.execute("SELECT original_metadata FROM meta.proceeding_metadata_reviews WHERE proceeding_id=%s",
                    (source["id"],))
        assert cur.fetchone()["original_metadata"]["metadata_quality"] == prior
