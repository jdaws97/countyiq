"""Pure helpers for extracting reviewed municipal meeting-page content."""

from __future__ import annotations

from urllib.parse import unquote, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup


def select_listing_region(html: str, *, selector: str = "", heading: str = "") -> str:
    """Isolate a reviewed body's listing before interpreting ambiguous filenames."""
    soup = BeautifulSoup(html, "html.parser")
    if selector:
        return "\n".join(str(element) for element in soup.select(selector))
    if heading:
        for element in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
            if " ".join(element.stripped_strings).casefold() != heading.casefold():
                continue
            fragments = []
            for sibling in element.next_siblings:
                if getattr(sibling, "name", None) in {
                    "h1",
                    "h2",
                    "h3",
                    "h4",
                    "h5",
                    "h6",
                }:
                    break
                fragments.append(str(sibling))
            return "\n".join(fragments)
    return ""


def extract_meeting_page_links(
    html: str,
    base_url: str,
    *,
    path_prefixes: tuple[str, ...],
) -> list[dict[str, str]]:
    """Extract same-origin meeting-page links beneath approved path prefixes.

    The caller supplies the approved path prefixes after reviewing a site's
    information architecture. This helper deliberately does not infer which
    pages are minutes or expand links outside those paths.
    """
    base = urlparse(base_url)
    soup = BeautifulSoup(html, "html.parser")

    document_base = base_url
    base_tag = soup.find("base", href=True)
    if base_tag is not None:
        candidate = urljoin(base_url, base_tag["href"])
        if _same_origin(urlparse(candidate), base):
            document_base = candidate

    records: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if not href or href.startswith(("#", "javascript:")):
            continue

        candidate = urlparse(urljoin(document_base, href))
        if candidate.scheme not in {"http", "https"}:
            continue
        if not _same_origin(candidate, base):
            continue
        if not any(candidate.path.startswith(prefix) for prefix in path_prefixes):
            continue

        url = urlunparse(candidate._replace(fragment=""))
        if url in seen_urls:
            continue
        seen_urls.add(url)

        link_text = " ".join(anchor.stripped_strings)
        records.append(
            {
                "url": url,
                "filename": _html_filename(candidate.path),
                "link_text": link_text,
                "format": "html",
            }
        )
    return records


def extract_html_record_text(html: str, *, content_selector: str) -> str | None:
    """Return readable text from an explicitly selected content region only."""
    soup = BeautifulSoup(html, "html.parser")
    content = soup.select_one(content_selector)
    if content is None:
        return None

    for element in content.select(
        "script, style, nav, footer, form, input, select, textarea, button, "
        "[hidden], [aria-hidden='true'], [role='navigation'], .sr-only, "
        ".screen-reader-text, .published-time"
    ):
        element.decompose()

    lines = [line.strip() for line in content.get_text("\n").splitlines()]
    text = "\n".join(line for line in lines if line)
    return text or None


def _same_origin(candidate, base) -> bool:
    return candidate.scheme == base.scheme and candidate.netloc == base.netloc


def _html_filename(path: str) -> str:
    """Build a stable synthetic HTML filename without losing a page label."""
    tail = unquote(path.rstrip("/").rsplit("/", maxsplit=1)[-1])
    if not tail:
        return "meeting-page.html"
    if tail.lower().endswith((".html", ".htm")):
        return tail
    return f"{tail}.html"
