"""Tests for coherent fingerprint generation."""

import pytest

from persona import generate, validate
from persona.fingerprint import sec_ch_ua
from persona.models import Fingerprint, Proxy
from persona import devices


def test_generated_fingerprint_is_always_coherent():
    # Every fingerprint we produce, across seeds and OSes, must validate clean.
    for seed in range(200):
        fp = generate(seed=seed)
        assert validate(fp) == [], f"seed {seed} produced: {validate(fp)}"


def test_seed_is_reproducible():
    a = generate(seed=42)
    b = generate(seed=42)
    assert a.to_dict() == b.to_dict()


def test_different_seeds_differ():
    a = generate(seed=1)
    b = generate(seed=2)
    assert a.to_dict() != b.to_dict()


@pytest.mark.parametrize("os_key", ["windows", "macos", "linux", "android"])
def test_forced_os_matches_platform_and_gpu(os_key):
    fp = generate(seed=7, os=os_key)
    assert fp.os == os_key
    assert fp.platform == devices.NAV_PLATFORM[os_key]
    assert (fp.webgl_vendor, fp.webgl_renderer) in devices.WEBGL[os_key]


def test_mobile_flag():
    fp = generate(seed=3, mobile=True)
    assert fp.is_mobile is True
    assert fp.os == "android"
    assert "Mobile" in fp.user_agent


def test_proxy_country_steers_locale():
    proxy = Proxy(server="http://x:1", country="PK")
    fp = generate(seed=9, proxy=proxy)
    assert fp.locale == "en-PK"
    assert fp.timezone == "Asia/Karachi"


def test_explicit_locale_wins_over_proxy():
    proxy = Proxy(server="http://x:1", country="PK")
    fp = generate(seed=9, proxy=proxy, locale="de-DE")
    assert fp.locale == "de-DE"
    assert fp.timezone == "Europe/Berlin"


def test_viewport_never_exceeds_screen():
    for seed in range(100):
        fp = generate(seed=seed)
        assert fp.viewport_width <= fp.screen_width
        assert fp.viewport_height <= fp.screen_height


def test_sec_ch_ua_contains_chrome_major():
    fp = generate(seed=5, os="windows")
    major = fp.chrome_version.split(".")[0]
    assert f'"Google Chrome";v="{major}"' in sec_ch_ua(fp)


def test_validate_catches_tampering():
    fp = generate(seed=11, os="windows")
    fp.platform = "MacIntel"  # deliberately break coherence
    problems = validate(fp)
    assert any("platform" in p for p in problems)


def test_fonts_come_from_the_os_font_set():
    for os_key in ("windows", "macos", "linux", "android"):
        fp = generate(seed=3, os=os_key)
        assert fp.fonts, f"{os_key} generated no fonts"
        assert set(fp.fonts) <= set(devices.FONTS[os_key])


def test_validate_catches_a_font_from_another_os():
    fp = generate(seed=12, os="windows")
    fp.fonts = fp.fonts + ["Helvetica Neue"]   # macOS-only
    assert any("fonts" in p for p in validate(fp))


def test_phones_always_have_a_camera_and_microphone():
    for seed in range(30):
        fp = generate(seed=seed, os="android")
        assert fp.cameras > 0 and fp.microphones > 0


def test_validate_catches_a_phone_with_no_camera():
    fp = generate(seed=4, os="android")
    fp.cameras = 0
    assert any("camera" in p for p in validate(fp))


def test_desktops_may_have_no_webcam():
    # A tower with no webcam is normal — the generator must be able to say so.
    assert any(generate(seed=s, os="windows").cameras == 0 for s in range(40))


def test_secondary_signals_survive_a_round_trip():
    fp = generate(seed=8, os="macos")
    assert Fingerprint.from_dict(fp.to_dict()).fonts == fp.fonts


def test_fingerprints_saved_before_these_fields_existed_still_load():
    d = generate(seed=9).to_dict()
    for gone in ("fonts", "cameras", "microphones"):
        del d[gone]
    restored = Fingerprint.from_dict(d)
    assert restored.fonts == [] and restored.cameras == 1


def test_webgl_plausible_accepts_real_host_gpus():
    from persona.fingerprint import webgl_plausible
    # A machine's actual GPU (not in the curated pool) is still coherent for its OS.
    assert webgl_plausible("windows", "Google Inc. (NVIDIA)",
                           "ANGLE (NVIDIA, NVIDIA GeForce RTX 3050 Ti Direct3D11 vs_5_0 ps_5_0, D3D11)")
    assert webgl_plausible("macos", "Google Inc. (Apple)",
                           "ANGLE (Apple, Apple M3 Pro, OpenGL 4.1)")


def test_webgl_plausible_rejects_wrong_os():
    from persona.fingerprint import webgl_plausible
    # An Apple/OpenGL GPU on Windows, or a D3D11 GPU on macOS, is still a tell.
    assert not webgl_plausible("windows", "Google Inc. (Apple)",
                               "ANGLE (Apple, Apple M1, OpenGL 4.1)")
    assert not webgl_plausible("macos", "Google Inc. (NVIDIA)",
                               "ANGLE (NVIDIA, RTX 3060 Direct3D11, D3D11)")


def test_real_screen_size_is_coherent():
    # A profile aligned to an ultrawide keeps a resolution outside the curated list.
    fp = generate(seed=1, os="windows")
    fp.screen_width, fp.screen_height = 3440, 1440
    fp.viewport_width, fp.viewport_height = 3440, 1400
    assert "screen resolution" not in " ".join(validate(fp))
