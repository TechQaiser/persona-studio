"""devicePixelRatio: it must fit the device — Macs are Retina, phones carry their
panel's exact ratio, Windows shows its display-scaling step."""

import pytest

from persona import validate
from persona.fingerprint import archetype_dpr, generate, pixel_ratio
from persona.models import Fingerprint


def test_macs_are_retina():
    for seed in range(1, 30):
        assert pixel_ratio(generate(os="macos", seed=seed)) == 2


def test_windows_125_percent_is_the_1536_screen():
    fp = generate(os="windows", seed=1)
    fp.screen_width, fp.screen_height, fp.device_scale_factor = 1536, 864, 0
    assert pixel_ratio(fp) == 1.25
    fp.screen_width, fp.screen_height = 1920, 1080
    assert pixel_ratio(fp) == 1


def test_phone_dpr_comes_from_the_handset():
    seen = {}
    for seed in range(1, 80):
        fp = generate(os="android", seed=seed)
        model = fp.user_agent.split("; ")[2].split(")")[0]
        seen.setdefault(model, set()).add(pixel_ratio(fp))
    assert seen["Pixel 7"] == {2.625}
    assert seen["SM-G991B"] == {3.0}
    assert all(len(v) == 1 for v in seen.values())


def test_old_profiles_without_the_field_derive_it():
    d = generate(os="macos", seed=3).to_dict()
    d.pop("device_scale_factor")
    fp = Fingerprint.from_dict(d)
    assert fp.device_scale_factor == 0 and pixel_ratio(fp) == 2


@pytest.mark.parametrize("os,dpr,bad", [("macos", 1.0, True), ("macos", 2.0, False),
                                        ("windows", 1.33, True), ("windows", 1.5, False),
                                        ("android", 1.0, True)])
def test_validate_flags_impossible_ratios(os, dpr, bad):
    fp = generate(os=os, seed=5)
    fp.device_scale_factor = dpr
    assert any("devicePixelRatio" in i for i in validate(fp)) is bad


def test_no_gologin_epsilon_trick():
    # A real Retina Mac reports exactly 2; 2.00000001 would itself be a tell.
    assert archetype_dpr(generate(os="macos", seed=1)) == 2.0


def test_dashboard_dpr_is_derived_unless_pinned():
    from persona.server import to_engine_profile
    base = {"id": "x", "name": "n", "os": "macOS", "screen": "1440x900",
            "webglRenderer": "ANGLE (Apple, Apple M1, OpenGL 4.1)", "locale": "en-US"}
    assert pixel_ratio(to_engine_profile(base).fingerprint) == 2
    assert pixel_ratio(to_engine_profile({**base, "dpr": 1.5}).fingerprint) == 1.5
