"""Offline passage-contract feasibility against unchanged archived evaluations.

Usage: from pipelines, .venv/bin/python -m eval.passage_contract_probe
  --report ../docs/research/municipal-llm-v2-results-2026-09-04.json
  --output ../output/passage-contract-probe.json
No database access, provider calls, output repairs, or publication.
"""

import argparse
import hashlib
import json
from pathlib import Path

from countyiq.lib.source_passages import index_source_passages

REPO_ROOT = Path(__file__).resolve().parents[2]


def probe(report_path: Path) -> dict:
    report = json.loads(report_path.read_text())
    documents = []
    for batch in report["batches"]:
        base = REPO_ROOT / batch["artifact_directory"]
        for filename, expected in batch["sha256"].items():
            actual = hashlib.sha256((base / filename).read_bytes()).hexdigest()
            if actual != expected:
                raise ValueError(f"Archived artifact hash mismatch: {base / filename}")
        sources = {
            str(row["id"]): row
            for row in json.loads((base / "sources.json").read_text())
        }
        responses = json.loads((base / "results.json").read_text())["responses"]
        for source_id, response in responses.items():
            text = sources[str(source_id)]["raw_text"]
            document = index_source_passages(text)
            assert "".join(p.text for p in document.passages) == text
            offsets = [i for i, char in enumerate(text) if not char.isspace()]
            compact = "".join(text[i] for i in offsets)
            checks = []
            for item in (response.get("parsed") or {}).get("extractions", []):
                for span in item.get("evidence_spans") or []:
                    quote = span.get("quote") or ""
                    needle = "".join(quote.split())
                    position = compact.find(needle) if needle else -1
                    if position < 0:
                        checks.append({"mapped": False})
                        continue
                    start, end = (
                        offsets[position],
                        offsets[position + len(needle) - 1] + 1,
                    )
                    ids = [
                        p.passage_id
                        for p in document.passages
                        if p.start < end and p.end > start
                    ]
                    selected = document.resolve(document.source_sha256, ids)
                    assert needle in "".join("".join(p.text.split()) for p in selected)
                    checks.append(
                        {
                            "mapped": True,
                            "passage_ids": ids,
                            "quote_characters": len(quote),
                            "id_array_characters": len(json.dumps(ids)),
                        }
                    )
            documents.append(
                {
                    "source_id": source_id,
                    "batch": str(base.relative_to(REPO_ROOT)),
                    "source_sha256": document.source_sha256,
                    "passages": len(document.passages),
                    "checks": checks,
                }
            )
    checks = [check for document in documents for check in document["checks"]]
    mapped = [check for check in checks if check["mapped"]]
    return {
        "scope": "Offline format feasibility only; membership is not entailment; character counts are not token or cost estimates.",
        "summary": {
            "documents": len(documents),
            "passages": sum(d["passages"] for d in documents),
            "mapped_quotes": len(mapped),
            "unmapped_quotes": len(checks) - len(mapped),
            "mapped_quote_characters": sum(c["quote_characters"] for c in mapped),
            "id_array_characters": sum(c["id_array_characters"] for c in mapped),
        },
        "documents": documents,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = probe(args.report)
    # Preserve earlier probes rather than silently replacing evidence.
    with args.output.open("x") as destination:
        json.dump(result, destination, indent=2)
    print(json.dumps(result["summary"]))


if __name__ == "__main__":
    main()
