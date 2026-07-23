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


def _proxy_url(proxy: dict) -> str:
    auth = ""
    if proxy.get("user"):
        auth = f"{proxy['user']}:{proxy.get('pass') or ''}@"
    return f"http://{auth}{proxy['host']}:{proxy['port']}"


def check(proxy: dict, timeout: float = 12) -> dict:
    """Route a real request through the proxy and report the exit IP/country.

    Uses urllib directly (no browser), which keeps a pool health-check fast.
    SOCKS proxies need a SOCKS-aware transport we don't want to hard-depend on,
    so those are reported as 'needs the profile proxy test' rather than failed.
    """
    if str(proxy.get("type", "HTTP")).upper().startswith("SOCKS"):
        return {"ok": None, "error": "SOCKS — test it via a profile's proxy test"}

    handler = urllib.request.ProxyHandler({"http": _proxy_url(proxy), "https": _proxy_url(proxy)})
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
