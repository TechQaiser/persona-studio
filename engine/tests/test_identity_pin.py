"""Pinned engine identities: a profile must present the same device every launch,
and the patched engines must present *Persona's* fingerprint, not their own."""

import json

import pytest

from persona import drivers
from persona.drivers import (CAMOUFOX_FP_FILE, CLOAK_SEED_FILE,
                             camoufox_fingerprint, cloak_identity_args)
from persona.fingerprint import generate, navigator_device_memory
from persona.models import Profile


def _flags(args):
    return dict(a.split("=", 1) for a in args if "=" in a)


def _prof(os="windows", seed=7):
    return Profile(name="p", fingerprint=generate(os=os, seed=seed))


# ---- navigator.deviceMemory --------------------------------------------------
@pytest.mark.parametrize("ram,shown", [(32, 8), (16, 8), (12, 8), (8, 8), (6, 4),
                                       (4, 4), (3, 2), (1, 1), (0.5, 0.5), (0.1, 0.25)])
def test_device_memory_is_what_chrome_presents(ram, shown):
    assert navigator_device_memory(ram) == shown


def test_stealth_script_never_reports_raw_ram():
    from persona.stealth import build_init_script
    fp = generate(os="windows", seed=1)
    fp.device_memory = 16
    assert '"deviceMemory": 8' in build_init_script(fp)


# ---- CloakBrowser --------------------------------------------------------------
def test_cloak_presents_persona_fingerprint(tmp_path):
    p = _prof()
    fp = p.fingerprint
    f = _flags(cloak_identity_args(p, tmp_path))
    assert f["--fingerprint-platform"] == "windows"
    assert f["--fingerprint-hardware-concurrency"] == str(fp.hardware_concurrency)
    assert float(f["--fingerprint-device-memory"]) == navigator_device_memory(fp.device_memory)
    assert f["--fingerprint-screen-width"] == str(fp.screen_width)
    assert f["--fingerprint-screen-height"] == str(fp.screen_height)
    assert f["--fingerprint-gpu-renderer"] == fp.webgl_renderer
    assert f["--fingerprint-gpu-vendor"] == fp.webgl_vendor


def test_cloak_seed_is_stable_and_per_profile(tmp_path):
    a1 = _flags(cloak_identity_args(_prof(seed=7), tmp_path))["--fingerprint"]
    a2 = _flags(cloak_identity_args(_prof(seed=7), tmp_path))["--fingerprint"]
    b = _flags(cloak_identity_args(_prof(seed=8), tmp_path))["--fingerprint"]
    assert a1 == a2 != b
    assert 10000 <= int(a1) <= 99999


def test_cloak_keeps_an_existing_seed(tmp_path):
    # A profile Cloak already opened keeps its seed: re-seeding would swap the
    # device under a logged-in session.
    (tmp_path / CLOAK_SEED_FILE).write_text("54321\n")
    assert "--fingerprint" not in _flags(cloak_identity_args(_prof(), tmp_path))


def test_cloak_macos_profile(tmp_path):
    f = _flags(cloak_identity_args(_prof(os="macos"), tmp_path))
    assert f["--fingerprint-platform"] == "macos"
    assert "Apple" in f["--fingerprint-gpu-renderer"] or "Intel" in f["--fingerprint-gpu-renderer"]


def test_cloak_unsupported_os_only_pins_seed(tmp_path):
    f = _flags(cloak_identity_args(_prof(os="linux"), tmp_path))
    assert set(f) == {"--fingerprint"}


# ---- Camoufox ----------------------------------------------------------------
def test_camoufox_fingerprint_generated_once_then_reused(tmp_path, monkeypatch):
    calls = []

    def fake_generate(os=None, screen=None, **_):
        calls.append(os)
        return {"navigator": {"userAgent": f"ff-{len(calls)}"}, "os": os}

    fake = type("M", (), {"generate_fingerprint": staticmethod(fake_generate),
                          "Screen": lambda **kw: kw})
    monkeypatch.setitem(__import__("sys").modules, "camoufox.fingerprints", fake)
    monkeypatch.setitem(__import__("sys").modules, "camoufox", type("P", (), {})())

    p = _prof(os="macos")
    first = camoufox_fingerprint(p, tmp_path)
    second = camoufox_fingerprint(p, tmp_path)
    assert first == second and calls == ["macos"]
    assert json.loads((tmp_path / CAMOUFOX_FP_FILE).read_text())["os"] == "macos"


def test_camoufox_real_fingerprint_round_trips(tmp_path):
    pytest.importorskip("camoufox")
    from camoufox.fingerprints import identity_salt
    p = _prof()
    first = camoufox_fingerprint(p, tmp_path)
    again = camoufox_fingerprint(p, tmp_path)
    # Camoufox salts every per-identity draw from the fingerprint it's given, so
    # an equal salt means the same fonts, voices, GPU and noise each launch.
    assert identity_salt(first) == identity_salt(again)
    assert first["screen"]["width"] <= p.fingerprint.screen_width

