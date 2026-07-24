"""DNS-leak grading. The live check needs the network and a third-party
service, so what's pinned here is the pure rule that turns observed resolvers
into pass/fail — the part that decides whether a leak happened."""

from persona.probe import _grade_dns


def _row(cc, kind="dns", asn="AS1"):
    return {"ip": "1.1.1.1", "country": cc, "country_code": cc, "asn": asn, "type": kind}


def test_no_proxy_country_is_baseline_only():
    # Without a proxy country to compare against there's nothing to "leak" past;
    # the resolvers are just reported, and the check passes.
    res = _grade_dns([_row("US"), _row("US")], proxy_country=None)
    assert res["ok"] is True
    assert res["countries"] == ["US"]


def test_all_resolvers_in_proxy_country_passes():
    res = _grade_dns([_row("DE"), _row("DE")], proxy_country="DE")
    assert res["ok"] is True
    assert any("no ISP leak" in c["name"] for c in res["checks"])


def test_resolver_outside_proxy_country_is_a_leak():
    # DE proxy but one resolver answers from the US — the lookup escaped the tunnel.
    res = _grade_dns([_row("DE"), _row("US")], proxy_country="DE")
    assert res["ok"] is False
    leak = next(c for c in res["checks"] if "proxy country" in c["name"])
    assert leak["ok"] is False
    assert "US" in leak["detail"]


def test_ignores_non_resolver_rows():
    rows = [_row("DE"), {"type": "ip", "country_code": "DE"},
            {"type": "conclusion", "ip": "|"}]
    res = _grade_dns(rows, proxy_country="DE")
    assert len(res["resolvers"]) == 1
    assert res["ok"] is True


def test_no_resolvers_observed_fails_the_first_check():
    res = _grade_dns([{"type": "ip", "country_code": "US"}], proxy_country="US")
    assert res["ok"] is False
    assert res["checks"][0]["ok"] is False
