#!/usr/bin/env python3
"""Live test of Pass 0 extraction against real municipality PDFs.

Sends 2-3 real meeting minute PDFs to Grok 4.1 Fast via OpenRouter
and prints the extraction results.

Usage:
    cd pipelines && source .venv/bin/activate
    OPENROUTER_API_KEY=$(cat ~/.config/openrouter/key) \
    python scripts/test_pass0_live.py
"""

import json
import os
import sys

import requests

# Ensure the package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from countyiq.lib.llm_harness import HarnessConfig, get_preset_for_model, invoke_with_retry
from countyiq.lib.pass0_templates import EXTRACTION_PROMPT

MODEL = "x-ai/grok-4.1-fast"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; CountyIQ/1.0; +https://countyiq.app)"}

# Real PDF URLs from the municipality survey (verified via Playwright)
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


def find_pdf_urls_on_page(url: str) -> list[str]:
    """Quick helper to find PDF links on a page."""
    import re
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return re.findall(r'href=["\']([^"\']+\.pdf)["\']', resp.text, re.I)[:5]
    except Exception as e:
        print(f"  Failed to fetch page: {e}")
        return []


def test_pdf(pdf_info: dict, config: HarnessConfig) -> None:
    url = pdf_info["url"]
    print(f"\n{'='*70}")
    print(f"Testing: {pdf_info['name']}")
    print(f"URL: {url}")

    # If URL is not a direct PDF, try to find PDFs on the page
    if not url.lower().endswith(".pdf"):
        print("  Not a direct PDF URL — searching page for PDF links...")
        pdf_urls = find_pdf_urls_on_page(url)
        if not pdf_urls:
            print("  No PDFs found on page. Skipping.")
            return
        url = pdf_urls[0]
        if not url.startswith("http"):
            from urllib.parse import urljoin
            url = urljoin(pdf_info["url"], url)
        print(f"  Found PDF: {url}")

    # Download PDF
    print("  Downloading PDF...")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        pdf_bytes = resp.content
        print(f"  Downloaded {len(pdf_bytes) // 1024} KB")
    except Exception as e:
        print(f"  FAILED to download: {e}")
        return

    # Build prompt
    date_clause = f" dated {pdf_info['meeting_date']}" if pdf_info.get("meeting_date") else ""
    prompt = EXTRACTION_PROMPT.format(
        body_name=pdf_info["body_name"],
        proceeding_type=pdf_info["proceeding_type"],
        date_clause=date_clause,
    )

    # Send to LLM
    print(f"  Sending to {MODEL}...")
    result = invoke_with_retry(
        config,
        prompt,
        pdf_bytes=pdf_bytes,
        retries=1,
        archive_key=f"test:{pdf_info['name']}",
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
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("ERROR: OPENROUTER_API_KEY not set")
        sys.exit(1)

    print(f"Model: {MODEL}")
    print(f"API key: {api_key[:12]}...{api_key[-4:]}")

    preset = get_preset_for_model(MODEL, thinking=False, reasoning_task=False)
    config = HarnessConfig(
        model_path=MODEL,
        backend="openrouter",
        archive_label="pass0_test",
        max_tokens=4096,
        **preset,
    )

    for pdf_info in TEST_PDFS:
        test_pdf(pdf_info, config)

    print(f"\n{'='*70}")
    print("Done!")


if __name__ == "__main__":
    main()
