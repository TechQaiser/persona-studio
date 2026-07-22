"""
Consistent fingerprint generation.

The whole point of this module is *coherence*. Anti-bot systems don't just read
individual values; they cross-check them. A convincing fingerprint is one where
the OS, user-agent, GPU, screen, CPU, timezone and language all tell the same
story. So instead of randomising each field independently, we pick a device
archetype first and then draw every value from that archetype's realistic pool.

Public API:
    generate(seed=None, os=None, locale=None, proxy=None, mobile=False) -> Fingerprint
"""

from __future__ import annotations

import random
from typing import Optional

from . import devices
from .models import Fingerprint, Proxy


def _build_user_agent(os_key: str, chrome: str) -> str:
    token = devices.OS_UA_TOKEN[os_key]
    if os_key == "android":
        return (
            f"Mozilla/5.0 ({token}) AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{chrome} Mobile Safari/537.36"
        )
    return (
        f"Mozilla/5.0 ({token}) AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{chrome} Safari/537.36"
    )


def _pick_locale(rng: random.Random, locale: Optional[str],
                 proxy: Optional[Proxy]) -> str:
    """Choose a locale. Explicit wins; else follow the proxy's country; else random."""
    if locale and locale in devices.LOCALES:
        return locale
    if proxy and proxy.country:
        hint = devices.COUNTRY_TO_LOCALE.get(proxy.country.upper())
        if hint:
            return hint
    return rng.choice(list(devices.LOCALES.keys()))


def generate(
    seed: Optional[int] = None,
    os: Optional[str] = None,
    locale: Optional[str] = None,
    proxy: Optional[Proxy] = None,
    mobile: bool = False,
) -> Fingerprint:
    """Produce one internally-consistent :class:`Fingerprint`.

    Args:
        seed: fixed seed for reproducibility (also drives canvas/audio noise).
              If ``None``, a random seed is generated and stored.
        os: force an OS ("windows"|"macos"|"linux"|"android"); random if None.
        locale: force a locale key; otherwise inferred from proxy or random.
        proxy: if given and it has a country, locale/timezone align to it.
        mobile: allow/force a mobile (Android) device.
    """
    if seed is None:
        seed = random.randint(1, 2**31 - 1)
    rng = random.Random(seed)

    # 1. Pick the operating system (the archetype root).
    if os:
        os_key = os.lower()
    elif mobile:
        os_key = "android"
    else:
        os_key = rng.choice(devices.DESKTOP_OS)
    is_mobile = os_key == "android"

    # 2. Browser version.
    chrome = rng.choice(devices.CHROME_VERSIONS)

    # 3. Screen + viewport. Viewport is the screen minus realistic chrome/taskbar.
    sw, sh = rng.choice(devices.SCREENS[os_key])
    if is_mobile:
        vw, vh = sw, sh - rng.choice([0, 80, 120])
    else:
        vw = sw - rng.choice([0, 16])
        vh = sh - rng.choice([74, 88, 104, 120])  # browser UI + OS bar

    # 4. Hardware consistent with the OS.
    cores = rng.choice(devices.HARDWARE[os_key]["cores"])
    memory = rng.choice(devices.HARDWARE[os_key]["memory"])

    # 5. GPU that actually exists on this OS.
    webgl_vendor, webgl_renderer = rng.choice(devices.WEBGL[os_key])

    # 6. Locale -> timezone + languages (optionally steered by the proxy).
    loc = _pick_locale(rng, locale, proxy)
    timezone, languages = devices.LOCALES[loc]

    return Fingerprint(
        os=os_key,
        user_agent=_build_user_agent(os_key, chrome),
        platform=devices.NAV_PLATFORM[os_key],
        ch_platform=devices.CH_PLATFORM[os_key],
        chrome_version=chrome,
        screen_width=sw,
        screen_height=sh,
        viewport_width=vw,
        viewport_height=vh,
        hardware_concurrency=cores,
        device_memory=memory,
        webgl_vendor=webgl_vendor,
        webgl_renderer=webgl_renderer,
        locale=loc,
        timezone=timezone,
        languages=languages,
        is_mobile=is_mobile,
        seed=seed,
    )


def sec_ch_ua(fp: Fingerprint) -> str:
    """Build a Client Hints ``sec-ch-ua`` header matching the Chrome version."""
    major = fp.chrome_version.split(".")[0]
    return (
        f'"Chromium";v="{major}", "Google Chrome";v="{major}", '
        f'"Not-A.Brand";v="99"'
    )


def validate(fp: Fingerprint) -> list[str]:
    """Return a list of consistency problems (empty list == coherent).

    Useful in tests and as a sanity gate before launching a profile.
    """
    issues: list[str] = []

    if fp.platform != devices.NAV_PLATFORM.get(fp.os):
        issues.append(f"platform '{fp.platform}' does not match os '{fp.os}'")

    if (fp.webgl_vendor, fp.webgl_renderer) not in devices.WEBGL.get(fp.os, []):
        issues.append("webgl vendor/renderer not valid for this os")

    if (fp.screen_width, fp.screen_height) not in devices.SCREENS.get(fp.os, []):
        issues.append("screen resolution not typical for this os")

    if fp.viewport_width > fp.screen_width or fp.viewport_height > fp.screen_height:
        issues.append("viewport larger than screen")

    if fp.locale in devices.LOCALES:
        tz, langs = devices.LOCALES[fp.locale]
        if fp.timezone != tz:
            issues.append("timezone does not match locale")
        if fp.languages != langs:
            issues.append("languages do not match locale")
    else:
        issues.append(f"unknown locale '{fp.locale}'")

    if fp.is_mobile != (fp.os == "android"):
        issues.append("is_mobile flag inconsistent with os")

    return issues
