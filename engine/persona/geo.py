"""
Launch-time geo alignment: timezone and geolocation from the proxy's *exit IP*.

A profile's timezone is set once, from the proxy's declared country. But a
rotating or residential proxy exits wherever it likes — a "US" pool can leave
from Chicago one day and Los Angeles the next — and a site compares the IP's
location with ``Intl`` timezone and ``navigator.geolocation``. GoLogin resolves
the exit IP *through the proxy* on every launch and pins both to it; so do we.

Geolocation also stops being a shared constant: every profile used to report the
same capital-city coordinate for its country (a collision in itself). Now it's
the exit IP's city, offset by a small per-profile amount that's stable across
launches, with a per-profile accuracy radius.

The lookup goes through the proxy itself (never direct, which would reveal the
real IP to the echo service). If it fails, launch falls back to the profile's
stored timezone and country — it never blocks a launch.
"""

from __future__ import annotations

import json
import math
import random
import time
import urllib.request
from typing import Optional

from . import devices
from .bridge import browser_proxy
from .models import Profile

# Echo services that report the caller's IP *with* timezone + coordinates.
_GEO_ECHO = ["https://ipwho.is/", "https://ipapi.co/json/"]
_CACHE_TTL = 600                      # seconds; a trust run right after launch reuses it
_cache: dict[tuple, tuple[float, Optional[dict]]] = {}


def _parse(data: dict) -> Optional[dict]:
    """Normalize ipwho.is / ipapi.co answers to one shape."""
    if data.get("success") is False or data.get("error"):
        return None
    tz = data.get("timezone")
    if isinstance(tz, dict):
        tz = tz.get("id")
    lat, lon = data.get("latitude"), data.get("longitude")
    if not data.get("ip") or not tz or lat is None or lon is None:
        return None
    return {"ip": data["ip"], "timezone": tz, "lat": float(lat), "lon": float(lon),
            "country": (data.get("country_code") or "").upper() or None,
            "city": data.get("city")}


def lookup_exit(proxy, timeout: float = 8) -> Optional[dict]:
    """Ask an echo service, *through the proxy*, where the exit IP is.

    Returns ``{ip, timezone, lat, lon, country, city}`` or ``None``. SOCKS
    proxies return ``None`` for now — urllib can't speak SOCKS (the local proxy
    bridge will route them through HTTP)."""
    if proxy is None or proxy.server.lower().startswith("socks"):
        return None
    host = proxy.server.split("://", 1)[-1]
    auth = ""
    if proxy.username:
        from urllib.parse import quote
        auth = f"{quote(proxy.username, safe='')}:{quote(proxy.password or '', safe='')}@"
    url = f"http://{auth}{host}"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": url, "https": url}))
    opener.addheaders = [("User-Agent", "Mozilla/5.0")]
    for echo in _GEO_ECHO:
        try:
            with opener.open(echo, timeout=timeout) as r:
                info = _parse(json.loads(r.read().decode("utf-8", "replace")))
            if info:
                return info
        except Exception:  # noqa: BLE001 - try the next service
            continue
    return None


def _jitter(profile: Profile, lat: float, lon: float) -> dict:
    """The profile's own spot near (lat, lon): stable per profile, different
    between profiles, within a few km — the precision IP geolocation has anyway."""
    rng = random.Random(f"geo:{profile.fingerprint.seed or profile.id}")
    dist_km = rng.uniform(0.4, 6.0)
    bearing = rng.uniform(0, 2 * math.pi)
    dlat = dist_km / 111.0 * math.cos(bearing)
    dlon = dist_km / (111.0 * max(0.2, math.cos(math.radians(lat)))) * math.sin(bearing)
    return {"latitude": round(lat + dlat, 5), "longitude": round(lon + dlon, 5),
            "accuracy": rng.choice([20, 35, 50, 65, 80, 100])}


def launch_geo(profile: Profile, lookup=lookup_exit) -> dict:
    """Timezone + geolocation a launch should present, and where they came from.

    ``{"timezone", "geolocation" (or None), "ip" (or None), "source"}`` where
    source is ``"exit-ip"`` (resolved through the proxy) or ``"profile"``
    (fallback: the stored timezone and the country's reference point)."""
    fp = profile.fingerprint
    info = None
    if profile.proxy:
        key = (profile.id, profile.proxy.server, profile.proxy.username)
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < _CACHE_TTL:
            info = hit[1]
        else:
            # Through the bridge when the browser needs one (SOCKS5 + auth), so
            # the lookup leaves from exactly where the browser's traffic does.
            info = lookup(browser_proxy(profile.proxy))
            _cache[key] = (time.time(), info)
    if info:
        return {"timezone": info["timezone"], "geolocation": _jitter(profile, info["lat"], info["lon"]),
                "ip": info["ip"], "country": info["country"], "city": info.get("city"),
                "source": "exit-ip"}

    country = (profile.proxy.country if profile.proxy and profile.proxy.country
               else devices.LOCALE_TO_COUNTRY.get(fp.locale))
    coords = devices.COUNTRY_GEO.get((country or "").upper())
    return {"timezone": fp.timezone,
            "geolocation": _jitter(profile, *coords) if coords else None,
            "ip": None, "country": country, "city": None, "source": "profile"}


def accept_languages(country: Optional[str]) -> Optional[list[str]]:
    """The language list a browser in ``country`` usually has: the country's
    language with and without region, then English (``de-DE, de, en-US, en``),
    which is what real non-English users typically end up with. None if the
    country is unknown."""
    cc = (country or "").upper()
    if cc == "UK":
        cc = "GB"
    lang = devices.COUNTRY_LANGUAGE.get(cc)
    if not lang:
        return None
    out: list[str] = []
    for tag in (f"{lang}-{cc}", lang, "en-US", "en"):
        if tag not in out:
            out.append(tag)
    return out


def launch_languages(profile: Profile, geo: Optional[dict] = None) -> tuple[str, list[str]]:
    """``(locale, languages)`` a launch should present. They follow the exit IP's
    country only when the profile opts in (``auto_lang``): moving an existing
    account to a new language is a signal of its own."""
    fp = profile.fingerprint
    if getattr(profile, "auto_lang", False):
        geo = geo if geo is not None else launch_geo(profile)
        langs = accept_languages(geo.get("country"))
        if langs:
            return langs[0], langs
    return fp.locale, list(fp.languages)


def clear_cache() -> None:
    _cache.clear()
