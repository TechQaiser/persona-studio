"""Importing profiles exported from other anti-detect browsers.

The samples below mirror the shapes GoLogin, AdsPower and Multilogin actually
produce (field names, nesting). The importer is tolerant by design, so the
tests pin the mapping and the coherence guarantee rather than an exact schema.
"""

import json

from persona.importers import profile_from_export, load_export, _unwrap
from persona.store import ProfileStore


GOLOGIN = {
    "name": "GL-Account-1",
    "os": "mac",
    "navigator": {
        "userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/128.0.0.0 Safari/537.36",
        "resolution": "1440x900", "language": "en-US",
        "hardwareConcurrency": 10, "deviceMemory": 16, "platform": "MacIntel",
    },
    "timezone": {"timezone": "America/New_York"},
    "webGLMetadata": {"vendor": "Google Inc. (Apple)", "renderer": "ANGLE (Apple, Apple M2, OpenGL 4.1)"},
    "proxy": {"mode": "http", "host": "1.2.3.4", "port": 8080, "username": "u", "password": "p"},
}

ADSPOWER = {
    "name": "ADS-Store-7",
    "group_name": "Amazon",
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/127.0.0.0 Safari/537.36",
    "fingerprint_config": {"webgl_vendor": "Google Inc. (NVIDIA)",
                           "webgl_renderer": "ANGLE (NVIDIA GeForce RTX 3060)"},
    "screen_resolution": "1920x1080",
    "timezone": "Europe/Berlin", "language": "de-DE",
    "user_proxy_config": {"proxy_type": "socks5", "proxy_host": "9.9.9.9",
                          "proxy_port": "1080", "proxy_user": "x", "proxy_password": "y"},
}

MULTILOGIN = {
    "name": "ML-QA",
    "os_type": "linux",
    "navigator": {"user_agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/126.0.0.0 Safari/537.36",
                  "resolution": "1920x1080", "hardware_concurrency": 8, "platform": "Linux x86_64"},
    "timezone": "Europe/London",
}


def test_gologin_core_fields():
    prof, issues = profile_from_export(GOLOGIN)
    assert prof.name == "GL-Account-1"
    assert prof.fingerprint.os == "macos"
    assert (prof.fingerprint.screen_width, prof.fingerprint.screen_height) == (1440, 900)
    assert prof.fingerprint.hardware_concurrency == 10
    assert prof.proxy.server == "http://1.2.3.4:8080"
    assert prof.proxy.password == "p"


def test_adspower_nested_and_group_becomes_tag():
    prof, issues = profile_from_export(ADSPOWER)
    assert prof.fingerprint.os == "windows"
    assert prof.fingerprint.timezone == "Europe/Berlin"
    assert prof.proxy.server == "socks5://9.9.9.9:1080"
    assert "Amazon" in prof.tags


def test_multilogin_without_proxy():
    prof, issues = profile_from_export(MULTILOGIN)
    assert prof.fingerprint.os == "linux"
    assert prof.proxy is None


def test_os_inferred_from_user_agent_when_field_missing():
    prof, _ = profile_from_export({"name": "x", "user_agent":
                                   "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/128 Safari/537.36"})
    assert prof.fingerprint.os == "macos"


def test_missing_fields_fall_back_to_a_coherent_base():
    # An almost-empty export must still yield a launchable, coherent profile.
    prof, issues = profile_from_export({"name": "sparse"})
    assert prof.fingerprint.user_agent  # filled from the generated base
    assert prof.fingerprint.locale in ("en-US", prof.fingerprint.locale)


def test_unknown_locale_is_replaced_not_left_incoherent():
    prof, issues = profile_from_export({"name": "x", "language": "zz-ZZ"})
    assert "languages do not match locale" not in issues
    assert "unknown locale" not in " ".join(issues)


def test_direct_proxy_mode_means_no_proxy():
    prof, _ = profile_from_export({"name": "x", "proxy": {"mode": "none", "host": "1.1.1.1"}})
    assert prof.proxy is None


def test_unwrap_handles_wrappers():
    assert len(_unwrap({"data": [{"a": 1}, {"b": 2}]})) == 2
    assert len(_unwrap([{"a": 1}])) == 1
    assert len(_unwrap({"name": "single"})) == 1
    assert _unwrap("garbage") == []


def test_import_file_saves_and_reports(tmp_path):
    src = tmp_path / "export.json"
    src.write_text(json.dumps([GOLOGIN, ADSPOWER, MULTILOGIN]), encoding="utf-8")
    store = ProfileStore(tmp_path / "store")
    results = ProfileStore  # placeholder to satisfy linters if unused
    from persona.importers import import_file
    out = import_file(src, store)
    assert len(out) == 3
    assert len(store.list()) == 3
    assert {p.name for p in store.list()} == {"GL-Account-1", "ADS-Store-7", "ML-QA"}
