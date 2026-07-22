"""Tests for the pluggable launch-driver registry."""

from persona import drivers
from persona.models import Profile
from persona.fingerprint import generate


def test_builtin_engines_registered():
    names = drivers.names()
    assert "playwright" in names
    assert "patchright" in names
    assert "camoufox" in names


def test_availability_map_covers_all():
    avail = drivers.available()
    assert set(avail) == set(drivers.names())
    assert all(isinstance(v, bool) for v in avail.values())


def test_unknown_engine_raises():
    try:
        drivers.get("does-not-exist")
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "Unknown engine" in str(e)


def test_uninstalled_engine_raises_with_hint():
    # camoufox isn't a test dependency, so this should raise a helpful error.
    if not drivers.is_installed("camoufox"):
        try:
            drivers.get("camoufox")
            assert False, "expected RuntimeError"
        except RuntimeError as e:
            assert "camoufox" in str(e)


def test_profile_defaults_to_playwright_engine():
    p = Profile(name="x", fingerprint=generate(os="windows"))
    assert p.engine == "playwright"
    # round-trips through serialization
    assert Profile.from_dict(p.to_dict()).engine == "playwright"
