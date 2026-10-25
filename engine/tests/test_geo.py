"""Launch-time geo: timezone + geolocation follow the proxy's exit IP, and each
profile gets its own stable spot instead of one shared capital-city point."""

from persona import geo
from persona.fingerprint import generate
from persona.models import Profile, Proxy

CHICAGO = {"ip": "203.0.113.7", "timezone": "America/Chicago", "lat": 41.88, "lon": -87.63,
           "country": "US", "city": "Chicago"}


def _p(seed=1, country="US", locale="en-US", proxy=True):
    px = Proxy(server="http://h:1", country=country) if proxy else None
    return Profile(name="g", fingerprint=generate(seed=seed, locale=locale), proxy=px)


def setup_function(_):
    geo.clear_cache()


def test_exit_ip_sets_timezone_and_city():
    g = geo.launch_geo(_p(), lookup=lambda px: CHICAGO)
    assert g["source"] == "exit-ip" and g["timezone"] == "America/Chicago"
    assert g["ip"] == "203.0.113.7"
    assert abs(g["geolocation"]["latitude"] - 41.88) < 0.1
    assert abs(g["geolocation"]["longitude"] + 87.63) < 0.1


def test_each_profile_gets_its_own_stable_spot():
    a1 = geo.launch_geo(_p(seed=1), lookup=lambda px: CHICAGO)["geolocation"]
    geo.clear_cache()
    a2 = geo.launch_geo(_p(seed=1), lookup=lambda px: CHICAGO)["geolocation"]
    b = geo.launch_geo(_p(seed=2), lookup=lambda px: CHICAGO)["geolocation"]
    assert a1 == a2
    assert (a1["latitude"], a1["longitude"]) != (b["latitude"], b["longitude"])
    assert 20 <= a1["accuracy"] <= 100


def test_lookup_is_cached_for_the_trust_run():
    calls = []
    p = _p()
    for _ in range(3):
        geo.launch_geo(p, lookup=lambda px: calls.append(1) or CHICAGO)
    assert len(calls) == 1


def test_falls_back_to_profile_when_lookup_fails():
    p = _p(country="DE", locale="de-DE")
    g = geo.launch_geo(p, lookup=lambda px: None)
    assert g["source"] == "profile" and g["timezone"] == p.fingerprint.timezone
    assert round(g["geolocation"]["latitude"]) in (52, 53)      # near Berlin, jittered


def test_no_proxy_uses_locale_and_never_looks_up():
    g = geo.launch_geo(_p(locale="fr-FR", proxy=False), lookup=lambda px: 1 / 0)
    assert g["source"] == "profile" and round(g["geolocation"]["latitude"]) in (48, 49)


def test_unknown_country_has_no_geolocation():
    assert geo.launch_geo(_p(country="ZZ", locale="xx-XX"), lookup=lambda px: None)["geolocation"] is None


def test_socks_proxy_is_not_looked_up_directly():
    assert geo.lookup_exit(Proxy(server="socks5://h:1")) is None


def test_parses_both_echo_services():
    ipwho = {"ip": "1.2.3.4", "success": True, "country_code": "us", "city": "X",
             "latitude": 1, "longitude": 2, "timezone": {"id": "America/Denver"}}
    ipapi = {"ip": "1.2.3.4", "country_code": "US", "latitude": 1, "longitude": 2,
             "timezone": "America/Denver"}
    assert geo._parse(ipwho)["timezone"] == geo._parse(ipapi)["timezone"] == "America/Denver"
    assert geo._parse({"success": False}) is None


def test_trust_expects_the_launch_timezone():
    from persona.probe import _grade
    fp = generate(seed=1, locale="en-US")
    seen = {"webdriver": False, "webdriverOwn": False, "hasChrome": True, "plugins": 3,
            "userAgent": fp.user_agent, "platform": fp.platform, "languages": list(fp.languages),
            "cores": fp.hardware_concurrency, "memory": 8, "screenW": fp.screen_width,
            "screenH": fp.screen_height, "timezone": "America/Chicago", "toStringNative": True,
            "permissionsAgree": True, "canvasStable": True}
    tz = next(c for c in _grade(fp, seen, "camoufox", "America/Chicago")["checks"] if "Timezone" in c["name"])
    assert tz["ok"] and "IP location" in tz["name"]
