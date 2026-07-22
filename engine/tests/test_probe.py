"""Probe helpers that don't need a browser.

The full trust report and proxy test need a real Chromium, so what's covered
here is the logic that decides *what counts as a problem* — the part that would
silently give wrong answers if it broke.
"""

from persona.probe import _is_private, check_leaks


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
