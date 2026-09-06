"""Prepare frozen candidate requests only; this command cannot invoke a provider."""

import argparse
import hashlib
import json
from pathlib import Path

from eval.passage_candidate_prompt import SYSTEM_PROMPT, PROMPT_VERSION
from eval.passage_extraction_contract import CANDIDATE_SCHEMA, passage_input
from eval.passage_contract_probe import REPO_ROOT
from countyiq.lib.source_passages import index_source_passages


def prepare(report_path: Path, output: Path) -> dict:
    report = json.loads(report_path.read_text())
    requests = []
    seen = set()
    for batch in report["batches"]:
        base = REPO_ROOT / batch["artifact_directory"]
        for filename, expected in batch["sha256"].items():
            if hashlib.sha256((base / filename).read_bytes()).hexdigest() != expected:
                raise ValueError(f"Archived artifact hash mismatch: {base / filename}")
        for source in json.loads((base / "sources.json").read_text()):
            if source["id"] in seen:
                raise ValueError("Duplicate source across candidate batches")
            seen.add(source["id"])
            document = index_source_passages(source["raw_text"])
            user = {
                "body_name": source["body_name"],
                "meeting_date": source["meeting_date"],
                "proceeding_type": source["proceeding_type"],
                **passage_input(document),
            }
            requests.append(
                {
                    "source_id": source["id"],
                    "batch": batch["artifact_directory"],
                    "document_url": source["document_url"],
                    "user": user,
                }
            )
    code_paths = [
        "countyiq/lib/source_passages.py",
        "eval/passage_extraction_contract.py",
        "eval/passage_candidate_prompt.py",
        "eval/prepare_passage_candidate.py",
        "countyiq/lib/pass_schemas.py",
        "countyiq/lib/proceeding_contract.py",
        "countyiq/lib/intelligence_integrity.py",
    ]
    code_hashes = {
        name: hashlib.sha256((REPO_ROOT / "pipelines" / name).read_bytes()).hexdigest()
        for name in code_paths
    }
    protocol = {
        "state": "prepared_only",
        "prompt_version": PROMPT_VERSION,
        "document_count": len(requests),
        "publication": "none",
        "model": None,
        "spend_authorization": None,
        "code_sha256": code_hashes,
        "sample_scope": "Previously evaluated sources; these are regression inputs, not new unseen holdout evidence.",
        "required_review": [
            "claim support",
            "decision scope",
            "date purpose",
            "material omissions",
            "relevance",
            "project continuity",
            "unresolved references",
            "returned cost",
        ],
    }
    files = {
        "system-prompt.txt": SYSTEM_PROMPT,
        "schema.json": json.dumps(CANDIDATE_SCHEMA, indent=2),
        "requests.json": json.dumps(requests, ensure_ascii=False, indent=2),
    }
    protocol["artifact_sha256"] = {
        name: hashlib.sha256(content.encode()).hexdigest()
        for name, content in files.items()
    }
    output.mkdir(parents=True, exist_ok=False)
    for name, content in files.items():
        (output / name).write_text(content)
    (output / "protocol.json").write_text(json.dumps(protocol, indent=2))
    return protocol


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.report, args.output_dir)))


if __name__ == "__main__":
    main()
