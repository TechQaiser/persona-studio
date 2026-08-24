"""End-to-end proof that an extension really loads, headless included.

The unit tests pin the flags and the channel; only a real browser proves the
extension's content script actually ran. Needs Playwright's chromium, so it
skips when the browser isn't installed (``playwright install chromium``).
"""

import http.server
import socketserver
import threading

import pytest

from persona import generate
from persona.models import Profile
from persona.store import ProfileStore

pytest.importorskip("playwright")

MANIFEST = """{
  "manifest_version": 3,
  "name": "probe",
  "version": "1.0",
  "content_scripts": [{"matches": ["<all_urls>"], "js": ["cs.js"],
                       "run_at": "document_start"}]
}"""
# Content scripts run in an isolated world, so the marker has to land somewhere
# the page's own JS can see it.
CONTENT_SCRIPT = "document.documentElement.setAttribute('data-probe', 'loaded');"


@pytest.fixture
def local_site():
    """A page on http:// — content scripts don't run on about:blank."""
    class Handler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body>ok</body></html>")

        def log_message(self, *a):
            pass

    with socketserver.TCPServer(("127.0.0.1", 0), Handler) as srv:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        yield f"http://127.0.0.1:{srv.server_address[1]}/"
        srv.shutdown()


@pytest.fixture
def extension(tmp_path):
    d = tmp_path / "probe-ext"
    d.mkdir()
    (d / "manifest.json").write_text(MANIFEST, encoding="utf-8")
    (d / "cs.js").write_text(CONTENT_SCRIPT, encoding="utf-8")
    return str(d)


@pytest.mark.parametrize("headless", [True, False], ids=["headless", "headed"])
def test_extension_content_script_runs(tmp_path, local_site, extension, headless):
    from persona.drivers import get
    if headless is False and not _has_display():
        pytest.skip("no display for a windowed launch")

    store = ProfileStore(tmp_path)
    prof = Profile(name="probe", fingerprint=generate(seed=7), extensions=[extension])
    try:
        pw, ctx, page = get("playwright")(prof, store, headless=headless, keep_open=True)
    except Exception as e:                      # browser not downloaded
        pytest.skip(f"chromium unavailable: {str(e).splitlines()[0][:80]}")
    try:
        page.goto(local_site)
        marker = page.evaluate("() => document.documentElement.getAttribute('data-probe')")
    finally:
        ctx.close()
        pw.stop()
    assert marker == "loaded"


def _has_display():
    import os
    import sys
    return sys.platform != "linux" or bool(os.environ.get("DISPLAY"))
