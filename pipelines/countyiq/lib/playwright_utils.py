"""Headless Chromium launcher with consistent settings for scraping.

Used by the remaining Playwright-based scraper assets (sheriff sales, public
proceedings' JS-rendered municipal sites).
"""

from contextlib import contextmanager

from dagster import get_dagster_logger
from playwright.sync_api import sync_playwright


# Shared browser launch args — reduce memory use on the production VPS.
BROWSER_ARGS = [
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-default-apps",
    "--disable-sync",
    "--disable-translate",
    "--mute-audio",
    "--no-first-run",
]

DEFAULT_VIEWPORT = {"width": 1280, "height": 720}
DEFAULT_TIMEOUT_MS = 30_000


@contextmanager
def browser_context(
    headless: bool = True,
    viewport: dict | None = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
):
    """Launch a Chromium browser and yield a page, then clean up.

    Usage::

        with browser_context() as page:
            page.goto("https://example.com")
            html = page.content()

    Args:
        headless: Run in headless mode (default True).
        viewport: Browser viewport size dict. Defaults to 1280x720.
        timeout_ms: Default navigation/action timeout in milliseconds.
    """
    log = get_dagster_logger()
    vp = viewport or DEFAULT_VIEWPORT

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=headless,
            args=BROWSER_ARGS,
        )
        ctx = browser.new_context(
            viewport=vp,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        ctx.set_default_timeout(timeout_ms)
        page = ctx.new_page()

        log.info(f"Browser launched (headless={headless}, viewport={vp})")
        try:
            yield page
        finally:
            ctx.close()
            browser.close()
            log.info("Browser closed")
