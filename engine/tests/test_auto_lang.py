"""Languages that follow the proxy's exit IP (opt-in per profile)."""

from persona import geo
from persona.fingerprint import generate
from persona.models import Profile, Proxy
from persona.server import to_dashboard_profile, to_engine_profile


def _profile(auto_lang=True):
    return Profile(name="p", fingerprint=generate(os="windows", locale="en-US", seed=2),
                   proxy=Proxy(server="http://1.2.3.4:8080"), auto_lang=auto_lang)


def test_accept_languages_shape():
    assert geo.accept_languages("DE") == ["de-DE", "de", "en-US", "en"]
    assert geo.accept_languages("br") == ["pt-BR", "pt", "en-US", "en"]
    assert geo.accept_languages("GB") == ["en-GB", "en", "en-US"]
    assert geo.accept_languages("UK") == ["en-GB", "en", "en-US"]
    assert geo.accept_languages("US") == ["en-US", "en"]
    assert geo.accept_languages("ZZ") is None
    assert geo.accept_languages(None) is None


def test_launch_languages_follow_the_exit_country_only_when_opted_in():
    seen = {"country": "FR"}
    assert geo.launch_languages(_profile(True), seen) == ("fr-FR", ["fr-FR", "fr", "en-US", "en"])
    off = _profile(False)
    assert geo.launch_languages(off, seen) == (off.fingerprint.locale, list(off.fingerprint.languages))
    unknown = _profile(True)
    assert geo.launch_languages(unknown, {"country": None})[0] == unknown.fingerprint.locale


def test_trust_expects_the_launch_languages(monkeypatch):
    from persona import probe
    prof = _profile(True)
    monkeypatch.setattr(probe, "launch_languages", lambda p, g=None: ("de-DE", ["de-DE", "de", "en-US", "en"]))
    assert probe._launch_langs(prof, "playwright") == ["de-DE", "de", "en-US", "en"]
    assert probe._launch_langs(prof, "camoufox") is None
    assert probe._launch_langs(_profile(False), "playwright") is None

    fp = prof.fingerprint
    seen = {"webdriver": False, "webdriverOwn": False, "hasChrome": True, "plugins": 5,
            "userAgent": fp.user_agent, "platform": fp.platform, "cores": fp.hardware_concurrency,
            "memory": 8, "timezone": fp.timezone, "toStringNative": True, "permissionsAgree": True,
            "canvasStable": True, "webglVendor": fp.webgl_vendor, "webglRenderer": fp.webgl_renderer,
            "languages": ["de-DE", "de", "en-US", "en"]}
    rep = probe._grade(fp, seen, "playwright", None, ["de-DE", "de", "en-US", "en"])
    lang = next(c for c in rep["checks"] if c["name"].startswith("Languages"))
    assert lang["ok"] and lang["name"] == "Languages match the IP location"


def test_round_trips():
    prof = _profile(True)
    assert Profile.from_dict(prof.to_dict()).auto_lang is True
    d = prof.to_dict()
    d.pop("auto_lang")
    assert Profile.from_dict(d).auto_lang is False
    dash = {**to_dashboard_profile(prof), "id": prof.id}
    assert dash["autoLang"] is True
    assert to_engine_profile(dash).auto_lang is True


def test_cli_edit_auto_lang(tmp_path):
    from persona.cli import main
    from persona.store import ProfileStore
    store = ProfileStore(tmp_path)
    prof = _profile(False)
    store.save(prof)
    assert main(["--data-dir", str(tmp_path), "edit", prof.id, "--auto-lang", "on"]) == 0
    assert store.get(prof.id).auto_lang is True
