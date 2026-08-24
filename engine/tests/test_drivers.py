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


# ---- geolocation + WebRTC coherence --------------------------------------
from persona.models import Proxy
from persona.drivers import _geolocation_for, _webrtc_arg


def _p(country=None, locale="en-US"):
    proxy = Proxy(server="http://h:1", country=country) if country else None
    return Profile(name="g", fingerprint=generate(seed=1, locale=locale), proxy=proxy)


def test_geolocation_follows_proxy_country():
    geo = _geolocation_for(_p(country="DE"))
    assert (round(geo["latitude"]), round(geo["longitude"])) == (53, 13)  # Berlin


def test_geolocation_falls_back_to_locale_without_proxy():
    geo = _geolocation_for(_p(locale="fr-FR"))
    assert round(geo["latitude"]) == 49 and round(geo["longitude"]) == 2   # Paris


def test_geolocation_none_for_unknown_country():
    assert _geolocation_for(_p(country="ZZ")) is None


def test_webrtc_forces_proxy_when_one_is_set():
    assert "disable_non_proxied_udp" in _webrtc_arg(_p(country="US"))[0]


def test_webrtc_hides_local_ip_without_proxy():
    assert "default_public_interface_only" in _webrtc_arg(_p())[0]


# ---- headless has to use the full browser, not the headless shell -------
# Playwright's default headless binary is chromium_headless_shell, which cannot
# load extensions at all and announces itself as HeadlessChrome over CDP. The
# "chromium" channel is the same download in --headless=new mode.


class _FakeContext:
    def __init__(self):
        self.pages = []
        self.closed = False

    def add_init_script(self, script):
        pass

    def new_page(self):
        page = _FakePage()
        self.pages.append(page)
        return page

    def close(self):
        self.closed = True


class _FakePage:
    url = "about:blank"

    def goto(self, *a, **k):
        pass


class _FakePlaywright:
    def __init__(self, seen):
        self.seen = seen

        class _Chromium:
            @staticmethod
            def launch_persistent_context(**kwargs):
                seen.update(kwargs)
                return _FakeContext()

        self.chromium = _Chromium()

    def start(self):
        return self

    def stop(self):
        pass


def _launch_kwargs(headless):
    from persona.drivers import _launch_playwright_like
    from persona.store import ProfileStore
    import tempfile

    seen = {}
    with tempfile.TemporaryDirectory() as tmp:
        prof = Profile(name="k", fingerprint=generate(seed=3))
        _launch_playwright_like(lambda: _FakePlaywright(seen), prof,
                                ProfileStore(tmp), headless, keep_open=True)
    return seen


def test_headless_uses_the_full_chromium_channel():
    assert _launch_kwargs(headless=True)["channel"] == "chromium"


def test_headed_leaves_the_channel_alone():
    assert _launch_kwargs(headless=False)["channel"] is None
