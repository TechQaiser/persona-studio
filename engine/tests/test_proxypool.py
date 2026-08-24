"""Proxy-pool parsing and the engine<->dashboard profile round-trip for import.

The health check needs the network, so what's pinned here is the parser (which
has to read every layout a vendor might hand you) and the reverse mapping that
turns an imported engine profile back into the dashboard shape.
"""

from persona.proxypool import parse_line, parse_many
from persona.server import ProxyPool, to_dashboard_profile, to_engine_profile
from persona import generate
from persona.models import Profile, Proxy


def test_parse_host_port():
    assert parse_line("1.2.3.4:8080") == {
        "type": "HTTP", "host": "1.2.3.4", "port": "8080",
        "user": None, "pass": None, "country": None}


def test_parse_host_port_user_pass():
    p = parse_line("1.2.3.4:8080:alice:secret")
    assert (p["host"], p["port"], p["user"], p["pass"]) == ("1.2.3.4", "8080", "alice", "secret")


def test_parse_user_pass_at_host():
    p = parse_line("alice:secret@1.2.3.4:8080")
    assert (p["user"], p["pass"], p["host"], p["port"]) == ("alice", "secret", "1.2.3.4", "8080")


def test_parse_scheme_and_socks():
    assert parse_line("socks5://host.io:1080")["type"] == "SOCKS5"
    assert parse_line("https://u:p@host.io:3128")["type"] == "HTTPS"


def test_parse_trailing_country_code():
    assert parse_line("1.2.3.4:8080:u:p:US")["country"] == "US"
    assert parse_line("1.2.3.4:8080:DE")["country"] == "DE"


def test_parse_rejects_junk():
    assert parse_line("not a proxy") is None
    assert parse_line("# comment") is None
    assert parse_line("") is None
    assert parse_line("host-without-port") is None


def test_parse_many_skips_bad_lines():
    text = "1.2.3.4:8080\n# a comment\n\ngarbage\nuser:pass@5.6.7.8:3128\n"
    out = parse_many(text)
    assert len(out) == 2
    assert {p["host"] for p in out} == {"1.2.3.4", "5.6.7.8"}


def test_dashboard_engine_round_trip_preserves_identity():
    prof = Profile(name="rt", engine="cloak",
                   fingerprint=generate(seed=5, os="macos", locale="de-DE"),
                   proxy=Proxy(server="socks5://9.9.9.9:1080", username="x",
                               password="y", country="DE"), tags=["t"])
    d = to_dashboard_profile(prof)
    assert d["os"] == "macOS" and d["engine"] == "cloak"
    assert d["proxy"]["type"] == "SOCKS5" and d["proxy"]["host"] == "9.9.9.9"
    assert d["proxy"]["country"] == "DE"

    back = to_engine_profile(d)
    assert back.fingerprint.os == "macos"
    assert back.fingerprint.webgl_renderer == prof.fingerprint.webgl_renderer
    assert back.proxy.server.startswith("socks5://9.9.9.9")


def test_import_shaped_profile_is_coherent():
    # A profile produced by the importer must survive to_dashboard_profile ->
    # to_engine_profile and still validate.
    from persona.importers import profile_from_export
    from persona.fingerprint import validate
    prof, _ = profile_from_export({"name": "gl", "os": "mac",
                                   "navigator": {"userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/128.0.0.0 Safari/537.36"}})
    d = to_dashboard_profile(prof)
    assert validate(to_engine_profile(d).fingerprint) == []


def test_sticky_session_proxies_are_not_collapsed(tmp_path):
    # Sticky-session vendors serve one host:port for the whole pool and pick the
    # exit node from the credentials - some vary the username, some only the
    # password. Every line is a distinct proxy, so none may be deduped away.
    pool = ProxyPool(tmp_path)
    lines = ",".join(
        f"socks5://gate.example.com:32325:acct-1:token-{cc}-{n}"
        for cc in ("IT", "BE", "UK", "TR") for n in range(1, 5)
    )
    added = pool.add_many(parse_many(lines))
    assert len(added) == 16
    assert len(pool.list()) == 16

    # Re-importing the same list is still a no-op.
    assert pool.add_many(parse_many(lines)) == []
    assert len(pool.list()) == 16
