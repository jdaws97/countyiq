"""County Scout discovery, classification, and monitoring heuristics."""

from __future__ import annotations

import hashlib
import re
import time
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

from countyiq.lib.scout.models import (
    CandidateRecord,
    ObservationRecord,
    ProbeResult,
    RegistryMonitorRecord,
    ScoutSeed,
)
from countyiq.lib.robots import get_public_with_redirects
from countyiq.lib.scout.seeds import get_scout_seeds

PROMOTION_THRESHOLD = 70
MAX_PROBE_BYTES = 1_000_000
USER_AGENT = (
    "CountyScout/0.1 (+https://countyiq.local; "
    "public-interest source discovery for Pennsylvania counties)"
)

RELEVANT_TERMS = (
    "agenda",
    "assessment",
    "bid",
    "bridge",
    "building",
    "code",
    "commissioner",
    "compliance",
    "contract",
    "delinquent",
    "development",
    "efacts",
    "environment",
    "flood",
    "hearing",
    "infrastructure",
    "land",
    "meeting",
    "packet",
    "parcel",
    "permit",
    "plan",
    "procurement",
    "project",
    "proposal",
    "rfp",
    "sale",
    "sediment",
    "solicitation",
    "subdivision",
    "tax",
    "transportation",
    "variance",
    "zoning",
)

CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "development_land_use": (
        "subdivision",
        "land development",
        "plan review",
        "erosion",
        "sediment",
        "growth area",
        "development activity",
    ),
    "planning_zoning": (
        "planning",
        "zoning",
        "rezoning",
        "variance",
        "conditional use",
        "ordinance",
        "hearing board",
    ),
    "permit_activity": (
        "permit",
        "licen",
        "inspection",
        "review list",
        "compliance",
        "regulated site",
    ),
    "procurement_bids": (
        "bid",
        "rfp",
        "rfq",
        "proposal",
        "solicitation",
        "contract",
        "procurement",
    ),
    "tax_sales_delinquency": (
        "tax sale",
        "delinquent",
        "upset sale",
        "repository",
        "judicial sale",
        "tax claim",
    ),
    "assessment_property": (
        "assessment",
        "parcel",
        "property",
        "deed",
        "owner",
        "appraised",
        "value history",
        "parid",
        "pidn",
    ),
    "infrastructure_public_works": (
        "road",
        "bridge",
        "infrastructure",
        "public works",
        "transportation",
        "pennDOT",
        "capital project",
    ),
    "public_decisions": (
        "commissioners",
        "board",
        "agenda",
        "minutes",
        "meeting",
        "packet",
        "resolution",
    ),
    "code_enforcement": (
        "code enforcement",
        "violation",
        "hearing",
        "appeal",
        "inspection",
    ),
    "environmental_site": (
        "dep",
        "efacts",
        "wetland",
        "flood",
        "environment",
        "stormwater",
        "erosion",
        "sediment",
        "regulated site",
    ),
}

CATEGORY_AUDIENCES: dict[str, tuple[str, ...]] = {
    "development_land_use": ("builders", "realtors", "investors", "journalists"),
    "planning_zoning": ("builders", "lawyers", "journalists", "citizens"),
    "permit_activity": ("builders", "property_managers", "lawyers", "investors"),
    "procurement_bids": ("local_businesses", "builders", "journalists"),
    "tax_sales_delinquency": ("investors", "lawyers", "property_managers"),
    "assessment_property": ("realtors", "investors", "lawyers", "property_managers"),
    "infrastructure_public_works": ("builders", "local_businesses", "journalists", "citizens"),
    "public_decisions": ("citizens", "journalists", "local_businesses"),
    "code_enforcement": ("lawyers", "property_managers", "citizens"),
    "environmental_site": ("builders", "lawyers", "journalists", "investors"),
}

CATEGORY_ALERT_TEMPLATES: dict[str, str] = {
    "development_land_use": "Alert when a new subdivision, land-development, or erosion-control item appears in {source_name}.",
    "planning_zoning": "Flag zoning hearings, rezoning packets, or planning agenda changes from {source_name}.",
    "permit_activity": "Watch {source_name} for permit, inspection, or license changes tied to properties in the county.",
    "procurement_bids": "Send same-day bid and RFP alerts from {source_name} to contractors and local vendors.",
    "tax_sales_delinquency": "Trigger distressed-property alerts when {source_name} posts new tax-sale or delinquency records.",
    "assessment_property": "Notify when {source_name} exposes parcel, ownership, or assessed-value changes worth review.",
    "infrastructure_public_works": "Push corridor and project-change alerts when {source_name} updates public works activity.",
    "public_decisions": "Summarize agendas, packets, and votes from {source_name} before most residents see them.",
    "code_enforcement": "Track hearings and enforcement actions surfaced by {source_name}.",
    "environmental_site": "Alert on DEP, stormwater, or site-permit movement detected in {source_name}.",
}

CATEGORY_PRODUCT_TEMPLATES: dict[str, str] = {
    "development_land_use": "Weekly development pipeline brief for builders and investors built from {source_name}.",
    "planning_zoning": "Municipal land-use watchlist product that turns {source_name} into parcel-level zoning intelligence.",
    "permit_activity": "Paid permit-risk dashboard that ties {source_name} changes to affected parcels and owners.",
    "procurement_bids": "Local government bid tracker for York contractors using {source_name}.",
    "tax_sales_delinquency": "Distressed-property scouting feed for investors and attorneys sourced from {source_name}.",
    "assessment_property": "Property-intelligence enrichment layer that converts {source_name} into owner and parcel alerts.",
    "infrastructure_public_works": "Infrastructure opportunity report that turns {source_name} into corridor-impact forecasts.",
    "public_decisions": "Decision-signal digest for citizens, reporters, and public-affairs teams based on {source_name}.",
    "code_enforcement": "Compliance and hearing monitor for landlords and attorneys fed by {source_name}.",
    "environmental_site": "Environmental due-diligence report that turns {source_name} into site-risk alerts.",
}


def build_session() -> requests.Session:
    """Create a requests session with a stable user agent."""
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    return session


def discover_county_sources(
    county_key: str = "york",
    *,
    session: requests.Session | None = None,
) -> tuple[list[CandidateRecord], list[ObservationRecord]]:
    """Probe the active county seed catalog and classify seed + linked sources."""
    seeds = get_scout_seeds(county_key)
    http = session or build_session()
    probe_cache: dict[str, ProbeResult] = {}
    candidates_by_key: dict[str, CandidateRecord] = {}
    observations: list[ObservationRecord] = []

    for seed in seeds:
        seed_probe = _get_or_probe(http, seed.url, probe_cache)
        seed_candidate = classify_candidate(seed, seed_probe, parent_url=None, discovery_method=seed.discovery_method)
        _merge_candidate(candidates_by_key, seed_candidate, preferred=True)
        observations.append(
            build_observation(seed_candidate.source_key, county_key, seed_probe, seed_candidate.extraction_method)
        )

        for child_url, link_text in extract_relevant_links(seed_probe, seed):
            child_probe = _get_or_probe(http, child_url, probe_cache)
            child_candidate = classify_candidate(
                seed,
                child_probe,
                parent_url=seed.url,
                discovery_method="link_crawl",
                link_text=link_text,
            )
            if child_candidate.value_score < 40 and len(child_candidate.categories) < 2:
                continue
            _merge_candidate(candidates_by_key, child_candidate)
            observations.append(
                build_observation(
                    child_candidate.source_key,
                    county_key,
                    child_probe,
                    child_candidate.extraction_method,
                )
            )

    return list(candidates_by_key.values()), observations


def monitor_registry_sources(
    registry_rows: list[dict],
    *,
    session: requests.Session | None = None,
) -> tuple[list[RegistryMonitorRecord], list[ObservationRecord]]:
    """Re-check promoted sources and return registry updates + observations."""
    http = session or build_session()
    updates: list[RegistryMonitorRecord] = []
    observations: list[ObservationRecord] = []

    for row in registry_rows:
        probe = probe_url(http, row["source_url"])
        health_status = _health_from_probe(probe)
        last_hash = row.get("last_content_hash")
        last_changed = bool(last_hash and probe.content_hash and last_hash != probe.content_hash)
        if last_changed:
            health_status = "changed"

        notes = []
        if probe.error:
            notes.append(probe.error)
        if last_changed:
            notes.append("content hash changed")

        extraction_method = row.get("extraction_method") or determine_extraction_method(
            infer_source_type(probe.final_url, probe.content_type, probe.html or "", probe.normalized_text),
            infer_platform(probe.final_url, probe.content_type, probe.html or "", probe.normalized_text),
            probe.html or "",
        )

        updates.append(
            RegistryMonitorRecord(
                source_key=row["source_key"],
                source_url=row["source_url"],
                health_status=health_status,
                probe_status=probe.probe_status,
                status_code=probe.status_code,
                content_hash=probe.content_hash,
                last_changed=last_changed,
                notes="; ".join(notes) if notes else None,
                metadata={
                    "content_type": probe.content_type,
                    "etag": probe.etag,
                    "last_modified": probe.last_modified,
                    "response_ms": probe.response_ms,
                },
            )
        )
        observations.append(
            build_observation(row["source_key"], row["county_key"], probe, extraction_method)
        )

    return updates, observations


def extract_relevant_links(probe: ProbeResult, seed: ScoutSeed) -> list[tuple[str, str]]:
    """Extract same-domain or explicitly allowed links worth probing next."""
    if not probe.html:
        return []

    soup = BeautifulSoup(probe.html, "html.parser")
    ranked_links: list[tuple[int, str, str]] = []
    seen: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()
        if not href or href.startswith(("mailto:", "javascript:", "#")):
            continue

        absolute_url = normalize_url(urljoin(probe.final_url, href))
        if absolute_url in seen:
            continue

        if not _allowed_domain(absolute_url, seed):
            continue

        link_text = " ".join(anchor.get_text(" ", strip=True).split())
        score = _link_relevance_score(absolute_url, link_text)
        if score <= 0:
            continue

        seen.add(absolute_url)
        ranked_links.append((score, absolute_url, link_text))

    ranked_links.sort(key=lambda item: (-item[0], item[1]))
    return [(url, text) for _, url, text in ranked_links[: seed.max_discovery_links]]


def classify_candidate(
    seed: ScoutSeed,
    probe: ProbeResult,
    *,
    parent_url: str | None,
    discovery_method: str,
    link_text: str = "",
) -> CandidateRecord:
    """Classify a source candidate based on URL, content type, and page text."""
    combined_text = " ".join(
        part
        for part in (
            seed.name,
            link_text,
            probe.title,
            probe.final_url,
            probe.normalized_text[:4000],
            seed.notes,
        )
        if part
    )
    categories = sorted(set(seed.category_hints) | infer_categories_from_text(combined_text))
    platform = infer_platform(probe.final_url, probe.content_type, probe.html or "", combined_text)
    source_type = infer_source_type(probe.final_url, probe.content_type, probe.html or "", combined_text)
    extraction_method = determine_extraction_method(source_type, platform, probe.html or "")
    audiences = infer_audiences(categories, seed.audience_hints)
    value_score = score_candidate(seed, probe, categories, source_type, extraction_method)
    risk_level = infer_risk_level(probe, extraction_method, platform)
    source_name = pick_source_name(seed, probe, link_text)
    risk_memo = build_risk_memo(source_name, probe, extraction_method, platform, risk_level)
    alert_examples = build_examples(categories, source_name, CATEGORY_ALERT_TEMPLATES)
    product_examples = build_examples(categories, source_name, CATEGORY_PRODUCT_TEMPLATES)
    confidence = classification_confidence(probe, categories, source_type, platform)
    normalized_url = normalize_url(probe.final_url or probe.requested_url)

    return CandidateRecord(
        source_key=make_source_key(seed.county_key, seed.slug, normalized_url),
        county_key=seed.county_key,
        seed_slug=seed.slug,
        source_name=source_name,
        source_url=probe.final_url or seed.url,
        normalized_url=normalized_url,
        parent_url=parent_url,
        discovery_method=discovery_method,
        source_type=source_type,
        platform=platform,
        extraction_method=extraction_method,
        categories=categories,
        audiences=audiences,
        value_score=value_score,
        risk_level=risk_level,
        risk_memo=risk_memo,
        alert_examples=alert_examples,
        product_examples=product_examples,
        monitor_interval_hours=seed.monitor_interval_hours,
        classification_confidence=confidence,
        metadata={
            "title": probe.title,
            "status_code": probe.status_code,
            "probe_status": probe.probe_status,
            "content_type": probe.content_type,
            "content_hash": probe.content_hash,
            "etag": probe.etag,
            "last_modified": probe.last_modified,
            "response_ms": probe.response_ms,
            "seed_url": seed.url,
            "link_text": link_text,
        },
    )


def select_promoted_candidates(candidates: list[CandidateRecord]) -> list[CandidateRecord]:
    """Promote high-value candidates into the monitored source registry."""
    promoted: list[CandidateRecord] = []
    for candidate in candidates:
        if candidate.value_score < PROMOTION_THRESHOLD:
            continue
        if candidate.metadata.get("status_code") != 200:
            continue
        if candidate.metadata.get("probe_status") not in {"ok", "redirect"}:
            continue
        promoted.append(candidate)
    return promoted


def probe_url(session: requests.Session, url: str) -> ProbeResult:
    """Probe a URL and return normalized metadata for scoring."""
    started = time.monotonic()
    try:
        response = get_public_with_redirects(
            session,
            url,
            timeout=30,
            stream=True,
        )
        status_code = response.status_code
        raw_bytes = _read_limited_body(response)
        response.close()
        response_ms = int((time.monotonic() - started) * 1000)

        content_type = response.headers.get("Content-Type", "").split(";")[0].lower()
        text_content = ""
        html = None
        title = ""

        if _is_textual_response(content_type, response.url):
            text_content = raw_bytes.decode(response.encoding or "utf-8", errors="ignore")
            if "html" in content_type or response.url.lower().endswith((".html", ".htm", ".aspx", ".php")):
                html = text_content
                title = _extract_title(html)

        probe_status = "ok"
        if status_code in {401, 403, 429}:
            probe_status = "blocked"
        elif status_code >= 500:
            probe_status = "error"
        elif response.url != url:
            probe_status = "redirect"

        return ProbeResult(
            requested_url=url,
            final_url=response.url,
            status_code=status_code,
            content_type=content_type or _guess_content_type_from_url(response.url),
            title=title,
            text_content=text_content,
            response_ms=response_ms,
            content_hash=(
                hashlib.sha1(raw_bytes, usedforsecurity=False).hexdigest()
                if raw_bytes
                else None
            ),
            etag=response.headers.get("ETag"),
            last_modified=response.headers.get("Last-Modified"),
            probe_status=probe_status,
            headers=dict(response.headers),
            html=html,
        )
    except requests.RequestException as exc:
        response_ms = int((time.monotonic() - started) * 1000)
        return ProbeResult(
            requested_url=url,
            final_url=url,
            status_code=None,
            content_type="",
            title="",
            text_content="",
            response_ms=response_ms,
            content_hash=None,
            etag=None,
            last_modified=None,
            probe_status="error",
            error=str(exc),
        )


def build_observation(
    source_key: str,
    county_key: str,
    probe: ProbeResult,
    extraction_method: str,
) -> ObservationRecord:
    """Convert a probe into an append-only observation row."""
    notes = probe.error
    return ObservationRecord(
        source_key=source_key,
        county_key=county_key,
        source_url=probe.requested_url,
        probe_status=probe.probe_status,
        status_code=probe.status_code,
        final_url=probe.final_url,
        content_type=probe.content_type,
        extraction_method=extraction_method,
        response_ms=probe.response_ms,
        content_hash=probe.content_hash,
        etag=probe.etag,
        last_modified=probe.last_modified,
        notes=notes,
        metadata={"title": probe.title, "error": probe.error},
    )


def infer_categories_from_text(text: str) -> set[str]:
    """Infer topical categories from URL + title + page text."""
    lowered = text.lower()
    matched = {
        category
        for category, keywords in CATEGORY_KEYWORDS.items()
        if any(keyword in lowered for keyword in keywords)
    }
    return matched


def infer_platform(url: str, content_type: str, html: str, text: str) -> str:
    """Infer the upstream platform or site shape."""
    lowered_url = url.lower()
    lowered_text = text.lower()
    lowered_html = html.lower()
    if "/featureserver/" in lowered_url or "/mapserver/" in lowered_url or "arcgis/rest/services" in lowered_html:
        return "arcgis"
    if "data.pa.gov" in lowered_url or "socrata" in lowered_html or "socrata" in lowered_text:
        return "socrata"
    if lowered_url.endswith(".pdf") or content_type == "application/pdf":
        return "pdf"
    if "cloudflare" in lowered_html or "cf-chl-" in lowered_html:
        return "cloudflare"
    if "__viewstate" in lowered_html or lowered_url.endswith(".aspx"):
        return "aspnet"
    if "granicus" in lowered_url or "granicus" in lowered_text:
        return "granicus"
    if "civicplus" in lowered_html or "bids.aspx" in lowered_url:
        return "civicplus"
    if "<table" in lowered_html:
        return "html_table"
    return "generic_web"


def infer_source_type(url: str, content_type: str, html: str, text: str) -> str:
    """Infer the concrete source shape that County Scout would extract."""
    lowered_url = url.lower()
    lowered_text = text.lower()
    lowered_html = html.lower()
    if "/featureserver/" in lowered_url or "/mapserver/" in lowered_url:
        return "arcgis_rest"
    if "data.pa.gov" in lowered_url or "socrata" in lowered_html:
        return "open_data_api"
    if lowered_url.endswith(".csv") or "csv" in content_type:
        return "csv_download"
    if lowered_url.endswith(".json") or "json" in content_type:
        return "json_api"
    if lowered_url.endswith(".pdf") or content_type == "application/pdf":
        return "pdf_document"
    if "__viewstate" in lowered_html:
        return "aspx_search_portal"
    if "<table" in lowered_html or any(term in lowered_text for term in ("agenda", "minutes", "bid", "rfp", "packet")):
        return "html_index"
    return "html_page"


def determine_extraction_method(source_type: str, platform: str, html: str) -> str:
    """Choose the cheapest viable extraction path."""
    if source_type in {"arcgis_rest", "open_data_api", "csv_download", "json_api"}:
        return "static_http_fetch"
    if source_type in {"pdf_document", "html_index"}:
        return "crawler_static_parser"
    lowered_html = html.lower()
    if platform in {"cloudflare", "aspnet"} or "__next_data__" in lowered_html or "ng-app" in lowered_html:
        return "browser_automation_fallback"
    return "crawler_static_parser"


def infer_audiences(categories: list[str], audience_hints: tuple[str, ...]) -> list[str]:
    """Estimate likely paying or high-value audiences for the source."""
    audiences = set(audience_hints)
    for category in categories:
        audiences.update(CATEGORY_AUDIENCES.get(category, ()))
    return sorted(audiences)


def score_candidate(
    seed: ScoutSeed,
    probe: ProbeResult,
    categories: list[str],
    source_type: str,
    extraction_method: str,
) -> int:
    """Compute an operational value score for County Scout."""
    score = 10
    domain = urlsplit(probe.final_url).netloc.lower()
    if domain.endswith((".gov", ".pa.gov")) or "yorkcountypa.gov" in domain or "ycpc.org" in domain or "yorkccd.org" in domain:
        score += 20
    if probe.status_code == 200:
        score += 10
    elif probe.status_code in {401, 403, 429}:
        score -= 20
    elif probe.status_code and probe.status_code >= 500:
        score -= 15

    score += min(len(categories) * 7, 28)

    structured_bonus = {
        "arcgis_rest": 26,
        "open_data_api": 24,
        "csv_download": 22,
        "json_api": 20,
        "html_index": 14,
        "pdf_document": 10,
        "aspx_search_portal": 10,
        "html_page": 6,
    }
    score += structured_bonus.get(source_type, 0)

    extraction_bonus = {
        "static_http_fetch": 15,
        "crawler_static_parser": 8,
        "browser_automation_fallback": 0,
    }
    score += extraction_bonus.get(extraction_method, 0)

    lower_text = probe.normalized_text.lower()
    if any(term in lower_text for term in ("updated", "posted", "agenda", "minutes", "last modified")):
        score += 5
    if "cloudflare" in lower_text:
        score -= 10
    if "cannot be sold" in lower_text or "terms of use" in lower_text:
        score -= 6
    if any(category in seed.category_hints for category in ("development_land_use", "tax_sales_delinquency", "public_decisions")):
        score += 4

    return max(0, min(score, 100))


def infer_risk_level(probe: ProbeResult, extraction_method: str, platform: str) -> str:
    """Estimate operational and legal fragility."""
    if probe.probe_status in {"blocked", "error"}:
        return "high"
    if extraction_method == "browser_automation_fallback":
        return "medium"
    if platform in {"pdf", "civicplus"}:
        return "medium"
    return "low"


def build_risk_memo(
    source_name: str,
    probe: ProbeResult,
    extraction_method: str,
    platform: str,
    risk_level: str,
) -> str:
    """Build a short risk memo, not a legal ruling."""
    clauses = []
    domain = urlsplit(probe.final_url or probe.requested_url).netloc.lower()
    if domain.endswith((".gov", ".pa.gov")) or "yorkcountypa.gov" in domain or "ycpc.org" in domain:
        clauses.append("Official government or quasi-government domain lowers authenticity risk")
    if probe.probe_status == "blocked":
        clauses.append("current access pattern is blocked, so dependence risk is high")
    elif extraction_method == "browser_automation_fallback":
        clauses.append("cheapest viable extraction is browser automation, which is more fragile than static fetches")
    elif extraction_method == "crawler_static_parser":
        clauses.append("source is public but parser fragility will depend on page and PDF layout stability")
    else:
        clauses.append("source is publicly reachable with a low-cost static fetch path")

    lowered_text = probe.normalized_text.lower()
    if "cannot be sold" in lowered_text or "terms of use" in lowered_text or "disclaimer" in lowered_text:
        clauses.append("page text includes disclaimer-style language that merits manual review before scaling")
    if platform == "cloudflare":
        clauses.append("bot mitigation is present and could require a different acquisition path later")

    memo = f"{source_name}: {'. '.join(clauses)}. Risk level: {risk_level}. Memo only, not legal advice."
    return memo.replace("..", ".")


def build_examples(categories: list[str], source_name: str, templates: dict[str, str]) -> list[str]:
    """Build up to three concrete alert or product ideas."""
    examples = []
    for category in categories:
        template = templates.get(category)
        if not template:
            continue
        examples.append(template.format(source_name=source_name))
        if len(examples) == 3:
            break
    return examples


def classification_confidence(
    probe: ProbeResult,
    categories: list[str],
    source_type: str,
    platform: str,
) -> float:
    """Estimate heuristic confidence for the classification."""
    score = 0.35
    if probe.status_code == 200:
        score += 0.2
    if categories:
        score += min(len(categories) * 0.08, 0.24)
    if source_type in {"arcgis_rest", "open_data_api", "csv_download", "pdf_document"}:
        score += 0.15
    if platform in {"arcgis", "socrata", "aspnet", "pdf"}:
        score += 0.06
    return round(min(score, 0.99), 2)


def pick_source_name(seed: ScoutSeed, probe: ProbeResult, link_text: str) -> str:
    """Choose a stable human-readable name for a candidate source."""
    for value in (probe.title, link_text):
        if value:
            return value[:180]
    path = urlsplit(probe.final_url).path.strip("/")
    if path:
        return path.split("/")[-1].replace("-", " ").replace("_", " ").title()
    return seed.name


def normalize_url(url: str) -> str:
    """Normalize URL casing and strip fragments."""
    parts = urlsplit(url)
    path = parts.path or "/"
    if path != "/":
        path = path.rstrip("/")
    normalized = urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), path, parts.query, "")
    )
    return normalized


def make_source_key(county_key: str, seed_slug: str, normalized_url: str) -> str:
    """Build a stable, human-readable source key."""
    parsed = urlsplit(normalized_url)
    path_slug = slugify(f"{parsed.netloc}-{parsed.path.strip('/') or 'root'}")
    # SHA-1 is retained only for stable, pre-existing source identifiers. It
    # is not used for authentication, signatures, or integrity decisions.
    digest = hashlib.sha1(
        normalized_url.encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()[:8]
    key = f"{county_key}-{seed_slug}-{path_slug[:48]}-{digest}"
    return key[:96]


def slugify(value: str) -> str:
    """Make a DB-safe slug fragment."""
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _get_or_probe(
    session: requests.Session,
    url: str,
    probe_cache: dict[str, ProbeResult],
) -> ProbeResult:
    normalized = normalize_url(url)
    if normalized not in probe_cache:
        probe_cache[normalized] = probe_url(session, normalized)
    return probe_cache[normalized]


def _merge_candidate(
    candidates_by_key: dict[str, CandidateRecord],
    candidate: CandidateRecord,
    *,
    preferred: bool = False,
) -> None:
    existing = candidates_by_key.get(candidate.source_key)
    if existing is None:
        candidates_by_key[candidate.source_key] = candidate
        return
    if preferred or candidate.value_score > existing.value_score:
        candidates_by_key[candidate.source_key] = candidate


def _read_limited_body(response: requests.Response) -> bytes:
    body = bytearray()
    for chunk in response.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        remaining = MAX_PROBE_BYTES - len(body)
        body.extend(chunk[:remaining])
        if len(body) >= MAX_PROBE_BYTES:
            break
    return bytes(body)


def _is_textual_response(content_type: str, url: str) -> bool:
    if not content_type:
        return url.lower().endswith((".html", ".htm", ".txt", ".csv", ".json", ".xml", ".aspx"))
    return content_type.startswith("text/") or content_type in {
        "application/json",
        "application/xml",
        "application/xhtml+xml",
        "application/javascript",
    }


def _extract_title(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    if soup.title and soup.title.string:
        return " ".join(soup.title.string.split())
    heading = soup.find(["h1", "h2"])
    if heading:
        return " ".join(heading.get_text(" ", strip=True).split())
    return ""


def _guess_content_type_from_url(url: str) -> str:
    lowered = url.lower()
    if lowered.endswith(".pdf"):
        return "application/pdf"
    if lowered.endswith(".csv"):
        return "text/csv"
    if lowered.endswith(".json"):
        return "application/json"
    return ""


def _allowed_domain(url: str, seed: ScoutSeed) -> bool:
    candidate_domain = urlsplit(url).netloc.lower()
    seed_domain = urlsplit(seed.url).netloc.lower()
    if _domains_match(candidate_domain, seed_domain):
        return True
    return any(_domains_match(candidate_domain, allowed) for allowed in seed.allow_external_domains)


def _domains_match(left: str, right: str) -> bool:
    left = left.lower()
    right = right.lower()
    return left == right or left.endswith(f".{right}") or right.endswith(f".{left}")


def _link_relevance_score(url: str, link_text: str) -> int:
    parsed = urlsplit(url)
    lowered = f"{parsed.path} {parsed.query} {link_text}".lower()
    score = sum(1 for term in RELEVANT_TERMS if term in lowered)
    if lowered.endswith((".pdf", ".csv", ".json")):
        score += 2
    if "/featureserver/" in lowered or "/mapserver/" in lowered or "data.pa.gov" in lowered:
        score += 3
    return score


def _health_from_probe(probe: ProbeResult) -> str:
    if probe.probe_status == "blocked":
        return "blocked"
    if probe.probe_status == "error":
        return "error"
    if probe.status_code == 200:
        return "healthy"
    return "degraded"
