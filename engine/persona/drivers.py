"""
Pluggable launch backends ("drivers").

Persona's real job is to *manage* browser identities — coherent fingerprints,
proxies, persistent sessions, folders, and the dashboard. Actually rendering an
identity in a browser is delegated to a launch backend, so a client can pick the
stealth engine that fits their needs and threat model:

  * ``playwright`` — stock Playwright Chromium + Persona's injected stealth script.
    Always available. Good for fingerprint test sites and lighter use. Its ceiling
    is the JS-injection ceiling: it can't change the TLS/JA3 fingerprint or hide
    the CDP transport.

  * ``patchright`` — a drop-in *patched* Playwright that fixes ``webdriver``/CDP
    and other runtime-level leaks that plain Playwright can't. Same API, stronger.
    Install:  ``pip install patchright`` then ``patchright install chromium``.

  * ``camoufox`` — a patched Firefox with C++-level fingerprint spoofing and its
    own coherent fingerprint generator; among the strongest open options.
    Install:  ``pip install "camoufox[geoip]"`` then ``camoufox fetch``.

  * ``cloak`` — CloakBrowser: a patched Chromium binary whose fingerprint, TLS and
    CDP are altered at the C++ source level. Reaches detection grades JS injection
    can't (Cloudflare, DataDome, reCAPTCHA v3). Install:  ``pip install cloakbrowser``.

Persona stays the manager on top of all of them: it owns the profile identity,
the proxy, the session directory, and the coherence checks; the driver just opens
a window wearing it.

Add your own backend by decorating a function with ``@register("name", requires=...)``.
Each driver has the signature ``(profile, store, headless, keep_open)`` and either
returns launch handles (``keep_open=True``) or blocks until the window closes
(``keep_open=False``).
"""

from __future__ import annotations

import importlib.util
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Callable, Optional

from . import devices as fp_mod_devices
from . import fingerprint as fp_mod
from .models import Profile
from .stealth import build_init_script

_DRIVERS: dict[str, dict] = {}


def _open_startup_urls(context, page, profile: Profile) -> None:
    """Navigate the first tab to the profile's first startup URL and open the
    rest in new tabs. A bad URL is skipped rather than aborting the launch."""
    urls = getattr(profile, "startup_urls", None) or []
    if not urls:
        return
    for i, url in enumerate(urls):
        try:
            target = page if i == 0 else context.new_page()
            target.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            continue  # unreachable site / typo — don't crash the session


def _geolocation_for(profile: Profile) -> Optional[dict]:
    """Coordinates that agree with the profile's proxy country (or its locale
    when there's no proxy), so navigator.geolocation doesn't contradict the IP."""
    country = None
    if profile.proxy and profile.proxy.country:
        country = profile.proxy.country.upper()
    if not country:
        country = fp_mod_devices.LOCALE_TO_COUNTRY.get(profile.fingerprint.locale)
    coords = fp_mod_devices.COUNTRY_GEO.get(country or "")
    if not coords:
        return None
    lat, lon = coords
    return {"latitude": lat, "longitude": lon, "accuracy": 60}


def _webrtc_arg(profile: Profile) -> list[str]:
    """Stop WebRTC from leaking the real IP. With a proxy, force everything
    through it (or don't send UDP at all); otherwise expose only the public
    interface so local addresses stay hidden."""
    if profile.proxy:
        return ["--force-webrtc-ip-handling-policy=disable_non_proxied_udp"]
    return ["--force-webrtc-ip-handling-policy=default_public_interface_only"]


def _extension_args(profile: Profile) -> list[str]:
    """Chromium flags that load the profile's unpacked extensions.

    Both flags are required: ``--load-extension`` alone still leaves every other
    extension enabled, which would leak identity between profiles.
    """
    paths = [str(Path(p).expanduser().resolve())
             for p in (getattr(profile, "extensions", None) or [])]
    paths = [p for p in paths if Path(p).is_dir()]
    if not paths:
        return []
    joined = ",".join(paths)
    return [f"--disable-extensions-except={joined}", f"--load-extension={joined}"]


def _wait_until_closed(page) -> None:
    """Block until the session ends, headed or headless.

    Headed, that is the user closing the window. Headless there is no window,
    but the session still has to stay up — a server profile is driven over CDP
    or stopped by the API, and returning early would tear the browser down the
    moment it finished opening. Blocking on the same event covers both: the page
    closes when the browser is stopped, and Ctrl-C still interrupts.
    """
    try:
        page.wait_for_event("close", timeout=0)
    except KeyboardInterrupt:
        pass
    except Exception:
        # The browser died on its own (crash, external kill) — nothing to wait
        # for any more; fall through to the caller's cleanup.
        pass


def register(name: str, requires: Optional[str] = None):
    """Register a launch backend. ``requires`` is the pip module it needs (if any)."""
    def deco(fn: Callable):
        _DRIVERS[name] = {"fn": fn, "requires": requires}
        return fn
    return deco


def names() -> list[str]:
    return sorted(_DRIVERS)


def is_installed(name: str) -> bool:
    req = _DRIVERS.get(name, {}).get("requires")
    return req is None or importlib.util.find_spec(req) is not None


def available() -> dict[str, bool]:
    """Map every known engine to whether its dependency is importable."""
    return {n: is_installed(n) for n in names()}


def get(name: str) -> Callable:
    if name not in _DRIVERS:
        raise RuntimeError(
            f"Unknown engine '{name}'. Known engines: {', '.join(names())}."
        )
    if not is_installed(name):
        req = _DRIVERS[name]["requires"]
        raise RuntimeError(
            f"The '{name}' engine needs the '{req}' package, which isn't installed.\n"
            f"Install it, then try again  (see persona/drivers.py for hints)."
        )
    return _DRIVERS[name]["fn"]


@contextmanager
def session(profile: Profile, store, engine: Optional[str] = None,
            headless: bool = True):
    """Open a profile's persistent session and yield its browser context.

    This is the entry point for the tools that *inspect* a profile rather than
    hand it to a user — cookie transfer, the proxy/leak test, the trust report.
    Startup URLs are stripped: these callers want the identity, not a browsing
    session. The context is always closed on the way out, which is also what
    flushes cookies to disk.
    """
    name = engine or profile.engine or "playwright"
    quiet = replace(profile, startup_urls=[])

    if name == "camoufox":
        # Camoufox's driver is launch-and-wait only, so open it directly.
        from camoufox.sync_api import Camoufox
        with Camoufox(headless=headless, persistent_context=True,
                      user_data_dir=str(store.user_data_path(profile.id))) as browser:
            yield browser
        return

    handles = get(name)(quiet, store, headless=headless, keep_open=True)
    pw, context, _page = handles
    try:
        yield context
    finally:
        context.close()
        if pw:
            pw.stop()


# --------------------------------------------------------------------------
# Shared Playwright-style launch (used by both playwright and patchright).
# --------------------------------------------------------------------------
def _launch_playwright_like(sync_playwright, profile: Profile, store, headless: bool,
                            keep_open: bool, extra_args=None):
    fp = profile.fingerprint
    launch_args = [
        f"--window-size={fp.viewport_width},{fp.viewport_height}",
        "--disable-blink-features=AutomationControlled",
        "--no-first-run",
        "--no-default-browser-check",
        *_webrtc_arg(profile),
        *_extension_args(profile),
        *(extra_args or []),
    ]
    geolocation = _geolocation_for(profile)
    context_opts: dict = {
        "user_agent": fp.user_agent,
        "locale": fp.locale,
        "timezone_id": fp.timezone,
        "viewport": {"width": fp.viewport_width, "height": fp.viewport_height},
        "screen": {"width": fp.screen_width, "height": fp.screen_height},
        "is_mobile": fp.is_mobile,
        "device_scale_factor": 2 if fp.is_mobile else 1,
        "extra_http_headers": {
            "sec-ch-ua": fp_mod.sec_ch_ua(fp),
            "sec-ch-ua-platform": fp.ch_platform,
            "sec-ch-ua-mobile": "?1" if fp.is_mobile else "?0",
            "accept-language": ",".join(
                f"{l};q={1.0 - i*0.1:.1f}" if i else l
                for i, l in enumerate(fp.languages)
            ),
        },
    }
    if profile.proxy:
        context_opts["proxy"] = profile.proxy.to_playwright()
    if geolocation:
        # Grant the permission too, so a site that asks gets the coordinates
        # rather than a prompt that would stall an unattended session.
        context_opts["geolocation"] = geolocation
        context_opts["permissions"] = ["geolocation"]

    pw = sync_playwright().start()
    context = pw.chromium.launch_persistent_context(
        user_data_dir=str(store.user_data_path(profile.id)),
        headless=headless,
        # Headless defaults to the "headless shell" binary, which cannot load
        # extensions at all and announces itself as HeadlessChrome over CDP.
        # The chromium channel is the full browser in --headless=new mode: same
        # download, extensions work, and the browser stops advertising that it
        # is headless.
        channel="chromium" if headless else None,
        args=launch_args,
        # Drop Playwright's automation switch so Chrome doesn't show the
        # "controlled by automated test software" infobar.
        ignore_default_args=["--enable-automation"],
        **context_opts,
    )
    context.add_init_script(build_init_script(fp))
    page = context.pages[0] if context.pages else context.new_page()
    _open_startup_urls(context, page, profile)

    if keep_open:
        return pw, context, page
    try:
        _wait_until_closed(page)
    finally:
        context.close()
        pw.stop()
    return None


@register("playwright", requires="playwright")
def _driver_playwright(profile, store, headless=False, keep_open=True, extra_args=None):
    from playwright.sync_api import sync_playwright
    return _launch_playwright_like(sync_playwright, profile, store, headless, keep_open, extra_args)


@register("patchright", requires="patchright")
def _driver_patchright(profile, store, headless=False, keep_open=True, extra_args=None):
    # Patchright is an API-compatible, patched drop-in for Playwright.
    from patchright.sync_api import sync_playwright
    return _launch_playwright_like(sync_playwright, profile, store, headless, keep_open, extra_args)


@register("camoufox", requires="camoufox")
def _driver_camoufox(profile, store, headless=False, keep_open=True, extra_args=None):
    """Camoufox (patched Firefox) generates its own coherent fingerprint; we feed
    it the profile's OS/locale/proxy as hints and keep the persistent session."""
    if keep_open:
        raise RuntimeError(
            "The camoufox engine supports launch-and-wait only (keep_open=False), "
            "which is what `persona launch` and the dashboard use."
        )
    from camoufox.sync_api import Camoufox

    fp = profile.fingerprint
    os_hint = {"windows": "windows", "macos": "macos", "linux": "linux"}.get(fp.os, "windows")
    kwargs: dict = {
        "headless": headless,
        "os": os_hint,
        "locale": fp.locale,
        "persistent_context": True,
        "user_data_dir": str(store.user_data_path(profile.id)),
    }
    if profile.proxy:
        kwargs["proxy"] = profile.proxy.to_playwright()
        kwargs["geoip"] = True  # align timezone/locale to the proxy exit IP

    with Camoufox(**kwargs) as browser:
        page = browser.pages[0] if getattr(browser, "pages", None) else browser.new_page()
        _open_startup_urls(browser, page, profile)
        if not headless:
            page.wait_for_event("close", timeout=0)
    return None


@register("cloak", requires="cloakbrowser")
def _driver_cloak(profile, store, headless=False, keep_open=True, extra_args=None):
    """CloakBrowser — a patched Chromium binary whose fingerprints are altered at
    the C++ source level. Persona feeds it the profile's identity + proxy and keeps
    the persistent session; the binary does the heavy stealth work (its own
    fingerprint, TLS, CDP), so we don't inject our JS stealth script here.

    The binary auto-downloads on first launch. Docs: https://github.com/CloakHQ/CloakBrowser
    """
    import cloakbrowser

    fp = profile.fingerprint
    context = cloakbrowser.launch_persistent_context(
        user_data_dir=str(store.user_data_path(profile.id)),
        headless=headless,
        proxy=profile.proxy.to_playwright() if profile.proxy else None,
        user_agent=fp.user_agent,
        viewport={"width": fp.viewport_width, "height": fp.viewport_height},
        locale=fp.locale,
        timezone=fp.timezone,
        geoip=bool(profile.proxy),   # align timezone/locale to the proxy exit IP
        # CloakBrowser launches with --no-sandbox (its stealth args), which makes
        # Chromium show a local "unsupported command-line flag" infobar. --test-type
        # hides that purely-cosmetic bar; it isn't visible to websites (JS can't
        # read command-line flags), so it doesn't affect the fingerprint.
        args=["--test-type", "--no-first-run", "--no-default-browser-check",
              *_webrtc_arg(profile), *_extension_args(profile), *(extra_args or [])],
    )
    page = context.pages[0] if context.pages else context.new_page()
    _open_startup_urls(context, page, profile)

    if keep_open:
        return None, context, page
    try:
        _wait_until_closed(page)
    finally:
        context.close()
    return None
