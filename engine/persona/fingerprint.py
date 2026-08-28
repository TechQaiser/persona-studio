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


def _build_user_agent(os_key: str, chrome: str, token: Optional[str] = None) -> str:
    token = token or devices.OS_UA_TOKEN[os_key]
    if os_key == "android":
        return (
            f"Mozilla/5.0 ({token}) AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{chrome} Mobile Safari/537.36"
        )
    return (
        f"Mozilla/5.0 ({token}) AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{chrome} Safari/537.36"
    )


def _android_token(device: dict) -> str:
    """The `(...)` platform token in an Android Chrome UA, describing the handset:
    e.g. ``Linux; Android 13; Pixel 7``."""
    return f"Linux; Android {device['android']}; {device['model']}"


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

    # On Android everything below (model, screen, GPU, RAM, UA token) has to
    # describe one real handset, so we pick a whole device and draw from it.
    device = rng.choice(devices.ANDROID_DEVICES) if is_mobile else None

    # 3. Screen + viewport. Viewport is the screen minus realistic chrome/taskbar.
    if device:
        sw, sh = device["screen"]
        vw, vh = sw, sh - rng.choice([0, 56, 80])   # URL bar / gesture area
    else:
        sw, sh = rng.choice(devices.SCREENS[os_key])
        vw = sw - rng.choice([0, 16])
        vh = sh - rng.choice([74, 88, 104, 120])    # browser UI + OS bar

    # 4. Hardware consistent with the OS (or the specific phone).
    if device:
        cores, memory = device["cores"], device["memory"]
    else:
        cores = rng.choice(devices.HARDWARE[os_key]["cores"])
        memory = rng.choice(devices.HARDWARE[os_key]["memory"])

    # 5. GPU that actually exists on this OS (or ships in this phone).
    if device:
        webgl_vendor, webgl_renderer = device["webgl"]
    else:
        webgl_vendor, webgl_renderer = rng.choice(devices.WEBGL[os_key])

    # 6. Locale -> timezone + languages (optionally steered by the proxy).
    loc = _pick_locale(rng, locale, proxy)
    timezone, languages = devices.LOCALES[loc]

    # 7. Secondary signals. Fonts come from the OS's real set (minus a few, since
    #    no two machines have an identical list); media devices match the form
    #    factor — phones always have both, desktops sometimes have neither.
    pool = devices.FONTS[os_key]
    fonts = sorted(rng.sample(pool, k=max(6, len(pool) - rng.randint(0, 6))))
    if is_mobile:
        cameras, microphones = 2, 1
    else:
        cameras = rng.choice([0, 1, 1, 1, 2])
        microphones = rng.choice([0, 1, 1, 1, 2]) if cameras else rng.choice([0, 1])

    ua_token = _android_token(device) if device else None
    return Fingerprint(
        os=os_key,
        user_agent=_build_user_agent(os_key, chrome, ua_token),
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
        fonts=fonts,
        cameras=cameras,
        microphones=microphones,
    )


def sec_ch_ua(fp: Fingerprint) -> str:
    """Build a Client Hints ``sec-ch-ua`` header matching the Chrome version."""
    major = fp.chrome_version.split(".")[0]
    return (
        f'"Chromium";v="{major}", "Google Chrome";v="{major}", '
        f'"Not-A.Brand";v="99"'
    )


def build_user_agent(os_key: str, chrome: str) -> str:
    """Public wrapper so callers (e.g. the aligner) can rebuild a UA for an OS."""
    return _build_user_agent(os_key, chrome)


def webgl_plausible(os_key: str, vendor: str, renderer: str) -> bool:
    """Is this WebGL vendor/renderer believable for ``os_key``?

    The curated pool in :mod:`devices` can't list every real GPU — there are
    thousands. So on top of "is it one we generate?", we accept any renderer
    whose API shape matches the OS: Windows drives WebGL through Direct3D
    (ANGLE/D3D11), while macOS and Linux go through desktop OpenGL. This lets a
    profile carry the machine's *actual* GPU (e.g. after `persona align`)
    without being flagged as incoherent, while still catching an Apple GPU
    pretending to be on Windows.
    """
    if (vendor, renderer) in devices.WEBGL.get(os_key, []):
        return True
    r = (renderer or "").lower()
    if not r:
        return False
    is_d3d = "direct3d" in r or "d3d11" in r or "d3d9" in r
    is_gl = "opengl" in r
    if os_key == "windows":
        return is_d3d
    if os_key == "macos":
        return is_gl and not is_d3d and ("apple" in r or "intel" in r or "amd" in r or "metal" in r or "opengl 4" in r)
    if os_key == "linux":
        return is_gl and not is_d3d
    if os_key == "android":
        return "opengl es" in r or "adreno" in r or "mali" in r
    return False


def validate(fp: Fingerprint) -> list[str]:
    """Return a list of consistency problems (empty list == coherent).

    Useful in tests and as a sanity gate before launching a profile.
    """
    issues: list[str] = []

    if fp.platform != devices.NAV_PLATFORM.get(fp.os):
        issues.append(f"platform '{fp.platform}' does not match os '{fp.os}'")

    if not webgl_plausible(fp.os, fp.webgl_vendor, fp.webgl_renderer):
        issues.append("webgl vendor/renderer not valid for this os")

    # Accept the curated resolutions, but also any real-world one: after aligning
    # to a machine, a profile carries that display's actual size, which won't be
    # in the short curated list yet is perfectly coherent.
    sane = 320 <= fp.screen_width <= 8000 and 480 <= fp.screen_height <= 5000
    if (fp.screen_width, fp.screen_height) not in devices.SCREENS.get(fp.os, []) and not sane:
        issues.append("screen resolution not typical for this os")

    if fp.viewport_width > fp.screen_width or fp.viewport_height > fp.screen_height:
        issues.append("viewport larger than screen")

    if fp.locale in devices.LOCALES:
        tz, langs = devices.LOCALES[fp.locale]
        if fp.timezone != tz:
            issues.append("timezone does not match locale")
        # navigator.languages varies with the user's settings (one entry or
        # several), so we require the *primary* language to agree with the
        # locale rather than an exact list — a machine-aligned profile that
        # reports just ["en-US"] is as coherent as ["en-US", "en"]. We compare
        # the base language (en), not the region (en-US vs en-PK): an English
        # browser in a Karachi timezone is a real, coherent user, and matching
        # on region would wrongly flag it.
        def _base(tag):
            return (tag or "").split("-")[0].lower()
        if not fp.languages or _base(fp.languages[0]) != _base(langs[0]):
            issues.append("languages do not match locale")
    else:
        issues.append(f"unknown locale '{fp.locale}'")

    if fp.is_mobile != (fp.os == "android"):
        issues.append("is_mobile flag inconsistent with os")

    # A font that doesn't ship with this OS is as loud a tell as the wrong GPU.
    if fp.fonts:
        pool = set(devices.FONTS.get(fp.os, []))
        alien = [f for f in fp.fonts if f not in pool]
        if alien:
            issues.append(f"fonts not found on {fp.os}: {', '.join(sorted(alien)[:3])}")

    if fp.cameras < 0 or fp.microphones < 0:
        issues.append("media device counts cannot be negative")
    elif fp.is_mobile and (fp.cameras == 0 or fp.microphones == 0):
        issues.append("a phone with no camera or microphone is implausible")

    return issues
