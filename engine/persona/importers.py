"""
Import profiles from other anti-detect browsers.

The biggest reason people don't switch tools is the profiles they've already
built. This reads exports from the common ones — GoLogin, AdsPower, Multilogin —
and turns them into Persona profiles.

It's deliberately *tolerant*: those tools version their formats and rename fields
between releases, so instead of demanding an exact schema we look for a value
under any of the names a field is known by, fall back to a coherent generated
value when it's missing, and then run the profile through ``validate()`` so you
can see and fix anything that didn't line up. An import is a starting point you
review, not a black box.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from . import devices
from .fingerprint import generate, validate
from .models import Fingerprint, Profile, Proxy


def _first(d: dict, *names, default=None):
    """First present, non-empty value among ``names`` (supports 'a.b' paths)."""
    for name in names:
        node = d
        for part in name.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                node = None
                break
        if node not in (None, "", [], {}):
            return node
    return default


def _norm_os(value: Optional[str], ua: str = "") -> str:
    text = f"{value or ''} {ua}".lower()
    if "mac" in text or "os x" in text or "darwin" in text:
        return "macos"
    if "android" in text:
        return "android"
    if "linux" in text and "android" not in text:
        return "linux"
    return "windows"


def _parse_resolution(value) -> tuple[int, int]:
    try:
        w, h = (int(x) for x in str(value).lower().replace(" ", "").split("x")[:2])
        return w, h
    except (ValueError, AttributeError):
        return 1920, 1080


def _parse_proxy(d: dict) -> Optional[Proxy]:
    px = _first(d, "proxy", "proxyConfig", "user_proxy_config", default=None)
    if not isinstance(px, dict):
        return None
    host = _first(px, "host", "ip", "proxy_host", "addr")
    if not host:
        return None
    # "mode: none" / "type: no_proxy" means the profile is really direct.
    mode = str(_first(px, "mode", "type", "proxy_type", "proxy_soft", default="")).lower()
    if mode in ("none", "no_proxy", "direct", ""):
        if not _first(px, "type", "proxy_type"):
            return None
    scheme = "socks5" if "socks" in mode else "http"
    port = _first(px, "port", "proxy_port", default="")
    return Proxy(
        server=f"{scheme}://{host}:{port}".rstrip(":"),
        username=_first(px, "username", "user", "proxy_user", "login"),
        password=_first(px, "password", "pass", "proxy_password"),
        country=_first(px, "country", "geo"),
    )


def profile_from_export(d: dict) -> tuple[Profile, list[str]]:
    """Map one exported profile dict to a Persona :class:`Profile`.

    Returns the profile plus the list of coherence issues ``validate()`` found,
    so the caller can surface what needs a look.
    """
    ua = _first(d, "navigator.userAgent", "user_agent", "ua", "useragent",
                "fingerprint.ua", "fingerprint.userAgent", default="") or ""
    os_key = _norm_os(_first(d, "os", "os_type", "osType", "navigator.platform"), ua)

    # Start from a coherent base for this OS, then overlay whatever the export
    # actually specified. Gaps stay coherent instead of becoming holes.
    base = generate(os=os_key)

    sw, sh = _parse_resolution(_first(d, "navigator.resolution", "screen_resolution",
                                      "resolution", "screen", default=""))
    locale = _first(d, "navigator.language", "language", "locale", default=base.locale)
    if locale not in devices.LOCALES:
        locale = base.locale
    tz = _first(d, "timezone.timezone", "timezone", "time_zone",
                "fingerprint.timezone", default=devices.LOCALES[locale][0])

    fp = Fingerprint(
        os=os_key,
        user_agent=ua or base.user_agent,
        platform=devices.NAV_PLATFORM[os_key],
        ch_platform=devices.CH_PLATFORM[os_key],
        chrome_version=base.chrome_version,
        screen_width=sw, screen_height=sh,
        viewport_width=sw, viewport_height=max(1, sh - 88),
        hardware_concurrency=int(_first(d, "navigator.hardwareConcurrency",
                                         "hardware_concurrency", "cores", default=base.hardware_concurrency)),
        device_memory=int(_first(d, "navigator.deviceMemory", "device_memory",
                                 "memory", default=base.device_memory)),
        webgl_vendor=_first(d, "webGLMetadata.vendor", "webgl_vendor",
                            "fingerprint.webgl_vendor", default=base.webgl_vendor),
        webgl_renderer=_first(d, "webGLMetadata.renderer", "webgl_renderer",
                              "fingerprint.webgl_renderer", default=base.webgl_renderer),
        locale=locale,
        timezone=tz,
        languages=devices.LOCALES[locale][1],
        is_mobile=os_key == "android",
        seed=base.seed,
        fonts=base.fonts, cameras=base.cameras, microphones=base.microphones,
    )

    tags = _first(d, "tags", default=[]) or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    group = _first(d, "group_name", "group", "folder")
    if group and group not in tags:
        tags.append(str(group))

    prof = Profile(
        name=_first(d, "name", "title", "profile_name", default="imported profile"),
        fingerprint=fp,
        proxy=_parse_proxy(d),
        notes=_first(d, "notes", "description", default="") or "",
        tags=tags,
    )
    return prof, validate(fp)


def _unwrap(data) -> list[dict]:
    """Pull the list of profiles out of whatever the export wraps them in."""
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("data", "profiles", "list", "items", "rows"):
            inner = data.get(key)
            if isinstance(inner, list):
                return [x for x in inner if isinstance(x, dict)]
        return [data]   # a single profile object
    return []


def load_export(path: str | Path) -> list[dict]:
    return _unwrap(json.loads(Path(path).read_text(encoding="utf-8")))


def import_file(path: str | Path, store) -> list[tuple[Profile, list[str]]]:
    """Import every profile in ``path`` into ``store``. Returns (profile, issues)
    per profile so the caller can report what came in and what needs a look."""
    out = []
    for raw in load_export(path):
        prof, issues = profile_from_export(raw)
        store.save(prof)
        out.append((prof, issues))
    return out
