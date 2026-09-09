import json

import pytest
from countyiq.lib.quality_release import check_quality_release, release_identity
from eval.feature_cases import FIXTURE, prompt_for, score
from eval.fixture_io import load_frozen_cases


def test_quality_receipt_cannot_survive_prompt_model_or_fixture_changes(
    tmp_path, monkeypatch
):
    path = tmp_path / "quality.json"
    import hashlib

    artifact = tmp_path / "reviewed-outputs.json"
    artifact.write_text("test evaluation record")
    receipt = {
        "identity": release_identity(2),
        "decision": "approved",
        "reviewer": "test reviewer",
        "reviewed_at": "2026-09-04",
        "evaluation_record": {
            "path": artifact.name,
            "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        },
        "catastrophic_errors": 0,
    }
    path.write_text(json.dumps(receipt))
    assert check_quality_release(2, path)["ok"]
    artifact.write_text("modified evaluation record")
    assert not check_quality_release(2, path)["ok"]
    artifact.write_text("test evaluation record")
    monkeypatch.setenv("COUNTYIQ_PASS2_MODEL", "different/model")
    assert not check_quality_release(2, path)["ok"]


def test_supplemental_cases_are_frozen_and_have_real_prompt_context():
    cases = load_frozen_cases(FIXTURE)
    assert len([c for c in cases if c["pass"] == "2"]) >= 4
    assert len([c for c in cases if c["pass"] == "3b"]) >= 3
    for case in cases:
        prompt = prompt_for(case)
        assert "municipal_action" in prompt
        assert not score(case, {})["passed"]


def test_quality_receipts_fail_closed_on_bad_shape(tmp_path):
    path = tmp_path / "quality.json"
    for payload in [[], None, {"decision": "approved"}, "approved"]:
        path.write_text(json.dumps(payload))
        assert not check_quality_release(2, path)["ok"]


@pytest.mark.parametrize(
    "pass_numbers, source_name",
    [
        ((0,), "proceeding_quality.py"),
        ((0,), "public_proceedings.py"),
        ((2, 3), "066_parcel_spatial_facts.py"),
        ((1,), "entity_verification.py"),
        ((1,), "entity_context_plan.py"),
        ((1,), "entity_context_review.py"),
        ((0, 1), "intelligence_resolution.py"),
        ((0, 1, 2, 3), "llm_harness.py"),
        ((0, 1, 2, 3), "pass_llm_config.py"),
    ],
)
def test_quality_receipt_expires_when_source_or_dispatch_rules_change(
    tmp_path, monkeypatch, pass_numbers, source_name
):
    import hashlib
    from datetime import UTC, datetime
    from pathlib import Path

    artifact = tmp_path / "reviewed.json"
    artifact.write_text("reviewed source outputs")
    paths = []
    for pass_number in pass_numbers:
        path = tmp_path / f"pass{pass_number}.json"
        path.write_text(
            json.dumps(
                {
                    "identity": release_identity(pass_number),
                    "decision": "approved",
                    "reviewer": "test reviewer",
                    "reviewed_at": datetime.now(UTC).date().isoformat(),
                    "evaluation_record": {
                        "path": artifact.name,
                        "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                    },
                    "catastrophic_errors": 0,
                }
            )
        )
        assert check_quality_release(pass_number, path)["ok"]
        paths.append((pass_number, path))
    original_read = Path.read_bytes

    def changed_source(path):
        contents = original_read(path)
        return (
            contents + b"\n# changed production rules"
            if path.name == source_name
            else contents
        )

    monkeypatch.setattr(Path, "read_bytes", changed_source)
    assert all(not check_quality_release(number, path)["ok"] for number, path in paths)


def test_pass3_contract_uses_investigation_actions_without_changing_original_gold():
    from pathlib import Path

    fixture_dir = Path(FIXTURE).parent
    current = load_frozen_cases(fixture_dir / "p3_investigation_frozen.json")
    prior = load_frozen_cases(fixture_dir / "p3_frozen.json")
    assert [c["context_sha256"] for c in current] == [
        c["context_sha256"] for c in prior
    ]
    for case in current:
        fields = case["labels"]["accepted_fields"]
        assert set(fields["recommendation"]) <= {
            "investigate",
            "watch",
            "insufficient_evidence",
        }
        assert fields["urgency"] == ["none"]


@pytest.mark.parametrize(
    "relative_path",
    [
        "countyiq/lib/record_explanations.py",
        "countyiq/assets/enrichment/record_explanations.py",
        "countyiq/lib/municipal_matters.py",
        "countyiq/lib/pass_subscription.py",
        "alembic/versions/071_municipal_matter_accounts.py",
        "alembic/versions/075_activity_presentation_readiness.py",
    ],
)
def test_records_receipt_expires_when_either_explanation_file_changes(
    tmp_path, monkeypatch, relative_path
):
    import hashlib
    from datetime import UTC, datetime
    from pathlib import Path

    monkeypatch.setenv("COUNTYIQ_PASS3_MODE", "records")
    artifact = tmp_path / "reviewed.json"
    artifact.write_text("reviewed source outputs")
    receipt = tmp_path / "quality.json"
    receipt.write_text(
        json.dumps(
            {
                "identity": release_identity(3),
                "decision": "approved",
                "reviewer": "test reviewer",
                "reviewed_at": datetime.now(UTC).date().isoformat(),
                "evaluation_record": {
                    "path": artifact.name,
                    "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                },
                "catastrophic_errors": 0,
            }
        )
    )
    assert check_quality_release(3, receipt)["ok"]
    target = Path(__file__).resolve().parents[1] / relative_path
    original_read = Path.read_bytes

    def changed_source(path):
        contents = original_read(path)
        if path.resolve() == target:
            return contents + b"\n# changed validation or generation rules"
        return contents

    monkeypatch.setattr(Path, "read_bytes", changed_source)
    assert not check_quality_release(3, receipt)["ok"]
