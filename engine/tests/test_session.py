"""Tests for the pure session/cookie-health analyzer."""

from persona import session


NOW = 1_700_000_000.0
DAY = 86400.0


def _cookie(name, domain, expires, **over):
    c = {"name": name, "value": "x", "domain": domain, "path": "/",
         "expires": expires, "httpOnly": False, "secure": True, "sameSite": "Lax"}
    c.update(over)
    return c


def test_empty_jar():
    r = session.analyze([], now=NOW)
    assert r["status"] == "empty"
    assert r["total"] == 0 and r["logins"] == []


def test_counts_session_persistent_expired_and_expiring():
    cookies = [
        _cookie("a", ".example.com", -1),                 # session cookie
        _cookie("b", ".example.com", NOW + 30 * DAY),     # healthy persistent
        _cookie("c", ".example.com", NOW - DAY),          # already expired
        _cookie("d", ".example.com", NOW + 2 * DAY),      # expiring soon (<7d)
    ]
    r = session.analyze(cookies, now=NOW)
    assert r["total"] == 4
    assert r["session"] == 1
    assert r["persistent"] == 3
    assert r["expired"] == 1
    assert r["expiringSoon"] == 1


def test_status_priority_expiring_beats_stale():
    # A soon-to-expire cookie is the more actionable warning.
    cookies = [_cookie("a", ".x.com", NOW - DAY),         # expired
               _cookie("b", ".x.com", NOW + DAY)]         # expiring soon
    assert session.analyze(cookies, now=NOW)["status"] == "expiring"


def test_status_stale_when_only_expired():
    cookies = [_cookie("a", ".x.com", NOW - DAY),
               _cookie("b", ".x.com", NOW + 90 * DAY)]
    assert session.analyze(cookies, now=NOW)["status"] == "stale"


def test_status_ok_when_all_current():
    cookies = [_cookie("a", ".x.com", NOW + 90 * DAY)]
    assert session.analyze(cookies, now=NOW)["status"] == "ok"


def test_detects_live_facebook_login():
    cookies = [_cookie("c_user", ".facebook.com", NOW + 90 * DAY),
               _cookie("xs", ".facebook.com", NOW + 90 * DAY)]
    assert "Facebook" in session.analyze(cookies, now=NOW)["logins"]


def test_expired_auth_cookie_is_not_a_live_login():
    cookies = [_cookie("c_user", ".facebook.com", NOW - DAY)]
    assert "Facebook" not in session.analyze(cookies, now=NOW)["logins"]


def test_session_auth_cookie_counts_as_live():
    # A session-scoped auth token still means "logged in right now".
    cookies = [_cookie("li_at", ".linkedin.com", -1)]
    assert "LinkedIn" in session.analyze(cookies, now=NOW)["logins"]


def test_subdomain_matches_the_service():
    cookies = [_cookie("sessionid", "www.instagram.com", NOW + DAY * 30)]
    assert "Instagram" in session.analyze(cookies, now=NOW)["logins"]


def test_unrelated_cookie_named_like_auth_does_not_match_wrong_domain():
    # "sessionid" on some random site isn't an Instagram login.
    cookies = [_cookie("sessionid", ".randomsite.com", NOW + DAY * 30)]
    assert session.analyze(cookies, now=NOW)["logins"] == []


def test_domains_are_deduped_and_bare():
    cookies = [_cookie("a", ".example.com", -1), _cookie("b", "example.com", -1)]
    assert session.analyze(cookies, now=NOW)["domains"] == ["example.com"]
