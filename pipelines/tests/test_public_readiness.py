"""Exercise deployment health checks against a real local HTTP endpoint."""

import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("status,body,expected", [
    (200, b'{"status":"ok"}', True),
    (200, b'{ "status": "ok" }', True),
    (302, b'', False),
    (200, b'<html>Sign in</html>', False),
    (200, b'{"status":"unavailable"}', False),
    (503, b'{"detail":"database unavailable"}', False),
])
def test_public_readiness_requires_successful_api_response(status, body, expected):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(status)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run(
            ["bash", "-c", 'source docker/lib/operations.sh; countyiq_check_public_readiness "$1"',
             "readiness-test", f"http://127.0.0.1:{server.server_port}/api/ready"],
            cwd=ROOT, capture_output=True, text=True,
            env={**os.environ, "COUNTYIQ_PUBLIC_READY_CURL_CONFIG": ""},
        )
        assert (result.returncode == 0) == expected, result.stderr
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
