"""Dry-run and apply deterministic proceedings cleanup, preserving source evidence.

From pipelines/: DATABASE_URL=... .venv/bin/python -m scripts.review_proceeding_metadata
    --plan /path/to/review.json [--apply]

The default writes a reviewable plan. --apply recomputes it against locked current
rows and current source policies and refuses stale plans or affected derivatives.
It never downloads documents, calls an LLM, or deletes evidence.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re

import psycopg2
from psycopg2.extras import Json, RealDictCursor

from countyiq.lib.county_config import get_county_config, municipality_source_key
from countyiq.lib.proceeding_quality import VERSION, review_metadata, source_fingerprint
from countyiq.lib.robots import source_origin

SOURCE_FIELDS = ("body_name", "meeting_date", "proceeding_type", "source_url",
                 "document_url", "content_hash", "raw_text")


def duplicate_identity(body, meeting_date, text):
    normalized = re.sub(r"\s+", " ", text or "").strip()
    return (body, str(meeting_date), hashlib.sha256(normalized.encode()).hexdigest())


def build_plan(rows, policies, county, *, today, baseline=()):
    items = []
    seen = {}
    baseline_receipts = []
    for prior in sorted(baseline, key=lambda row: row["id"]):
        seen.setdefault(duplicate_identity(prior["body_name"], prior["meeting_date"], prior["raw_text"]), prior["id"])
        baseline_receipts.append({"id": prior["id"], "fingerprint": source_fingerprint(prior)})
    for row in rows:
        review = review_metadata(row, county.municipality_websites,
                                 county.rejected_proceeding_domains, today=today)
        if review["status"] != "quarantined":
            policy = policies.get(municipality_source_key(review["body_name"]))
            if not policy or not policy["derived_product_allowed"] or (
                policy["rights_status"] not in ("allowed", "conditional")
            ) or not policy.get("review_due_on") or policy["review_due_on"] < today:
                review["issues"].append("source_policy_not_released")
                review["status"] = "review_required"
            elif any(source_origin(row.get(key) or "") not in set(policy.get("allowed_origins") or [])
                     for key in ("source_url", "document_url")):
                review["issues"].append("source_origin_not_released")
                review["status"] = "review_required"
        # Only exact text duplicates with a verified body/date can be retired.
        # Keep cross-board/cross-date documents distinct, even when text matches.
        if review["status"] == "ready":
            identity = duplicate_identity(review["body_name"], review["meeting_date"], row.get("raw_text"))
            if identity in seen:
                review.update(status="quarantined", issues=["duplicate_document"],
                              duplicate_of=seen[identity])
            else:
                seen[identity] = row["id"]
        original = {key: (str(row[key]) if row.get(key) is not None else None)
                    for key in ("body_name", "meeting_date", "proceeding_type")}
        changed = any(original[key] != review[key] for key in original)
        action = ("quarantined" if review["status"] == "quarantined"
                  else "superseded" if changed else "annotated")
        items.append(dict(id=row["id"], fingerprint=source_fingerprint(row),
                          original=original, prior_metadata_quality=row.get("metadata_quality") or {},
                          review=review, action=action))
    counts = Counter(item["review"]["status"] for item in items)
    issues = Counter(issue for item in items for issue in item["review"]["issues"])
    recent = [item for item in items if item["review"]["status"] == "ready"
              and today.replace(month=1, day=1).isoformat() <= item["review"]["meeting_date"] <= today.isoformat()]
    return dict(version=VERSION, county=county.s3_prefix, as_of=str(today),
                count=len(items), statuses=dict(counts), issues=dict(issues),
                actions=dict(Counter(item["action"] for item in items)),
                ready_recent_count=len(recent), duplicate_baseline=baseline_receipts, items=items)


def load_inputs(cur, *, lock=False):
    cur.execute("""
        SELECT id, body_name, meeting_date, proceeding_type, source_url,
               document_url, content_hash, raw_text, metadata_quality
        FROM staging.public_proceedings
        WHERE valid_to IS NULL
          AND metadata_quality->>'version' IS DISTINCT FROM %s
        ORDER BY id
    """ + (" FOR UPDATE" if lock else ""), (VERSION,))
    rows = list(cur.fetchall())
    cur.execute("""
        SELECT source_key, rights_status, derived_product_allowed, review_due_on, allowed_origins
        FROM meta.municipality_source_rights ORDER BY source_key
    """ + (" FOR SHARE" if lock else ""))
    policies = {r["source_key"]: r for r in cur.fetchall()}
    cur.execute("""
        SELECT id, body_name, meeting_date, proceeding_type, source_url,
               document_url, content_hash, raw_text, metadata_quality
        FROM staging.public_proceedings
        WHERE valid_to IS NULL AND metadata_quality->>'version' = %s
          AND metadata_quality->>'status' = 'ready'
        ORDER BY id
    """ + (" FOR SHARE" if lock else ""), (VERSION,))
    return rows, policies, list(cur.fetchall())


def apply_plan(cur, rows, plan):
    ids = [row["id"] for row in rows]
    cur.execute("""
        SELECT COUNT(*) AS count FROM staging.proceeding_extractions
        WHERE proceeding_id = ANY(%s)
    """, (ids,))
    if cur.fetchone()["count"]:
        raise RuntimeError("Affected proceedings have derived extractions; retract/review them before cleanup.")
    by_id = {row["id"]: row for row in rows}
    for item in plan["items"]:
        row = by_id[item["id"]]
        review = item["review"]
        replacement_id = None
        if item["action"] in ("quarantined", "superseded"):
            cur.execute("""
                UPDATE staging.public_proceedings SET valid_to = NOW()
                WHERE id = %s AND valid_to IS NULL
            """, (row["id"],))
            if cur.rowcount != 1:
                raise RuntimeError("Source changed during cleanup")
        if item["action"] == "superseded":
            replacement = {**row, **{key: review[key] for key in
                           ("body_name", "meeting_date", "proceeding_type")}}
            cur.execute("""
                INSERT INTO staging.public_proceedings
                    (body_name, meeting_date, proceeding_type, source_url,
                     document_url, content_hash, raw_text, metadata_quality, valid_from)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NOW()) RETURNING id
            """, (*[replacement[key] for key in SOURCE_FIELDS],
                  Json({**review, "supersedes_id": row["id"]})))
            replacement_id = cur.fetchone()["id"]
        else:
            # Only derived review annotations change in place; source metadata/text
            # remains untouched. Corrections above always create a new SCD2 version.
            cur.execute("""
                UPDATE staging.public_proceedings SET metadata_quality = %s WHERE id = %s
            """, (Json(review), row["id"]))
        cur.execute("""
            INSERT INTO meta.proceeding_metadata_reviews
                (proceeding_id, replacement_id, review_version, source_fingerprint,
                 original_metadata, review, action)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (row["id"], replacement_id, VERSION, item["fingerprint"],
              Json({**item["original"], "metadata_quality": item["prior_metadata_quality"]}),
              Json(review), item["action"]))
    return len(plan["items"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    county = get_county_config()
    with psycopg2.connect(os.environ["DATABASE_URL"]) as conn:
        conn.set_session(readonly=not args.apply)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if args.apply:
                cur.execute("SELECT pg_advisory_xact_lock(hashtext('proceeding-metadata-review'))")
                expected = json.loads(args.plan.read_text())
                if expected["version"] != VERSION:
                    raise RuntimeError("Plan version is stale; regenerate and review.")
                today = date.fromisoformat(expected["as_of"])
                if today != date.today():
                    raise RuntimeError("Plan date is stale; regenerate and review.")
            else:
                today = date.today()
            rows, policies, baseline = load_inputs(cur, lock=args.apply)
            plan = build_plan(rows, policies, county, today=today, baseline=baseline)
            if args.apply:
                if plan != expected:
                    raise RuntimeError("Source rows or policies changed; regenerate and review the plan.")
                applied = apply_plan(cur, rows, plan)
                print(json.dumps({"applied": applied, **{k: v for k, v in plan.items() if k not in {"items", "duplicate_baseline"}}}))
            else:
                args.plan.write_text(json.dumps(plan, indent=2) + "\n")
                print(json.dumps({k: v for k, v in plan.items() if k not in {"items", "duplicate_baseline"}}))


if __name__ == "__main__":
    main()
