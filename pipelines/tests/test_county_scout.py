from countyiq.lib.scout.discovery import (
    classify_candidate,
    extract_relevant_links,
    infer_categories_from_text,
)
from countyiq.lib.scout.models import ProbeResult
from countyiq.lib.scout.seeds import get_scout_seeds


def test_york_seed_catalog_covers_core_domains():
    seeds = get_scout_seeds("york")
    slugs = {seed.slug for seed in seeds}
    assert "gis-hub" in slugs
    assert "assessment" in slugs
    assert "county-bids" in slugs
    assert "tax-sale" in slugs
    assert "commissioners" in slugs
    assert "efacts" in slugs
    assert "building-permit-reports" in slugs


def test_infer_categories_detects_priority_signal_terms():
    categories = infer_categories_from_text(
        "York County subdivision activity report and rezoning agenda with permit review"
    )
    assert "development_land_use" in categories
    assert "planning_zoning" in categories
    assert "permit_activity" in categories


def test_extract_relevant_links_filters_noise_and_keeps_signal():
    seed = next(seed for seed in get_scout_seeds("york") if seed.slug == "county-home")
    probe = ProbeResult(
        requested_url=seed.url,
        final_url=seed.url,
        status_code=200,
        content_type="text/html",
        title="York County Government",
        text_content="",
        response_ms=150,
        content_hash="abc",
        etag=None,
        last_modified=None,
        probe_status="ok",
        html="""
            <html>
                <body>
                    <a href="/Bids.aspx">County Bids</a>
                    <a href="/528/Tax-Sale-Information">Tax Sale Information</a>
                    <a href="/contact">Contact Us</a>
                    <a href="https://example.com/random">Random</a>
                </body>
            </html>
        """,
    )
    links = extract_relevant_links(probe, seed)
    urls = [url for url, _ in links]
    assert "https://yorkcountypa.gov/Bids.aspx" in urls
    assert "https://yorkcountypa.gov/528/Tax-Sale-Information" in urls
    assert all("example.com" not in url for url in urls)
    assert all("/contact" not in url for url in urls)


def test_classify_arcgis_source_prefers_static_fetch():
    seed = next(seed for seed in get_scout_seeds("york") if seed.slug == "gis-hub")
    probe = ProbeResult(
        requested_url="https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/Parcels/FeatureServer/0",
        final_url="https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA/Parcels/FeatureServer/0",
        status_code=200,
        content_type="application/json",
        title="Parcels",
        text_content='{"currentVersion":11.1,"name":"Parcels"}',
        response_ms=220,
        content_hash="abc123",
        etag=None,
        last_modified=None,
        probe_status="ok",
    )
    candidate = classify_candidate(seed, probe, parent_url=seed.url, discovery_method="link_crawl")
    assert candidate.source_type == "arcgis_rest"
    assert candidate.platform == "arcgis"
    assert candidate.extraction_method == "static_http_fetch"
    assert candidate.value_score >= 75


def test_classify_aspx_portal_falls_back_to_browser():
    seed = next(seed for seed in get_scout_seeds("york") if seed.slug == "assessment")
    probe = ProbeResult(
        requested_url=seed.url,
        final_url=seed.url,
        status_code=200,
        content_type="text/html",
        title="York County Assessment Search",
        text_content="Assessment Search __VIEWSTATE owner value history delinquent taxes",
        response_ms=400,
        content_hash="hash",
        etag=None,
        last_modified=None,
        probe_status="ok",
        html="""
            <html>
                <head><title>York County Assessment Search</title></head>
                <body>
                    <input type="hidden" name="__VIEWSTATE" value="x" />
                    <div>Owner name, delinquent taxes, value history</div>
                </body>
            </html>
        """,
    )
    candidate = classify_candidate(seed, probe, parent_url=None, discovery_method="seed")
    assert candidate.source_type == "aspx_search_portal"
    assert candidate.extraction_method == "browser_automation_fallback"
    assert candidate.risk_level in {"medium", "high"}
    assert candidate.alert_examples
