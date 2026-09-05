import hashlib
import json
import pytest
from eval.prepare_passage_candidate import prepare


@pytest.fixture
def archived_report(tmp_path):
    batch=tmp_path / "batch"
    batch.mkdir()
    source={"id":1,"body_name":"Fixture Council","meeting_date":"2026-09-01",
            "proceeding_type":"council","document_url":"https://example.test/source.pdf",
            "raw_text":"Original source.\nNo text may be silently changed."}
    (batch / "sources.json").write_text(json.dumps([source]))
    report={"batches":[{"artifact_directory":str(batch),"sha256":{
        "sources.json":hashlib.sha256((batch / "sources.json").read_bytes()).hexdigest()}}]}
    path=tmp_path / "report.json"
    path.write_text(json.dumps(report))
    return path,batch,source


def test_preparation_preserves_source_and_binds_every_artifact(tmp_path, archived_report):
    report,_,source=archived_report
    output=tmp_path / "prepared"
    protocol=prepare(report,output)
    assert protocol["state"]=="prepared_only"
    assert protocol["model"] is None and protocol["spend_authorization"] is None
    requests=json.loads((output / "requests.json").read_text())
    assert "".join(p["text"] for p in requests[0]["user"]["passages"])==source["raw_text"]
    for name,digest in protocol["artifact_sha256"].items():
        assert hashlib.sha256((output / name).read_bytes()).hexdigest()==digest
    with pytest.raises(FileExistsError): prepare(report,output)


def test_changed_archive_is_rejected_before_creating_package(tmp_path, archived_report):
    report,batch,_=archived_report
    (batch / "sources.json").write_text("[]")
    output=tmp_path / "rejected"
    with pytest.raises(ValueError,match="hash mismatch"): prepare(report,output)
    assert not output.exists()


def test_repeated_sources_cannot_bias_prepared_sample(tmp_path, archived_report):
    report,_,_=archived_report
    value=json.loads(report.read_text())
    value["batches"]*=2
    report.write_text(json.dumps(value))
    output=tmp_path / "duplicates"
    with pytest.raises(ValueError,match="Duplicate source"): prepare(report,output)
    assert not output.exists()
