#!/usr/bin/env python3
"""Build de-identified frozen Pass 2/3 fixtures and a live shadow manifest.

This command performs no model calls. It reads deterministic database context,
selects one reproducible parcel for every two-signal production combination,
de-identifies direct identifiers, joins human-reviewed labels, and fingerprints
the exact contexts used by the frozen promotion lane.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras

from countyiq.lib.pass2_batched_validation import gather_parcel_batch_context
from eval.fixture_io import canonical_context_hash


FIXTURES = Path(__file__).resolve().parent / "fixtures"
INTERPRETIVE_SIGNALS = (
    "active_subdivision",
    "assemblage",
    "ownership_change",
    "vacancy",
    "zoning_mismatch",
)

_PERSON_ALIASES = (
    "Avery Bennett",
    "Morgan Ellis",
    "Jordan Patel",
    "Taylor Brooks",
    "Casey Morgan",
    "Riley Turner",
    "Cameron Reed",
    "Quinn Foster",
    "Drew Parker",
    "Hayden Ross",
    "Robin Carter",
    "Alex Monroe",
    "Jamie Sullivan",
    "Devon Hayes",
    "Skyler Grant",
    "Peyton Walsh",
)
_ORGANIZATION_ROOTS = (
    "Cedar Ridge",
    "North Valley",
    "Granite Creek",
    "Silver Oak",
    "Meadow Brook",
    "Pine Hollow",
    "Stone Bridge",
    "Clearwater",
    "Red Maple",
    "Blue Heron",
    "Fox Run",
    "Laurel Grove",
    "Ironwood",
    "Willow Bend",
    "Highland Park",
    "Mill Creek",
)

PAIR_SAMPLE_QUERY = """
WITH per_pidn AS (
    SELECT pidn,
           array_agg(DISTINCT signal_key ORDER BY signal_key) FILTER (
               WHERE signal_key = ANY(%(signals)s)
           ) AS keys
    FROM public.development_signals
    GROUP BY pidn
), ranked AS (
    SELECT pidn, keys,
           row_number() OVER (PARTITION BY keys ORDER BY md5(pidn)) AS rank
    FROM per_pidn
    WHERE cardinality(keys) = 2
)
SELECT pidn, keys
FROM ranked
WHERE rank = 1
ORDER BY keys
"""


def _db():
    return psycopg2.connect(
        host=os.environ.get("DATABASE_HOST", "localhost"),
        port=int(os.environ.get("DATABASE_PORT", 5433)),
        dbname=os.environ.get("DATABASE_NAME", "countyiq"),
        user=os.environ.get("DATABASE_USER", "dagster_admin"),
        password=os.environ.get("DATABASE_PASSWORD", "localtest"),
    )


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _scrub_evidence(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _scrub_evidence(item)
            for key, item in value.items()
            if key not in {"evidence_captured_at", "detail_url"}
        }
    if isinstance(value, list):
        return [_scrub_evidence(item) for item in value]
    return value


def _pseudonymous_owner(original: str, ordinal: int) -> str:
    """Return a realistic alias while retaining decision-relevant entity type."""
    upper = original.upper()
    person = _PERSON_ALIASES[ordinal % len(_PERSON_ALIASES)]
    root = _ORGANIZATION_ROOTS[ordinal % len(_ORGANIZATION_ROOTS)]
    if "WATER" in upper:
        return f"{root} Water Company"
    if "SEWER" in upper:
        return f"{root} Sewer Authority"
    if "SCHOOL" in upper:
        suffix = "School Authority" if "AUTH" in upper else "School District"
        return f"{root} {suffix}"
    if "TOWNSHIP" in upper or re.search(r"\bTWP\b", upper):
        return f"{root} Township"
    if "BOROUGH" in upper or re.search(r"\bBORO\b", upper):
        return f"{root} Borough"
    if "MUNICIPAL" in upper or "AUTHORITY" in upper:
        return f"{root} Municipal Authority"
    if "CEMETERY" in upper:
        return f"{root} Cemetery Association"
    if any(token in upper for token in ("CHURCH", "MINISTR", "PARISH")):
        return f"{root} Community Church"
    if "TRUST" in upper:
        return f"{person} Family Trust"
    if "ESTATE" in upper:
        return f"Estate of {person}"
    if re.search(r"\bLLC\b", upper):
        return f"{root} Holdings LLC"
    if re.search(r"\b(LP|L P)\b", upper):
        return f"{root} Partners LP"
    if any(token in upper for token in (" INC", "CORP", "COMPANY", " CO ")):
        return f"{root} Company"
    return person


def _deidentify_context(raw: dict, case_id: str) -> dict:
    """Remove direct identifiers while preserving relationships and entity type."""
    context = _json_safe(copy.deepcopy(raw))
    original_pidn = context["pidn"]
    target_pidn = case_id.upper().replace("-", "")
    original_owner = str(context.get("parcel", {}).get("owner") or "")
    original_surname = original_owner.split()[0].lower() if original_owner else ""
    case_number = int(case_id.rsplit("-", 1)[-1])
    owner_aliases: dict[str, str] = {}

    def alias_owner(value: Any) -> str:
        original = str(value or "").strip()
        if not original:
            return ""
        key = _normalized_owner(original)
        if key not in owner_aliases:
            owner_aliases[key] = _pseudonymous_owner(
                original, case_number * 17 + len(owner_aliases)
            )
        return owner_aliases[key]

    target_owner = alias_owner(original_owner)

    context["pidn"] = target_pidn
    parcel = context.get("parcel", {})
    parcel["pidn"] = target_pidn
    parcel["owner"] = target_owner
    parcel["address"] = f"{100 + case_number} Cedar Road"
    if parcel.get("previous_owner"):
        parcel["previous_owner"] = alias_owner(parcel["previous_owner"])
    parcel["source_url"] = ""

    entity = context.get("entity") or {}
    if entity.get("found"):
        entity["canonical_name"] = target_owner
        entity["linked_names"] = [target_owner]

    for index, neighbor in enumerate(context.get("neighbors") or [], 1):
        neighbor["pidn"] = f"{target_pidn}N{index:02d}"
        neighbor["owner"] = alias_owner(neighbor.get("owner"))

    for index, item in enumerate(context.get("portfolio") or [], 1):
        item["pidn"] = f"{target_pidn}P{index:02d}"
        item["owner"] = alias_owner(item.get("owner")) or target_owner

    for claim in context.get("tax_claims") or []:
        claim["pidn"] = target_pidn
        if "owner" in claim:
            claim["owner"] = alias_owner(claim.get("owner")) or target_owner

    for index, corporate in enumerate(context.get("corporate") or [], 1):
        for key in ("entity_name", "matched_name", "registered_agent_name"):
            if corporate.get(key):
                corporate[key] = alias_owner(corporate[key])
        for key in ("office_address", "registered_agent_address"):
            if corporate.get(key):
                corporate[key] = f"{300 + case_number + index} Market Street"

    for index, proceeding in enumerate(context.get("proceedings") or [], 1):
        if proceeding.get("applicant_name"):
            proceeding["applicant_name"] = alias_owner(proceeding["applicant_name"])
        if proceeding.get("parcel_reference"):
            proceeding["parcel_reference"] = target_pidn

    for signal in [
        *(context.get("signals") or []),
        *(context.get("context_signals") or []),
    ]:
        if str(signal.get("source_id")) == str(original_pidn):
            signal["source_id"] = target_pidn
        evidence = _scrub_evidence(signal.get("evidence") or {})
        if "prev_owner" in evidence:
            evidence["prev_owner"] = alias_owner(evidence["prev_owner"])
        if "plan_title" in evidence:
            title = str(evidence["plan_title"])
            evidence["plan_title"] = (
                target_owner
                if original_surname and original_surname in title.lower()
                else f"{_ORGANIZATION_ROOTS[case_number % len(_ORGANIZATION_ROOTS)]} Plan"
            )
        signal["evidence"] = evidence

    return context


def _normalized_owner(value: str) -> str:
    return " ".join(value.upper().split())


def _load_labels() -> dict[str, dict]:
    payload = json.loads((FIXTURES / "p2_labels.json").read_text())
    return {case["id"]: case for case in payload["cases"]}


def _build_pass3_cases(pass2_cases: list[dict]) -> list[dict]:
    specs = json.loads((FIXTURES / "p3_case_specs.json").read_text())["cases"]
    p2_by_id = {case["id"]: case for case in pass2_cases}
    cases = []
    for spec in specs:
        source = p2_by_id[spec["source_pass2_case"]]["context"]
        context = {
            "pidn": source["pidn"],
            "parcel": source["parcel"],
            "entity": source.get("entity") or {"found": False},
            "portfolio": {},
            "validated_signals": spec["validated_signals"],
        }
        cases.append(
            {
                "id": spec["id"],
                "source_pass2_case": spec["source_pass2_case"],
                "case_type": spec["case_type"],
                "context": context,
                "context_sha256": canonical_context_hash(context),
                "labels": spec["labels"],
                "review": spec["review"],
            }
        )
    return cases


def _build_pass1_cases() -> list[dict]:
    specs = json.loads((FIXTURES / "p1_case_specs.json").read_text())["cases"]
    cases = []
    for spec in specs:
        context = spec["context"]
        cases.append(
            {
                "id": spec["id"],
                "case_type": spec["case_type"],
                "context": context,
                "context_sha256": canonical_context_hash(context),
                "labels": spec["labels"],
                "review": spec["review"],
            }
        )
    return cases


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate that regenerated fixtures match committed files.",
    )
    args = parser.parse_args()

    labels = _load_labels()
    conn = _db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(PAIR_SAMPLE_QUERY, {"signals": list(INTERPRETIVE_SIGNALS)})
    selected = [dict(row) for row in cur.fetchall()]
    if len(selected) != 10:
        raise RuntimeError(
            f"Expected 10 two-signal combinations, found {len(selected)}"
        )

    pass2_cases = []
    shadow_rows = []
    for index, row in enumerate(selected, 1):
        case_id = f"p2-{index:03d}"
        if case_id not in labels:
            raise RuntimeError(f"Missing human label for {case_id}")
        raw = gather_parcel_batch_context(cur, row["pidn"])
        context = _deidentify_context(raw, case_id)
        pass2_cases.append(
            {
                "id": case_id,
                "case_type": labels[case_id]["case_type"],
                "signal_combination": list(row["keys"]),
                "context": context,
                "context_sha256": canonical_context_hash(context),
                "labels": labels[case_id]["labels"],
                "review": labels[case_id]["review"],
            }
        )
        shadow_rows.append(
            {"pidn": row["pidn"], "signals": list(row["keys"]), "case_id": case_id}
        )
    cur.close()
    conn.close()

    pass2_payload = {
        "version": 1,
        "reviewed_at": "2026-08-30",
        "selection": "one md5-stable parcel for every exact two-signal combination",
        "deidentification": (
            "Direct parcel, owner, address, neighbor, prior-owner, corporate, and "
            "applicant identifiers replaced with realistic stable aliases; ownership "
            "relationships and decision-relevant entity types, numeric facts, and "
            "source evidence retained."
        ),
        "cases": pass2_cases,
    }
    shadow_payload = {
        "version": 1,
        "refreshed_at": "2026-08-30",
        "selection": "one md5-stable live parcel for every exact two-signal combination",
        "cases": shadow_rows,
    }
    pass3_payload = {
        "version": 1,
        "reviewed_at": "2026-08-30",
        "derivation": "production Pass 3 contexts built from reviewed frozen Pass 2 cases",
        "cases": _build_pass3_cases(pass2_cases),
    }
    pass1_payload = {
        "version": 1,
        "reviewed_at": "2026-08-30",
        "derivation": "de-identified production-shaped entity-resolution contexts",
        "cases": _build_pass1_cases(),
    }

    outputs = {
        FIXTURES / "p1_frozen.json": json.dumps(pass1_payload, indent=2) + "\n",
        FIXTURES / "p2_frozen.json": json.dumps(pass2_payload, indent=2) + "\n",
        FIXTURES / "p2_live_shadow.json": json.dumps(shadow_payload, indent=2) + "\n",
        FIXTURES / "p2_pidns.txt": "".join(f"{row['pidn']}\n" for row in shadow_rows),
        FIXTURES / "p3_frozen.json": json.dumps(pass3_payload, indent=2) + "\n",
    }
    stale = []
    for path, content in outputs.items():
        if args.check:
            if not path.exists() or path.read_text() != content:
                stale.append(str(path))
        else:
            path.write_text(content)
            print(f"Wrote {path}")
    if stale:
        raise SystemExit("Stale generated fixtures: " + ", ".join(stale))


if __name__ == "__main__":
    main()
