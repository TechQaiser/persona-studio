"""Probe helpers that don't need a browser.

The full trust report and proxy test need a real Chromium, so what's covered
here is the logic that decides *what counts as a problem* — the part that would
silently give wrong answers if it broke.
"""

from persona.probe import _is_private, check_leaks, check_tls


def test_private_ipv4_ranges():
    for ip in ["10.0.0.1", "192.168.1.5", "172.16.4.4", "172.31.255.1",
               "127.0.0.1", "169.254.10.1"]:
        assert _is_private(ip), ip


def test_public_ipv4_is_not_private():
    for ip in ["8.8.8.8", "1.1.1.1", "172.32.0.1", "192.169.0.1", "203.0.113.9"]:
        assert not _is_private(ip), ip


def test_private_ipv6():
    assert _is_private("fd12::1")
    assert _is_private("fe80::1")
    assert _is_private("::1")


def test_public_ipv6_is_not_private():
    assert not _is_private("2001:4860:4860::8888")


def test_garbage_is_treated_as_private():
    # Never report a leak we aren't sure about — a false alarm here would send
    # someone chasing a proxy problem that doesn't exist.
    assert _is_private("not-an-ip")
    assert _is_private("999.1.1")


class FakePage:
    def __init__(self, ips):
        self._ips = ips

    def evaluate(self, _js, *args):
        return {"supported": True, "ips": self._ips}


class FakeContext:
    def __init__(self, ips):
        self.pages = [FakePage(ips)]


# A page that returns a canned TLS parse result, so we exercise check_tls's
# scoring logic without a browser or the network.
class FakeTlsPage:
    def __init__(self, parsed):
        self._parsed = parsed
        self.goto_calls = []

    def goto(self, url, **kw):
        self.goto_calls.append(url)

    def evaluate(self, _js, *args):
        return self._parsed


class FakeTlsContext:
    def __init__(self, parsed):
        self.pages = [FakeTlsPage(parsed)]


CHROME_TLS = {
    "ja3": "771,4865-4866-4867,0-23-65281,29-23,0", "ja3Hash": "abc123",
    "ja4": "t13d1516h2_8daaf6152771_d8a2da3f94cd", "http2": "hash",
    "grease": True, "greaseKnown": True, "cipherCount": 15,
}


def test_tls_real_chromium_passes_every_check():
    res = check_tls(None, None, context=FakeTlsContext(CHROME_TLS))
    assert res["ok"] is True
    assert res["ja4"].startswith("t13")
    assert all(c["ok"] for c in res["checks"])


def test_tls_flags_a_non_tls13_handshake():
    bad = {**CHROME_TLS, "ja4": "t12d0810h1_aaaa_bbbb"}
    res = check_tls(None, None, context=FakeTlsContext(bad))
    assert not res["ok"]
    assert any("TLS 1.3" in c["name"] and not c["ok"] for c in res["checks"])


def test_tls_flags_missing_http2():
    bad = {**CHROME_TLS, "ja4": "t13d1516_aaaa_bbbb"}
    res = check_tls(None, None, context=FakeTlsContext(bad))
    assert any("HTTP/2" in c["name"] and not c["ok"] for c in res["checks"])


def test_tls_flags_missing_grease_when_ciphers_were_exposed():
    bad = {**CHROME_TLS, "grease": False, "greaseKnown": True}
    res = check_tls(None, None, context=FakeTlsContext(bad))
    assert any("GREASE" in c["name"] and not c["ok"] for c in res["checks"])


def test_tls_does_not_penalise_grease_when_service_hides_ciphers():
    # A service that returns only a ja3 string can't reveal GREASE (it's
    # stripped per spec) — absence must not be scored as a failure.
    unknown = {**CHROME_TLS, "grease": False, "greaseKnown": False}
    res = check_tls(None, None, context=FakeTlsContext(unknown))
    assert not any("GREASE" in c["name"] for c in res["checks"])
    assert res["grease"] is None


def test_tls_reports_error_when_no_service_answers():
    res = check_tls(None, None, context=FakeTlsContext(None))
    assert res["ok"] is False
    assert "error" in res


def test_private_addresses_are_not_a_leak():
    res = check_leaks(None, None, context=FakeContext(["192.168.1.7", "10.0.0.2"]))
    assert res["exposed"] == []
    assert res["checks"][0]["ok"]


def test_public_address_that_is_not_the_exit_ip_is_a_leak():
    res = check_leaks(None, None, context=FakeContext(["203.0.113.9"]), exit_ip="8.8.8.8")
    assert res["exposed"] == ["203.0.113.9"]
    assert not res["checks"][0]["ok"]


def test_the_exit_ip_itself_is_not_a_leak():
    # Seeing the proxy's own address is expected; that's where traffic comes from.
    res = check_leaks(None, None, context=FakeContext(["8.8.8.8"]), exit_ip="8.8.8.8")
    assert res["exposed"] == []
    assert res["checks"][0]["ok"]
