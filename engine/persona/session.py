"""
Session / cookie health.

A profile manager's real value is keeping many logged-in accounts alive. But a
profile can *look* fine in the grid while its session has quietly died — the auth
cookie expired last week, or it's a day away from expiring. You only find out
when you open the browser and it's logged out, which is exactly when you didn't
want to find out.

This module reads a profile's cookies and answers the questions that matter:
  * How many cookies are expired, or expiring in the next few days?
  * Which services does this profile actually have a *live* login for?

Everything here is a pure function over a list of Playwright-shaped cookies
(see :mod:`persona.cookies`), so it's cheap to test and reuse. The one call that
touches a browser — reading the live jar — lives in :func:`check`.
"""

from __future__ import annotations

import time
from typing import Optional

from .models import Profile
from .store import ProfileStore

# Known "you are logged in" cookies, keyed by service. A login counts as *live*
# only if at least one of these cookies is present, on a matching domain, and
# not expired. Names are the session tokens each site actually sets.
LOGIN_COOKIES: dict[str, dict] = {
    "Google":    {"domains": ["google.com"], "names": ["SID", "SAPISID", "__Secure-1PSID", "__Secure-3PSID"]},
    "Facebook":  {"domains": ["facebook.com"], "names": ["c_user", "xs"]},
    "Instagram": {"domains": ["instagram.com"], "names": ["sessionid", "ds_user_id"]},
    "X":         {"domains": ["x.com", "twitter.com"], "names": ["auth_token"]},
    "TikTok":    {"domains": ["tiktok.com"], "names": ["sessionid", "sid_tt"]},
    "LinkedIn":  {"domains": ["linkedin.com"], "names": ["li_at"]},
    "Reddit":    {"domains": ["reddit.com"], "names": ["reddit_session", "token_v2"]},
    "Amazon":    {"domains": ["amazon.com"], "names": ["at-main", "sess-at-main", "sess-at-main-eu"]},
    "GitHub":    {"domains": ["github.com"], "names": ["user_session", "__Host-user_session_same_site"]},
    "YouTube":   {"domains": ["youtube.com"], "names": ["SID", "__Secure-1PSID"]},
}

# Default "expiring soon" horizon, in days.
SOON_DAYS = 7


def _bare_domain(domain: str) -> str:
    return (domain or "").lstrip(".").lower()


def _is_expired(expires: float, now: float) -> bool:
    # -1 is a session cookie (dies when the browser closes) — not "expired",
    # but it won't survive a restart, so we count it separately.
    return expires is not None and expires > 0 and expires < now


def _live_logins(cookies: list[dict], now: float) -> list[str]:
    """Which services have at least one present, non-expired auth cookie."""
    live: list[str] = []
    for service, spec in LOGIN_COOKIES.items():
        for c in cookies:
            dom = _bare_domain(c.get("domain"))
            if not any(dom == d or dom.endswith("." + d) for d in spec["domains"]):
                continue
            if c.get("name") not in spec["names"]:
                continue
            exp = c.get("expires", -1)
            # A session cookie for an auth token still means "logged in right now".
            if exp == -1 or not _is_expired(exp, now):
                live.append(service)
                break
    return live


def analyze(cookies: list[dict], now: Optional[float] = None,
            soon_days: int = SOON_DAYS) -> dict:
    """Summarise the health of a cookie jar. Pure — no browser involved.

    Returns counts (total / persistent / session / expired / expiring soon),
    the distinct domains, the live logins detected, and a single ``status``:

      * ``empty``     — no cookies at all
      * ``expiring``  — a persistent cookie dies within ``soon_days``
      * ``stale``     — something has already expired
      * ``ok``        — everything current
    """
    now = time.time() if now is None else now
    horizon = now + soon_days * 86400

    total = len(cookies)
    session = sum(1 for c in cookies if c.get("expires", -1) == -1)
    expired = sum(1 for c in cookies if _is_expired(c.get("expires", -1), now))
    expiring_soon = sum(
        1 for c in cookies
        if (e := c.get("expires", -1)) and e > 0 and now <= e < horizon
    )
    persistent = total - session
    domains = sorted({_bare_domain(c.get("domain")) for c in cookies if c.get("domain")})
    logins = _live_logins(cookies, now)

    if total == 0:
        status = "empty"
    elif expiring_soon:
        status = "expiring"
    elif expired:
        status = "stale"
    else:
        status = "ok"

    return {
        "status": status,
        "total": total,
        "persistent": persistent,
        "session": session,
        "expired": expired,
        "expiringSoon": expiring_soon,
        "soonDays": soon_days,
        "domains": domains,
        "logins": logins,
        "checkedAt": now,
    }


def check(profile: Profile, store: ProfileStore, engine: Optional[str] = None,
          soon_days: int = SOON_DAYS) -> dict:
    """Read the profile's live cookie jar and analyse it. Opens the profile
    headlessly (like the cookie export), so it's a per-profile, on-demand call —
    not something to run across the whole grid at once."""
    from . import cookies as cookies_mod
    jar = cookies_mod.read(profile, store, engine)
    return analyze(jar, soon_days=soon_days)
