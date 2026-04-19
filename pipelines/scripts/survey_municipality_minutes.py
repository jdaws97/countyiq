#!/usr/bin/env python3
"""Survey all York County municipality websites for meeting minutes PDFs.

For each municipality, visits the known homepage and any board/committee
subpages, extracts all PDF links and meeting-related links, and writes
a structured catalog to /tmp/municipality_minutes_catalog.json.

This is a one-time research script, not a production pipeline asset.
Run it, review the output, then use it to populate county_config.py.

Usage:
    python scripts/survey_municipality_minutes.py

Requires: requests, beautifulsoup4
"""

import json
import re
import sys
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; CountyIQ/1.0; +https://countyiq.app)"}
TIMEOUT = 15

# All 72 municipalities with known website URLs and committee page hints.
# Format: (name, base_url, {committee_type: path_or_url})
MUNICIPALITIES = [
    ("York Twp", "https://yorktownshippa.gov/", {
        "board_of_commissioners": "/boards/boc/",
        "planning_commission": "/boards/pc/",
        "zoning_hearing": "/boards/zhb/",
    }),
    ("Springettsbury Twp", "https://springettsbury.com/", {
        "board_of_supervisors": "/township-document-archives/?_checkbox_filter_2=meeting-minutes",
    }),
    ("Manchester Twp", "https://www.manchestertwp.org/", {
        "board_of_supervisors": "/meetings-agendas/",
    }),
    ("Spring Garden Twp", "https://www.springgardentwp.org/", {
        "board_of_supervisors": "/meeting-minutes/",
    }),
    ("Dover Twp", "https://www.dovertownship.org/", {
        "board_of_supervisors": "/minutes/",
    }),
    ("Fairview Twp", "https://www.fairviewtownship.com/", {
        "board_of_supervisors": "/boards/supervisors/minutes",
    }),
    ("West Manchester Twp", "https://www.westmanchestertownship.com/", {
        "board_of_supervisors": "/boards-committees/board-of-supervisors/",
        "zoning_hearing": "/boards-committees/zoning-hearing-board/",
    }),
    ("Penn Twp", "https://penntownship.org/", {
        "board_of_supervisors": "/meeting-minutes/",
    }),
    ("Hanover Boro", "https://hanoverboroughpa.gov/", {
        "borough_council": "/AgendaCenter",
    }),
    ("Conewago Twp", "https://conewagotownship.com/", {
        "board_of_supervisors": "/boards-and-commissions/board-of-supervisors/minutes/",
    }),
    ("Carroll Twp", "https://www.carrolltownship.com/", {
        "board_of_supervisors": "/bos-agenda-2024/",
    }),
    ("Newberry Twp", "https://newberrytownship.com/", {}),  # no minutes page found
    ("Codorus Twp", "https://codorustownship.org/", {
        "board_of_supervisors": "/meeting-minutes/",
    }),
    ("Windsor Twp", "https://windsortownship.com/", {
        "board_of_supervisors": "/events-minutes/board-of-trustees/",
    }),
    ("Hellam Twp", "https://www.hellamtownship.gov/", {
        "board_of_supervisors": "/departments/public-meetings/",
    }),
    ("Hopewell Twp", "https://www.hopewelltownship.com/", {
        "board_of_supervisors": "/public-meetings/board-of-supervisors/",
        "planning_commission": "/public-meetings/planning-commission-board/",
    }),
    ("York City", "https://www.yorkcity.org/", {
        "city_council": "/government/city-council/meetings/",
    }),
    ("Red Lion Boro", "https://redlionpa.org/", {
        "borough_council": "/government/agendas-minutes/borough-council-agendas-minutes/",
    }),
    ("Dallastown Boro", "https://dallastownboro.com/", {
        "borough_council": "/meetings-agendas-minutes/",
    }),
    ("Shrewsbury Twp", "https://www.shrewsburytownship.org/", {
        "board_of_supervisors": "/minutes/",
    }),
    ("Shrewsbury Boro", "https://shrewsburyborough.org/", {
        "borough_council": "/minutes/",
    }),
    ("North Codorus Twp", "https://northcodorustwp.org/", {
        "board_of_supervisors": "/board-of-supervisors-3/",
    }),
    ("East Hopewell Twp", "https://www.easthopewelltownshippa.gov/", {
        "board_of_supervisors": "/meetings",
    }),
    ("Manheim Twp", "https://www.manheimtwpyorkpa.org/", {
        "board_of_supervisors": "/index.php/government/minutes-agendas",
    }),
    ("Jackson Twp", "https://jackson-township.org/", {
        "board_of_supervisors": "/meeting-agendas/",
    }),
    ("Heidelberg Twp", "https://heidelbergtownship.org/", {}),  # has PDFs but old-style site
    ("Franklin Twp", "https://franklintownship.org/", {
        "board_of_supervisors": "/meeting-minutes-agendas/",
    }),
    ("North York Boro", "https://northyorkborough.com/", {
        "borough_council": "/borough-council-meeting-minutes/",
    }),
    ("Peach Bottom Twp", "https://www.peachbottomtownship.org/", {
        "board_of_supervisors": "/meeting-minutes",
    }),
    ("Monaghan Twp", "https://monaghantownship.com/", {
        "board_of_supervisors": "/AgendaCenter",
    }),
    ("Fawn Twp", "https://fawntownship.com/", {
        "board_of_supervisors": "/meetings/",
    }),
    ("Paradise Twp", "https://paradisetownship.org/", {
        "board_of_supervisors": "/documents/board-of-supervisor-agenda-notices/",
    }),
    ("East Prospect Boro", "https://www.eastprospectborough.com/", {
        "borough_council": "/minutes",
    }),
    ("Springfield Twp", "https://springfieldtownship.com/", {
        "board_of_supervisors": "/AgendaCenter",
    }),
    ("Hallam Boro", "https://hallamborough.com/", {
        "borough_council": "/AgendaCenter",
    }),
    ("Lewisberry Boro", "https://lewisberryborough.org/", {
        "borough_council": "/AgendaCenter/",
    }),
    ("Manchester Boro", "https://manchesterborough.gov/", {
        "borough_council": "/AgendaCenter/",
    }),
    ("New Salem Boro", "https://newsalemborough.org/", {
        "borough_council": "/AgendaCenter/",
    }),
    ("Seven Valleys Boro", "https://sevenvalleysborough.com/", {
        "borough_council": "/minutes/",
    }),
    ("York Haven Boro", "https://yorkhavenborough.org/", {
        "borough_council": "/AgendaCenter/",
    }),
    ("Fawn Grove Boro", "https://fawngroveborough.org/", {
        "borough_council": "/documents/council-meeting-minutes/",
    }),
    ("Wrightsville Boro", "https://wrightsvilleborough.com/", {
        "borough_council": "/meeting-minutes/",
    }),
    ("Yoe Boro", "https://yoeborough.org/", {
        "borough_council": "/information/minutes/",
    }),
    ("Yorkana Boro", "https://yorkanaborough.com/", {
        "borough_council": "/meeting-minutes/",
    }),
    ("Wellsville Boro", "https://wellsvilleborough.com/", {
        "borough_council": "/boards-commissions/borough-council-agenda-budget/",
    }),
    ("Winterstown Boro", "https://www.winterstownborough.com/", {}),
    ("Loganville Boro", "https://loganvilleborough.com/", {}),

    ("Glen Rock Boro", "https://www.glenrockpa.org/", {
        "borough_council": "/borough-government/council-meeting-minutes-agendas/",
    }),
    ("Chanceford Twp", "https://www.chancefordtwp.com/", {
        "board_of_supervisors": "/Minutes.html",
    }),
    ("Delta Boro", "https://www.deltaborough.us/", {
        "borough_council": "/current-meeting-minutes",
    }),
    ("Dillsburg Boro", "https://dillsburg.com/", {
        "borough_council": "/minutes/",
    }),
    ("Dover Boro", "https://www.doverboroughpa.com/", {
        "borough_council": "/minutes.html",
    }),
    ("Goldsboro Boro", "https://goldsboropa.com/", {
        "borough_council": "/document-library-2/",
    }),
    ("Jacobus Boro", "https://jacobuspa.com/", {
        "borough_council": "/council-meeting/council-meeting-minutes/",
    }),
    ("Jefferson Boro", "https://jeffersonboro.net/", {
        "borough_council": "/council-minutes-agendas",
    }),
    ("Mount Wolf Boro", "https://mtwolfpa.gov/", {
        "borough_council": "/agenda-minutes/",
    }),
    ("New Freedom Boro", "https://newfreedomboro.org/", {
        "borough_council": "/2026-meeting-minutes/",
    }),
    ("Spring Grove Boro", "https://www.springgrovepa.gov/", {
        "borough_council": "/meeting-minutes",
    }),
    ("Stewartstown Boro", "https://www.stewartstown.org/", {
        "borough_council": "/borough-government/",
    }),
    ("Windsor Boro", "https://www.windsorboropa.com/", {
        "borough_council": "/agenda-minutes.html",
    }),
    ("East Manchester Twp", "https://emanchestertwp.com/", {
        "board_of_supervisors": "/boards-and-committees/meetings-archive/",
    }),
    ("Lower Chanceford Twp", "https://lowerchancefordtwppa.gov/", {
        "board_of_supervisors": "/meetings.php",
    }),
    ("West Manheim Twp", "https://westmanheimtwp.com/", {
        "board_of_supervisors": "/boards-comissions/board-of-supervisors/minutes/",
    }),
    ("Warrington Twp", "https://warringtontownship.org/", {
        "board_of_supervisors": "https://warringtontwppa.documents-on-demand.com/?l=5bdff41b150eef11a401000c29a59557",
    }),
    ("Felton Boro", "https://feltonboroughpa.com/", {
        "borough_council": "/documents/minutes/",
    }),

    # === Municipalities with no known website or no minutes page ===
    # These mostly have no web presence or operate via Facebook only.
    ("Cross Roads Boro", None, {}),
    ("Franklintown Boro", None, {}),
    ("Goldsboro Boro", "https://goldsboropa.com/", {}),
    ("Lower Windsor Twp", None, {}),
    ("North Hopewell Twp", None, {}),
    ("Railroad Boro", None, {}),
    ("West York Boro", None, {
        # Google Drive — special handling needed
        "borough_council_2026": "https://drive.google.com/drive/folders/1-TOS70JiL-J0wrZK1R8Ez_lrJWZ3py7L",
        "borough_council_2025": "https://drive.google.com/drive/folders/1_kfY8Fq0lomdpIgul7XtCi6a3MlFAKnR",
    }),
]


def extract_pdf_links(html: str, base_url: str) -> list[dict]:
    """Extract all PDF links and meeting-related links from HTML."""
    soup = BeautifulSoup(html, "html.parser")
    results = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True)

        # Resolve relative URLs
        full_url = urljoin(base_url, href)

        # Is this a PDF?
        is_pdf = bool(re.search(r'\.pdf($|\?)', full_url, re.I))

        # Is this meeting-related?
        combined = (text + " " + href).lower()
        is_meeting = bool(re.search(
            r'minut|agenda|meeting|board|supervis|council|commission|zoning|zhb|planning',
            combined
        ))

        if is_pdf or is_meeting:
            results.append({
                "text": text[:100],
                "url": full_url,
                "is_pdf": is_pdf,
                "is_meeting": is_meeting,
            })

    return results


def survey_page(url: str) -> dict:
    """Fetch a page and extract PDF/meeting links."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        if resp.status_code >= 400:
            return {"status": resp.status_code, "links": [], "error": f"HTTP {resp.status_code}"}

        links = extract_pdf_links(resp.text, resp.url)
        pdf_count = sum(1 for l in links if l["is_pdf"])

        return {
            "status": resp.status_code,
            "final_url": resp.url,
            "links": links,
            "pdf_count": pdf_count,
            "total_links": len(links),
        }
    except Exception as e:
        return {"status": 0, "links": [], "error": str(e)}


def main():
    catalog = []

    for name, base_url, committees in MUNICIPALITIES:
        print(f"\n{'='*60}")
        print(f"{name}")

        if not base_url:
            print(f"  ⚠️ No website")
            catalog.append({"name": name, "base_url": None, "committees": {}, "status": "no_website"})
            continue

        entry = {
            "name": name,
            "base_url": base_url,
            "committees": {},
            "status": "surveyed",
        }

        for committee_type, path in committees.items():
            # Build full URL
            if path.startswith("http"):
                url = path
            else:
                url = base_url.rstrip("/") + path

            print(f"  {committee_type}: {url}")
            result = survey_page(url)

            pdf_links = [l for l in result.get("links", []) if l["is_pdf"]]
            meeting_links = [l for l in result.get("links", []) if l["is_meeting"] and not l["is_pdf"]]

            entry["committees"][committee_type] = {
                "url": url,
                "final_url": result.get("final_url", url),
                "status": result.get("status", 0),
                "pdf_count": len(pdf_links),
                "meeting_link_count": len(meeting_links),
                "pdf_links": pdf_links[:20],  # cap to keep output manageable
                "meeting_links": meeting_links[:10],
                "error": result.get("error"),
            }

            if pdf_links:
                print(f"    ✅ {len(pdf_links)} PDFs found")
                for pl in pdf_links[:3]:
                    print(f"      {pl['text'][:50]:50s} → ...{pl['url'][-40:]}")
            elif meeting_links:
                print(f"    📋 {len(meeting_links)} meeting links (no direct PDFs)")
            else:
                print(f"    ❌ No PDFs or meeting links")

            time.sleep(0.5)  # throttle

        catalog.append(entry)

    # Save catalog
    with open("/tmp/municipality_minutes_catalog.json", "w") as f:
        json.dump(catalog, f, indent=2, default=str)

    # Summary
    print(f"\n{'='*60}")
    print(f"SUMMARY")
    total_with_pdfs = 0
    total_pdfs = 0
    for entry in catalog:
        has_pdfs = any(
            c.get("pdf_count", 0) > 0
            for c in entry.get("committees", {}).values()
        )
        if has_pdfs:
            total_with_pdfs += 1
            total_pdfs += sum(c.get("pdf_count", 0) for c in entry["committees"].values())

    print(f"Municipalities surveyed: {len(catalog)}")
    print(f"With PDFs found: {total_with_pdfs}")
    print(f"Total PDFs discovered: {total_pdfs}")
    print(f"Catalog saved to /tmp/municipality_minutes_catalog.json")


if __name__ == "__main__":
    main()
