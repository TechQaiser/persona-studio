"""Cookie parsing / serialising.

The browser round-trip needs a real Chromium, so these tests cover the part that
has to be right regardless of engine: understanding the formats people paste in.
"""

import json

from persona import cookies as ck


EXTENSION_EXPORT = [
    {
        "domain": ".facebook.com", "expirationDate": 1893456000.5, "hostOnly": False,
        "httpOnly": True, "name": "c_user", "path": "/", "sameSite": "no_restriction",
        "secure": True, "session": False, "storeId": "0", "value": "1000123",
    },
    {
        "domain": "www.facebook.com", "name": "sb", "path": "/", "sameSite": "lax",
        "secure": False, "session": True, "value": "abc",
    },
]


def test_normalize_extension_cookie():
    c = ck.normalize(EXTENSION_EXPORT[0])
    assert c == {
        "name": "c_user", "value": "1000123", "domain": ".facebook.com", "path": "/",
        "expires": 1893456000.5, "httpOnly": True, "secure": True, "sameSite": "None",
    }


def test_session_cookie_gets_minus_one():
    assert ck.normalize(EXTENSION_EXPORT[1])["expires"] == -1


def test_samesite_none_requires_secure():
    # Chromium rejects SameSite=None on a non-secure cookie, so we downgrade it
    # rather than hand the browser something it will refuse.
    c = ck.normalize({"name": "a", "value": "1", "domain": "x.com",
                      "sameSite": "no_restriction", "secure": False})
    assert c["sameSite"] == "Lax"


def test_incomplete_cookies_are_dropped():
    assert ck.normalize({"value": "no name", "domain": "x.com"}) is None
    assert ck.normalize({"name": "no domain"}) is None
    assert ck.normalize("not a dict") is None


def test_parse_extension_json_list():
    jar = ck.parse(json.dumps(EXTENSION_EXPORT))
    assert [c["name"] for c in jar] == ["c_user", "sb"]


def test_parse_playwright_storage_state():
    state = {"cookies": EXTENSION_EXPORT, "origins": []}
    assert len(ck.parse(json.dumps(state))) == 2


def test_parse_single_cookie_object():
    assert ck.parse(json.dumps(EXTENSION_EXPORT[0]))[0]["name"] == "c_user"


def test_parse_empty_input():
    assert ck.parse("") == []
    assert ck.parse("   \n ") == []


def test_parse_netscape():
    text = (
        "# Netscape HTTP Cookie File\n"
        "\n"
        ".facebook.com\tTRUE\t/\tTRUE\t1893456000\tc_user\t1000123\n"
        "#HttpOnly_.facebook.com\tTRUE\t/\tTRUE\t1893456000\txs\tsecret\n"
        "# a real comment\n"
    )
    jar = ck.parse(text)
    assert [c["name"] for c in jar] == ["c_user", "xs"]
    assert jar[0]["httpOnly"] is False
    assert jar[1]["httpOnly"] is True      # the #HttpOnly_ prefix is not a comment
    assert jar[1]["domain"] == ".facebook.com"


def test_netscape_round_trip():
    jar = ck.parse(json.dumps(EXTENSION_EXPORT))
    again = ck.parse(ck.to_netscape(jar))
    assert [(c["name"], c["value"], c["domain"]) for c in again] == \
           [(c["name"], c["value"], c["domain"]) for c in jar]


def test_dumps_json_is_storage_state():
    out = json.loads(ck.dumps(ck.parse(json.dumps(EXTENSION_EXPORT))))
    assert set(out) == {"cookies", "origins"}
    assert out["cookies"][0]["name"] == "c_user"


def test_read_file(tmp_path):
    f = tmp_path / "cookies.json"
    f.write_text(json.dumps(EXTENSION_EXPORT), encoding="utf-8")
    assert len(ck.read_file(f)) == 2


def test_write_nothing_is_a_noop():
    # No cookies means no browser launch at all — safe to call without an engine.
    assert ck.write(None, None, []) == 0
