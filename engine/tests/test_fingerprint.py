"""Tests for coherent fingerprint generation."""

import pytest

from persona import generate, validate
from persona.fingerprint import sec_ch_ua
from persona.models import Proxy
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
