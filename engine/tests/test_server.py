"""Tests for the dashboard<->engine conversion in server.py.

These don't need FastAPI installed — to_engine_profile / dashboard_coherence
live at module level and only touch the engine core.
"""

from persona import validate
from persona.server import to_engine_profile, dashboard_coherence


BASE = {
    "id": "abc123",
    "name": "Test",
    "os": "Windows",
    "screen": "1920x1080",
    "cores": 8,
    "memory": 16,
    "webglRenderer": "ANGLE (NVIDIA GeForce RTX 3060 Direct3D11)",
    "locale": "en-US",
    "timezone": "America/New_York",
    "browserVersion": "128.0.0.0",
    "userAgent": "Mozilla/5.0 test",
}


def test_converts_os_and_screen():
    fp = to_engine_profile(BASE).fingerprint
    assert fp.os == "windows"
    assert (fp.screen_width, fp.screen_height) == (1920, 1080)
    assert fp.viewport_height < fp.screen_height


def test_maps_gpu_to_real_engine_string():
    fp = to_engine_profile(BASE).fingerprint
    assert "RTX 3060" in fp.webgl_renderer
    assert fp.webgl_vendor.startswith("Google Inc.")


def test_converted_profile_is_coherent():
    # A well-formed dashboard profile must produce a launchable, valid fingerprint.
    assert validate(to_engine_profile(BASE).fingerprint) == []
    assert dashboard_coherence(BASE) == []


def test_proxy_is_converted():
    d = dict(BASE, proxy={"type": "SOCKS5", "host": "h.proxy.io", "port": "1080",
                          "user": "u", "pass": "p", "country": "US"})
    prof = to_engine_profile(d)
    assert prof.proxy is not None
    assert prof.proxy.server == "socks5://h.proxy.io:1080"
    assert prof.proxy.username == "u"


def test_validate_tolerates_missing_id():
    d = {k: v for k, v in BASE.items() if k != "id"}
    # should not raise even without an id (used by the /validate endpoint)
    assert isinstance(dashboard_coherence(d), list)
