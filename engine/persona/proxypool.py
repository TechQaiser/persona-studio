"""
Proxy pool: parse the proxy lists people actually paste, and health-check them.

Proxy vendors hand you a text file, and every one uses a different order:
``host:port``, ``host:port:user:pass``, ``user:pass@host:port``,
``scheme://user:pass@host:port`` — sometimes with a trailing country code. This
module reads all of those tolerantly into one shape, and does a lightweight
liveness check (a real request through the proxy) without needing a browser, so
a whole pool can be tested quickly.

The shape everywhere is a plain dict::

    {"type": "HTTP"|"HTTPS"|"SOCKS5"|"SOCKS4", "host", "port",
     "user": str|None, "pass": str|None, "country": str|None}
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from typing import Optional

_SCHEME_TYPE = {"http": "HTTP", "https": "HTTPS", "socks5": "SOCKS5",
                "socks5h": "SOCKS5", "socks4": "SOCKS4", "socks": "SOCKS5"}
_CC = re.compile(r"^[A-Za-z]{2}$")

# A tiny IP-echo used for the liveness check; tried in order.
_ECHO = ["https://ipapi.co/json/", "https://ipwho.is/", "https://api.ipify.org/?format=json"]


def parse_line(line: str) -> Optional[dict]:
    """Parse one proxy line into the pool shape, or ``None`` if it isn't one."""
    s = (line or "").strip()
    if not s or s.startswith("#"):
        return None

    scheme = "http"
    if "://" in s:
        scheme, s = s.split("://", 1)
        scheme = scheme.lower()

    user = pw = None
    if "@" in s:                              # user:pass@host:port
        creds, s = s.rsplit("@", 1)
        if ":" in creds:
            user, pw = creds.split(":", 1)
        else:
            user = creds or None

    parts = s.split(":")
    if len(parts) < 2 or not parts[1].isdigit():
        return None
    host, port = parts[0].strip(), parts[1].strip()
    if not host:
        return None

    country = None
    # host:port:user:pass[:CC]  (creds after the port, colon-separated)
    if user is None and len(parts) >= 4:
        user, pw = parts[2] or None, parts[3] or None
        if len(parts) >= 5 and _CC.match(parts[4]):
            country = parts[4].upper()
    # host:port:CC  or  user:pass@host:port:CC
    elif len(parts) >= 3 and _CC.match(parts[-1]):
        country = parts[-1].upper()

    return {
        "type": _SCHEME_TYPE.get(scheme, "HTTP"),
        "host": host, "port": port,
        "user": user or None, "pass": pw or None,
        "country": country,
    }


def parse_many(text: str) -> list[dict]:
    """Parse a whole pasted list / file, skipping blank and unparseable lines."""
    out = []
    for line in (text or "").replace(",", "\n").splitlines():
        p = parse_line(line)
        if p:
            out.append(p)
    return out


def change_ip(url: str, timeout: float = 20) -> dict:
    """Ask a rotating/mobile proxy vendor for a new exit IP by requesting its
    change-IP URL. The URL is a vendor API endpoint, so it's called directly
    (like the vendor's own dashboard would), not through the proxy.

    Returns ``{ok, status, body}``. The exit-IP cache is cleared on success, so
    the next launch looks up the new IP's timezone and location."""
    url = (url or "").strip()
    if not re.match(r"^https?://", url, re.I):
        return {"ok": False, "status": None, "body": "the change-IP URL must start with http:// or https://"}
    req = urllib.request.Request(url, headers={"User-Agent": "persona-change-ip/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status, body = r.status, r.read(2000).decode("utf-8", "replace").strip()
    except urllib.error.HTTPError as e:
        status, body = e.code, (e.read(500).decode("utf-8", "replace").strip() or str(e))
    except Exception as e:  # noqa: BLE001 - report it
        return {"ok": False, "status": None, "body": str(e).splitlines()[0][:300]}
    ok = 200 <= status < 300
    if ok:
        from . import geo
        geo.clear_cache()
    return {"ok": ok, "status": status, "body": body[:500]}


def _proxy_url(proxy: dict) -> str:
    auth = ""
    if proxy.get("user"):
        auth = f"{proxy['user']}:{proxy.get('pass') or ''}@"
    return f"http://{auth}{proxy['host']}:{proxy['port']}"


def check(proxy: dict, timeout: float = 12) -> dict:
    """Route a real request through the proxy and report the exit IP/country.

    Uses urllib directly (no browser), which keeps a pool health-check fast.
    SOCKS4 and SOCKS5 go through the local bridge (``bridge.py``), which urllib
    can talk to.
    """
    kind = str(proxy.get("type", "HTTP")).upper()
    url = _proxy_url(proxy)
    if kind.startswith("SOCKS"):
        from .bridge import bridge_for
        from .models import Proxy
        scheme = "socks4" if kind == "SOCKS4" else "socks5"
        url = bridge_for(Proxy(server=f"{scheme}://{proxy['host']}:{proxy['port']}",
                               username=proxy.get("user"), password=proxy.get("pass"))).url

    handler = urllib.request.ProxyHandler({"http": url, "https": url})
    opener = urllib.request.build_opener(handler)
    opener.addheaders = [("User-Agent", "persona-proxy-check/1.0")]
    started = time.time()
    for url in _ECHO:
        try:
            with opener.open(url, timeout=timeout) as r:
                text = r.read().decode("utf-8", "replace").strip()
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                data = {"ip": text}
            ip = data.get("ip") or data.get("query") or data.get("IPv4")
            if not ip:
                continue
            return {
                "ok": True, "ip": ip,
                "country": data.get("country_code") or data.get("country") or data.get("countryCode"),
                "city": data.get("city"),
                "latencyMs": int((time.time() - started) * 1000),
            }
        except Exception as e:  # noqa: BLE001 - report, try the next echo
            last = str(e).splitlines()[0][:140]
    return {"ok": False, "error": locals().get("last", "no IP service answered")}
