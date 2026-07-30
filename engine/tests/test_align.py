"""Auto-adjust: aligning a profile to what its browser actually presents.

`align_to_reality` needs a real browser to *observe*, but the reconciliation
logic — turn an observation into a rewritten, coherent fingerprint that now
grades clean — is pure. We stub the observation and pin that logic, which is the
part that would silently do the wrong thing if it broke.
"""

from persona import generate, validate, devices
from persona.models import Profile
from persona.store import ProfileStore
from persona.probe import (
    align_to_reality, _os_from_platform, _chrome_from_ua, _vendor_from_renderer,
)
import persona.probe as probe


def test_os_inferred_from_platform():
    assert _os_from_platform("Win32", "macos") == "windows"
    assert _os_from_platform("MacIntel", "windows") == "macos"
    assert _os_from_platform("Linux x86_64", "windows") == "linux"
    assert _os_from_platform("Linux armv8l", "windows") == "android"
    assert _os_from_platform("", "linux") == "linux"   # falls back


def test_chrome_pulled_from_ua():
    assert _chrome_from_ua("... Chrome/127.0.0.0 Safari/537.36") == "127.0.0.0"
    assert _chrome_from_ua("no version here") is None


def test_vendor_guessed_from_renderer():
    assert "NVIDIA" in _vendor_from_renderer("ANGLE (NVIDIA, RTX 3050 Ti, D3D11)")
    assert "Apple" in _vendor_from_renderer("ANGLE (Apple, Apple M1, OpenGL 4.1)")


# A macOS profile running under an engine that shows the real *Windows* host —
# exactly the cloak-on-Windows situation that scores grade D.
def _windows_host_seen(profile):
    fp = profile.fingerprint
    return {
        "webdriver": False, "webdriverOwn": False, "hasChrome": True, "plugins": 3,
        "userAgent": fp.user_agent,               # the (mac) UA the engine was fed
        "platform": "Win32",
        "languages": ["en-US"],
        "cores": 8, "memory": 8,
        "screenW": 1920, "screenH": 1080,
        "timezone": fp.timezone,
        "toStringNative": True, "permissionsAgree": True,
        "canvasStable": True, "canvasEmpty": False,
        "webglVendor": "Google Inc. (NVIDIA)",
        "webglRenderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3050 Ti Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "fontKnown": False, "fontAlien": False,
        "cameras": 1, "microphones": 1,
        "fontsRendered": ["Segoe UI", "Calibri", "Consolas", "Arial", "Tahoma"],
    }


def test_align_reconciles_mac_profile_to_windows_host(tmp_path, monkeypatch):
    store = ProfileStore(tmp_path)
    prof = Profile(name="mac-on-win", fingerprint=generate(seed=1, os="macos", locale="en-US"),
                   engine="cloak")
    store.save(prof)

    monkeypatch.setattr(probe, "_observe", lambda *a, **k: _windows_host_seen(prof))
    res = align_to_reality(prof, store, engine="cloak")

    # The identity now reads as the machine it actually runs on.
    assert res["os"] == "windows"
    assert prof.fingerprint.os == "windows"
    assert prof.fingerprint.platform == "Win32"
    assert prof.fingerprint.hardware_concurrency == 8
    assert prof.fingerprint.device_memory == 8
    assert "RTX 3050 Ti" in prof.fingerprint.webgl_renderer
    assert prof.fingerprint.user_agent.startswith("Mozilla/5.0 (Windows NT")

    # And it grades clean — the whole point.
    assert res["before"]["score"] < res["after"]["score"]
    assert res["after"]["score"] == 100
    assert set(res["changed"]) >= {"os", "platform", "userAgent", "cores", "memory",
                                   "webglRenderer", "fonts"}


def test_aligned_profile_is_coherent(tmp_path, monkeypatch):
    store = ProfileStore(tmp_path)
    prof = Profile(name="p", fingerprint=generate(seed=2, os="macos", locale="en-US"))
    store.save(prof)
    monkeypatch.setattr(probe, "_observe", lambda *a, **k: _windows_host_seen(prof))
    align_to_reality(prof, store, engine="cloak")
    # A real host GPU/screen must not trip the coherence validator.
    assert validate(prof.fingerprint) == []


def test_align_is_a_noop_when_already_matching(tmp_path, monkeypatch):
    store = ProfileStore(tmp_path)
    prof = Profile(name="p", fingerprint=generate(seed=3, os="windows", locale="en-US"),
                   engine="playwright")
    store.save(prof)
    fp = prof.fingerprint

    # A profile whose browser presents exactly what it declares.
    seen = {
        "webdriver": False, "webdriverOwn": False, "hasChrome": True, "plugins": 3,
        "userAgent": fp.user_agent, "platform": fp.platform,
        "languages": list(fp.languages), "cores": fp.hardware_concurrency,
        "memory": fp.device_memory, "screenW": fp.screen_width, "screenH": fp.screen_height,
        "timezone": fp.timezone, "toStringNative": True, "permissionsAgree": True,
        "canvasStable": True, "canvasEmpty": False,
        "webglVendor": fp.webgl_vendor, "webglRenderer": fp.webgl_renderer,
        "fontKnown": True, "fontAlien": False,
        "cameras": fp.cameras, "microphones": fp.microphones,
        "fontsRendered": list(fp.fonts),
    }
    monkeypatch.setattr(probe, "_observe", lambda *a, **k: seen)
    res = align_to_reality(prof, store, engine="playwright")
    assert res["changed"] == []
    assert res["after"]["score"] == 100


def _fully_consistent_windows_seen(tz):
    """An observation where every check would pass — so the only thing keeping
    the grade below A is whether align picks up the timezone."""
    return {
        "webdriver": False, "webdriverOwn": False, "hasChrome": True, "plugins": 3,
        "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "platform": devices.NAV_PLATFORM["windows"], "languages": ["en-US", "en"],
        "cores": 8, "memory": 8, "timezone": tz,
        "toStringNative": True, "permissionsAgree": True,
        "canvasStable": True, "canvasEmpty": False,
        "webglVendor": "Google Inc. (NVIDIA)",
        "webglRenderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "screenW": 1920, "screenH": 1080,
        "fontsRendered": [devices.FONTS["windows"][0]],
        "cameras": 1, "microphones": 1,
    }


def test_align_moves_timezone_and_locale_to_reality(tmp_path, monkeypatch):
    # A US profile (America/New_York) on a machine whose real clock is Karachi —
    # the case where auto-adjust used to stop at B because the timezone check
    # stayed failed. Now align should follow the clock and reach A.
    store = ProfileStore(tmp_path)
    prof = Profile(name="flow", engine="cloak",
                   fingerprint=generate(seed=1, os="windows", locale="en-US"))
    store.save(prof)
    monkeypatch.setattr(probe, "_observe", lambda *a, **k: _fully_consistent_windows_seen("Asia/Karachi"))

    res = align_to_reality(prof, store, engine="cloak")

    assert prof.fingerprint.timezone == "Asia/Karachi"
    assert prof.fingerprint.locale == "en-PK"       # the coherent locale for that zone
    assert "timezone" in res["changed"]
    assert res["after"]["grade"] == "A" and res["after"]["score"] == 100
    assert validate(prof.fingerprint) == []          # still coherent


def test_align_keeps_timezone_when_no_locale_models_it(tmp_path, monkeypatch):
    # A zone Persona doesn't model: leave it alone rather than break coherence.
    store = ProfileStore(tmp_path)
    prof = Profile(name="flow", engine="cloak",
                   fingerprint=generate(seed=1, os="windows", locale="en-US"))
    store.save(prof)
    monkeypatch.setattr(probe, "_observe", lambda *a, **k: _fully_consistent_windows_seen("Antarctica/Troll"))

    res = align_to_reality(prof, store, engine="cloak")

    assert prof.fingerprint.timezone == devices.LOCALES["en-US"][0]   # unchanged
    assert "timezone" not in res["changed"]
