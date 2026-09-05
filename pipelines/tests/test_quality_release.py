import json
from countyiq.lib.quality_release import check_quality_release, release_identity
from eval.fixture_io import load_frozen_cases
from eval.feature_cases import FIXTURE, prompt_for, score


def test_quality_receipt_cannot_survive_prompt_model_or_fixture_changes(tmp_path, monkeypatch):
    path=tmp_path/"quality.json"
    import hashlib
    artifact = tmp_path/"reviewed-outputs.json"
    artifact.write_text("test evaluation record")
    receipt={"identity":release_identity(2), "decision":"approved", "reviewer":"test reviewer",
        "reviewed_at":"2026-09-04", "evaluation_record":{"path":artifact.name,"sha256":hashlib.sha256(artifact.read_bytes()).hexdigest()}, "catastrophic_errors":0}
    path.write_text(json.dumps(receipt))
    assert check_quality_release(2,path)["ok"]
    artifact.write_text("modified evaluation record")
    assert not check_quality_release(2,path)["ok"]
    artifact.write_text("test evaluation record")
    monkeypatch.setenv("COUNTYIQ_PASS2_MODEL","different/model")
    assert not check_quality_release(2,path)["ok"]


def test_supplemental_cases_are_frozen_and_have_real_prompt_context():
    cases=load_frozen_cases(FIXTURE)
    assert len([c for c in cases if c["pass"]=="2"]) >= 4
    assert len([c for c in cases if c["pass"]=="3b"]) >= 3
    for case in cases:
        prompt=prompt_for(case)
        assert "municipal_action" in prompt
        assert not score(case,{})["passed"]

def test_quality_receipts_fail_closed_on_bad_shape(tmp_path):
    path = tmp_path / "quality.json"
    for payload in [[], None, {"decision": "approved"}, "approved"]:
        path.write_text(json.dumps(payload))
        assert not check_quality_release(2, path)["ok"]


def test_pass3_contract_uses_investigation_actions_without_changing_original_gold():
    from pathlib import Path
    fixture_dir = Path(FIXTURE).parent
    current = load_frozen_cases(fixture_dir / "p3_investigation_frozen.json")
    prior = load_frozen_cases(fixture_dir / "p3_frozen.json")
    assert [c["context_sha256"] for c in current] == [c["context_sha256"] for c in prior]
    for case in current:
        fields = case["labels"]["accepted_fields"]
        assert set(fields["recommendation"]) <= {"investigate", "watch", "insufficient_evidence"}
        assert fields["urgency"] == ["none"]
