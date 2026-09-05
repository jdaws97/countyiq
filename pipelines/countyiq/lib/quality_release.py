"""Version-bound quality approval, independent of runtime format-gate rates."""
from __future__ import annotations
from datetime import date
import hashlib
import json
import os
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[2] / "eval/fixtures"


def release_identity(pass_number: int) -> dict:
    from countyiq.lib.pass_llm_config import resolve_pass_model, resolve_pass_reasoning_effort
    from countyiq.lib import pass0_templates, pass1_entity_verification, pass2_batched_validation, pass3_brief_generation, pass3_owner_briefs
    versions = {
        0: [pass0_templates.PROMPT_VERSION],
        1: [pass1_entity_verification.PROMPT_VERSION],
        2: [pass2_batched_validation.PROMPT_VERSION],
        3: [pass3_brief_generation.PROMPT_VERSION, pass3_owner_briefs.PROMPT_VERSION],
    }
    names = {0: ["p0_expected.json"], 1: ["p1_frozen.json"],
             2: ["p2_expanded_stability20.json", "feature_cases.json"],
             3: ["p3_investigation_frozen.json", "p2_frozen.json", "feature_cases.json"]}[pass_number]
    if pass_number == 0:
        manifest = json.loads((FIXTURES / "p0_expected.json").read_text())
        names.extend("p0_pdfs/" + item["file"] for item in manifest["documents"])
        names.extend(["municipal_pilot_regressions.json", "p0_claims_contract.json"])
    files = {name: hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest() for name in names}
    # Bind approval to schemas, prompt builders and relevant generation settings,
    # including escalation. A format-gate percentage alone cannot approve quality.
    modules = {0: pass0_templates, 1: pass1_entity_verification,
               2: pass2_batched_validation, 3: pass3_brief_generation}
    source_paths = [Path(modules[pass_number].__file__), Path(__file__).with_name("pass_schemas.py"),
                    Path(__file__).with_name("prompt_prefix.py"),
                    Path(__file__).with_name("intelligence_integrity.py")]
    if pass_number == 0:
        source_paths.extend(Path(__file__).with_name(name) for name in
                            ("proceeding_contract.py", "proceeding_claims.py", "proceeding_semantics.py", "proceeding_coverage.py", "source_passages.py", "proceeding_quality.py"))
        source_paths.extend([
            Path(__file__).parent / "parsers/public_proceedings.py",
            Path(__file__).parents[1] / "assets/enrichment/proceeding_extraction.py",
            Path(__file__).parents[2] / "alembic/versions/061_proceeding_evidence_contract.py",
            Path(__file__).parents[2] / "alembic/versions/063_intelligence_event_types.py",
            Path(__file__).parents[2] / "alembic/versions/064_proceeding_updates.py",
        ])
    if pass_number == 3:
        source_paths.append(Path(pass3_owner_briefs.__file__))
    if pass_number == 1:
        source_paths.append(Path(__file__).parents[1] / "assets/enrichment/entity_verification.py")
    if pass_number in (2, 3):
        source_paths.extend(Path(__file__).with_name(name) for name in
                            ("signal_policy.py", "intelligence_common.py"))
        source_paths.append(Path(__file__).parents[2] / "eval/source_context_cases.py")
        source_paths.extend([
            Path(__file__).parents[1] / "assets/enrichment/development_signals.py",
            Path(__file__).parents[2] / "alembic/versions/066_parcel_spatial_facts.py",
        ])
    if pass_number == 2:
        source_paths.append(Path(__file__).with_name("pass2_signal_validation.py"))
    source_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
    settings = {key: os.environ.get(key, "").strip() for key in (
        f"COUNTYIQ_PASS{pass_number}_THINKING", f"COUNTYIQ_PASS{pass_number}_MAX_TOKENS",
        f"COUNTYIQ_PASS{pass_number}_ESCALATION_MODEL",
        f"COUNTYIQ_PASS{pass_number}_ESCALATION_REASONING_EFFORT",
        "COUNTYIQ_THINKING", "COUNTYIQ_STRICT_SCHEMA", "COUNTYIQ_PASS1_ADAPTIVE_VOTING")}
    return {"pass_number": pass_number, "source_hashes": source_hashes, "settings": settings, "model": resolve_pass_model(pass_number),
            "prompt_versions": versions[pass_number], "reasoning_effort": resolve_pass_reasoning_effort(pass_number),
            "trials": os.environ.get(f"COUNTYIQ_PASS{pass_number}_TRIALS", "3" if pass_number == 1 else "1"),
            "fixtures": files}


def check_quality_release(pass_number: int, path: Path | None = None) -> dict:
    path = path or (Path(value) if (value := os.environ.get(f"COUNTYIQ_PASS{pass_number}_QUALITY_RECEIPT", "").strip()) else None)
    identity = release_identity(pass_number)
    if path is None:
        return {"ok": False, "reason": "A current model/prompt quality receipt is required", "expected": identity}
    try:
        receipt = json.loads(path.read_text())
        if not isinstance(receipt, dict):
            raise ValueError("Receipt must be an object")
        evaluation = receipt.get("evaluation_record")
        artifact_ok = False
        if isinstance(evaluation, dict) and isinstance(evaluation.get("path"), str):
            artifact = path.parent / evaluation["path"]
            artifact_ok = hashlib.sha256(artifact.read_bytes()).hexdigest() == evaluation.get("sha256")
        reviewed = date.fromisoformat(receipt.get("reviewed_at", ""))
        ok = (receipt.get("identity") == identity and receipt.get("decision") == "approved"
              and isinstance(receipt.get("reviewer"), str) and bool(receipt["reviewer"].strip())
              and reviewed <= date.today() and artifact_ok
              and type(receipt.get("catastrophic_errors")) is int and receipt["catastrophic_errors"] == 0)
        return {"ok": bool(ok), "reason": "Current release approved" if ok else "Quality approval missing, stale, or incomplete", "expected": identity}
    except (OSError, ValueError, TypeError):
        return {"ok": False, "reason": "Quality receipt is unreadable", "expected": identity}
