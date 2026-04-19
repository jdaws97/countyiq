#!/usr/bin/env python3
"""Live test of Pass 0 extraction against real municipality PDFs.

Downloads a few real meeting-minute PDFs and sends them to an OpenRouter
Pass 0 model with native PDF input.

Usage:
    cd pipelines && source .venv/bin/activate
    OPENROUTER_API_KEY=... COUNTYIQ_PASS0_MODEL=x-ai/grok-4.1-fast python scripts/test_pass0_live.py
"""

from __future__ import annotations

import os
import sys

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from countyiq.lib.llm_harness import invoke_with_retry
from countyiq.lib.pass_llm_config import build_pass_harness_config
from countyiq.lib.pass0_templates import EXTRACTION_PROMPT

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; CountyIQ/1.0; +https://countyiq.app)"}

TEST_PDFS = [
    {
        "name": "West Manchester ZHB Agenda Feb 2026",
        "url": "https://www.westmanchestertownship.com/wp-content/uploads/ZHB-Agenda-February-24-2026.pdf",
        "body_name": "West Manchester Twp Zoning Hearing Board",
        "proceeding_type": "zoning_hearing",
        "meeting_date": "2026-02-24",
    },
    {
        "name": "Dover Twp Auditors Minutes 2025",
        "url": "https://www.dovertownship.org/wp-content/uploads/2026/01/Auditors-Meeting-minutes-2025.pdf",
        "body_name": "Dover Twp Board of Supervisors",
        "proceeding_type": "board_of_supervisors",
        "meeting_date": "2025-01-07",
    },
]


def test_pdf(pdf_info: dict, config) -> None:
    url = pdf_info["url"]
    print(f"\n{'=' * 70}")
    print(f"Testing: {pdf_info['name']}")
    print(f"URL: {url}")

    print("  Downloading PDF...")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        pdf_bytes = resp.content
        print(f"  Downloaded {len(pdf_bytes) // 1024} KB")
    except Exception as exc:
        print(f"  FAILED to download: {exc}")
        return

    date_clause = f" dated {pdf_info['meeting_date']}" if pdf_info.get("meeting_date") else ""
    prompt = EXTRACTION_PROMPT.format(
        body_name=pdf_info["body_name"],
        proceeding_type=pdf_info["proceeding_type"],
        date_clause=date_clause,
    )

    print(f"  Sending PDF to OpenRouter model: {config.model_path}")
    result = invoke_with_retry(
        config,
        prompt,
        retries=1,
        archive_key=f"test:{pdf_info['name']}",
        pdf_bytes=pdf_bytes,
    )

    if not result.success:
        print(f"  LLM FAILED: {result.error}")
        if result.raw_output:
            print(f"  Raw output (first 500 chars): {result.raw_output[:500]}")
        return

    extractions = (result.parsed or {}).get("extractions", [])
    print(f"  SUCCESS: {len(extractions)} extraction(s)")

    for i, ext in enumerate(extractions, 1):
        print(f"\n  --- Extraction {i} ---")
        print(f"  Type: {ext.get('extraction_type')}")
        print(f"  Applicant: {ext.get('applicant_name')}")
        print(f"  Parcel: {ext.get('parcel_reference')}")
        print(f"  Decision: {ext.get('decision')}")
        print(f"  Confidence: {ext.get('confidence')}")
        text = ext.get("supporting_text", "")
        if text:
            print(f"  Supporting text: {text[:150]}...")

    if not extractions:
        print("  (No relevant records found in this document)")


def main():
    config = build_pass_harness_config(
        pass_number=0,
        archive_label="pass0_test",
        reasoning_task=False,
        default_max_tokens=4096,
        default_thinking=False,
    )
    if config is None:
        print("ERROR: Set COUNTYIQ_PASS0_MODEL or COUNTYIQ_OPENROUTER_MODEL before running this script")
        sys.exit(1)

    print(f"Model: {config.model_path}")
    for pdf_info in TEST_PDFS:
        test_pdf(pdf_info, config)

    print(f"\n{'=' * 70}")
    print("Done!")


if __name__ == "__main__":
    main()
