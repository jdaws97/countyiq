"""Exercise the actual Caddyfile in a loopback-bound Docker fixture."""
from http.client import HTTPConnection
from pathlib import Path
import subprocess
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def origin(tmp_path_factory):
    directory = tmp_path_factory.mktemp("site-origin")
    (directory / "index.html").write_text("PUBLIC_MARKETING")
    (directory / "app.html").write_text("PRIVATE_APP_SHELL")
    (directory / "assets").mkdir()
    (directory / "assets" / "fixture.js").write_text("STATIC_ASSET")
    name = "countyiq-site-test-" + uuid4().hex[:12]
    try:
        subprocess.run([
            "docker", "run", "--rm", "-d", "--name", name, "--network", "bridge",
            "--add-host", "api:127.0.0.1", "-p", "127.0.0.1::8080",
            "-e", "DOMAIN=countyiq.test",
            "-v", f"{ROOT / 'docker/Caddyfile'}:/etc/caddy/Caddyfile:ro",
            "-v", f"{directory}:/srv:ro", "caddy:2-alpine",
        ], check=True, capture_output=True, text=True)
        address = subprocess.check_output(["docker", "port", name, "8080"], text=True).strip()
        port = int(address.rsplit(":", 1)[1])
        for _ in range(30):
            try:
                if get(port, "localhost", "/healthz").status == 200:
                    break
            except OSError:
                pass
            time.sleep(.1)
        else:
            pytest.fail("Isolated Caddy did not become ready")
        yield port
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)


def get(port, host, path):
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request("GET", path, headers={"Host": host})
        response = connection.getresponse()
        return SimpleNamespace(status=response.status, body=response.read().decode(),
                               headers=dict(response.getheaders()))
    finally:
        connection.close()


@pytest.mark.integration
def test_hosts_select_separate_documents_and_unknown_hosts_fail(origin):
    public = get(origin, "countyiq.test", "/")
    assert public.status == 200 and public.body == "PUBLIC_MARKETING"
    for path in ["/", "/feed", "/property/123", "/index.html"]:
        app = get(origin, "app.countyiq.test", path)
        assert app.status == 200 and app.body == "PRIVATE_APP_SHELL"
        assert app.headers["X-Robots-Tag"] == "noindex, nofollow"
    assert get(origin, "unknown.test", "/").status == 404


@pytest.mark.integration
def test_marketing_never_proxies_any_api_path(origin):
    for path in ["/api", "/api/session", "/api/feed", "/api/ready", "/api/watchspaces"]:
        public = get(origin, "countyiq.test", path)
        assert public.status == 404
        assert public.headers["Cache-Control"] == "no-store"
    # api resolves to this isolated container, with nothing listening on 8000.
    # A 502 proves the app host selected the proxy rather than public HTML.
    assert get(origin, "app.countyiq.test", "/api/meta").status == 502


@pytest.mark.integration
def test_old_product_links_redirect_and_missing_chunks_are_not_html(origin):
    old = get(origin, "countyiq.test", "/property/123?tab=activity")
    assert old.status == 302
    assert old.headers["Location"] == "https://app.countyiq.test/property/123?tab=activity"
    for host in ["countyiq.test", "app.countyiq.test"]:
        missing = get(origin, host, "/assets/missing.js")
        assert missing.status == 404 and missing.headers["Cache-Control"] == "no-store"
        existing = get(origin, host, "/assets/fixture.js")
        assert existing.body == "STATIC_ASSET"
        assert "immutable" in existing.headers["Cache-Control"]
