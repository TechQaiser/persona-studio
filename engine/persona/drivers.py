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
import json
import re
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Callable, Optional

from . import fingerprint as fp_mod
from . import locks
from .bridge import browser_proxy
from .geo import launch_geo, launch_languages
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


def _webrtc_arg(profile: Profile) -> list[str]:
    """Stop WebRTC from leaking the real IP. With a proxy, force everything
    through it (or don't send UDP at all); otherwise expose only the public
    interface so local addresses stay hidden."""
    if profile.proxy:
        return ["--force-webrtc-ip-handling-policy=disable_non_proxied_udp"]
    return ["--force-webrtc-ip-handling-policy=default_public_interface_only"]


def _dns_lockdown_arg(profile: Profile) -> list[str]:
    """With a proxy, nothing should be resolved by this machine's DNS: page
    hosts already go to the proxy by name, but prefetching, WebRTC STUN names and
    the like would otherwise ask the real ISP's resolver — a DNS leak that
    places the user. Every local lookup is made to fail except the proxy's own
    host (which has to be found to connect to it) and localhost.

    The DNS leak *check* (``persona dns``) verifies this from the outside."""
    if not profile.proxy:
        return []
    from urllib.parse import urlsplit
    host = urlsplit(browser_proxy(profile.proxy).server).hostname or ""
    excludes = ", ".join(f"EXCLUDE {h}" for h in dict.fromkeys([host, "localhost"]) if h)
    return [f"--host-resolver-rules=MAP * ~NOTFOUND, {excludes}"]


# Client Hints platformVersion a real browser on each OS reports.
_CH_PLATFORM_VERSION = {"windows": "15.0.0", "macos": "14.6.0", "linux": "6.8.0"}


def ua_metadata(fp, full_version: Optional[str] = None) -> dict:
    """``userAgentMetadata`` for CDP's ``Emulation.setUserAgentOverride``.

    Without it Playwright's Chromium answers ``navigator.userAgentData`` (and
    the high-entropy Client Hints headers) as itself — "HeadlessChrome" /
    "Chromium" with no "Google Chrome" — contradicting the UA and the
    ``sec-ch-ua`` header. Brands mirror :func:`fingerprint.sec_ch_ua`."""
    major = fp.chrome_version.split(".")[0]
    full = full_version if (full_version or "").split(".")[0] == major else fp.chrome_version
    full = ".".join(full.split(".")[:4])
    brands = [("Chromium", major), ("Google Chrome", major), ("Not-A.Brand", "99")]
    phone = fp_mod.android_device(fp)
    apple_silicon = fp.os == "macos" and "Apple" in (fp.webgl_renderer or "")
    return {
        "brands": [{"brand": b, "version": v} for b, v in brands],
        "fullVersionList": [{"brand": b, "version": full if v == major else f"{v}.0.0.0"}
                            for b, v in brands],
        "fullVersion": full,
        "platform": fp.ch_platform.strip('"'),
        "platformVersion": (f"{phone['android']}.0.0" if phone
                            else _CH_PLATFORM_VERSION.get(fp.os, "")),
        "architecture": "arm" if (fp.is_mobile or apple_silicon) else "x86",
        "bitness": "64",
        "model": phone["model"] if phone else "",
        "mobile": bool(fp.is_mobile),
        "wow64": False,
    }


def _apply_ua_metadata(context, page, fp, full_version: Optional[str]) -> None:
    """Install the UA override on every page of a Chromium context (now and
    later), so ``navigator.userAgentData`` agrees with the UA and headers."""
    params = {"userAgent": fp.user_agent, "platform": fp.platform,
              "acceptLanguage": ",".join(fp.languages),
              "userAgentMetadata": ua_metadata(fp, full_version)}

    def install(p):
        try:
            context.new_cdp_session(p).send("Emulation.setUserAgentOverride", params)
        except Exception:  # noqa: BLE001 - a closed/odd page must not kill the launch
            pass

    for p in context.pages:
        install(p)
    context.on("page", install)


# Flags a profile can't set itself, grouped by why. Each one either is set by
# Persona (session dir, proxy, DNS lockdown, automation port, extension
# isolation, Cloak identity) or would change the identity behind Persona's
# back (UA, language, window size vs. the spoofed screen, pixel ratio, GPU
# backend, WebRTC policy). Letting a profile override them would silently undo
# a guarantee, so they're dropped and the reason is shown.
_MANAGED = {
    "Persona sets the session directory":
        ("--user-data-dir", "--profile-directory"),
    "Persona sets the proxy and DNS lockdown":
        ("--proxy-server", "--proxy-bypass-list", "--proxy-pac-url", "--no-proxy-server",
         "--host-resolver-rules"),
    "Persona owns the automation port":
        ("--remote-debugging-port", "--remote-debugging-pipe", "--remote-debugging-address",
         "--remote-allow-origins", "--enable-automation", "--headless"),
    "Persona loads the profile's extensions":
        ("--load-extension", "--disable-extensions-except", "--disable-extensions"),
    "it would change the identity the profile presents":
        ("--user-agent", "--lang", "--accept-lang", "--window-size",
         "--force-device-scale-factor", "--disable-blink-features", "--enable-blink-features",
         "--use-angle", "--use-gl"),
    "Persona sets the WebRTC policy":
        ("--force-webrtc-ip-handling-policy", "--webrtc-ip-handling-policy"),
    "it turns off the browser's sandbox":
        ("--no-sandbox",),
    "Persona passes the profile's identity to CloakBrowser":
        ("--fingerprint", "--fingerprint-platform", "--fingerprint-hardware-concurrency",
         "--fingerprint-device-memory", "--fingerprint-screen-width",
         "--fingerprint-screen-height", "--fingerprint-gpu-vendor",
         "--fingerprint-gpu-renderer", "--fingerprint-webrtc-ip"),
}
MANAGED_FLAGS = {flag: why for why, flags in _MANAGED.items() for flag in flags}
# A flag is one token: dashes, then letters/digits/dashes, then an optional =value.
# Firefox (Camoufox) takes single-dash flags, so one dash is accepted too.
_FLAG = re.compile(r"^--?[A-Za-z0-9][A-Za-z0-9-]*(=.*)?$")


def flag_problem(arg: str) -> Optional[str]:
    """Why a profile's launch flag would be dropped, or None if it's kept."""
    if not _FLAG.match(arg):
        return "not a browser flag"
    return MANAGED_FLAGS.get(arg.split("=", 1)[0].lower())


def profile_launch_args(profile: Profile) -> tuple[list[str], list[str]]:
    """The profile's own extra flags, split into (kept, dropped)."""
    kept, dropped = [], []
    for raw in getattr(profile, "launch_args", None) or []:
        arg = raw.strip()
        if not arg:
            continue
        (dropped if flag_problem(arg) else kept).append(arg)
    return kept, dropped


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


# --------------------------------------------------------------------------
# Pinned engine identities. A logged-in account must see the *same* device on
# every launch — a fingerprint that changes between sessions reads as a new
# device (security prompts) or a spoofed one (bans). The patched engines make
# their own fingerprints, so we pin each one per profile and feed it Persona's
# values where the engine accepts them. Pins live in the profile's user-data
# dir: a backup/restore carries the identity along, "duplicate as template"
# (fresh user-data) gets a new one.
# --------------------------------------------------------------------------
CLOAK_SEED_FILE = ".cloakbrowser-seed"            # CloakBrowser's own pin file
CAMOUFOX_FP_FILE = ".persona-camoufox-fingerprint.json"
# CloakBrowser presents a Windows or a macOS device; anything else it can't be.
CLOAK_PLATFORMS = {"windows": "windows", "macos": "macos"}
CLOAK_SEED_MIN, CLOAK_SEED_SPAN = 10000, 90000      # the binary's seed range


def host_os() -> str:
    import platform
    return {"Windows": "windows", "Darwin": "macos"}.get(platform.system(), "linux")


def launch_warnings(profile: Profile, engine: str, host: Optional[str] = None) -> list[str]:
    """Risks the fingerprint can't show, because they depend on the engine and
    the machine it runs on. Fonts are the big one: a page measures text with
    the fonts this machine really has, which no JS patch can change — so a
    profile claiming another OS is linkable by its font metrics unless the
    engine renders that OS's fonts itself."""
    host = host or host_os()
    want = profile.fingerprint.os
    out: list[str] = []
    for arg in profile_launch_args(profile)[1]:
        out.append(f"ignored launch flag {arg.split('=', 1)[0]}: {flag_problem(arg)}")
    if engine in ("playwright", "patchright") and want != host:
        out.append(f"{want} profile on a {host} machine with the '{engine}' engine: text renders "
                   f"with this machine's fonts, so font fingerprinting reads it as {host}. "
                   f"Use the 'cloak' engine (Windows/macOS) or 'camoufox', or a {host} profile.")
    if engine == "cloak":
        if want not in CLOAK_PLATFORMS:
            out.append(f"the 'cloak' engine can only present Windows or macOS — this {want} "
                       f"profile will show as the binary's own platform. Use another engine.")
        elif want == "macos" and host != "macos":
            out.append("macOS profile on cloak: install the real Mac fonts on this machine "
                       "(a Mac with no Mac fonts is a common block reason) and, headed, use a "
                       "HiDPI display — the pixel ratio comes from the real screen.")
    return out


_engine_versions: dict[str, Optional[str]] = {}


def engine_chrome_version(name: str) -> Optional[str]:
    """The Chromium version a launch engine actually runs, read without
    launching it (``None`` for Camoufox/Firefox or when unknown)."""
    if name in _engine_versions:
        return _engine_versions[name]
    version = None
    try:
        if name == "cloak":
            from cloakbrowser.config import get_chromium_version
            version = get_chromium_version()
        elif name in ("playwright", "patchright"):
            spec = importlib.util.find_spec(name)
            if spec and spec.origin:
                f = Path(spec.origin).parent / "driver" / "package" / "browsers.json"
                browsers = json.loads(f.read_text(encoding="utf-8"))["browsers"]
                version = next(b["browserVersion"] for b in browsers if b["name"] == "chromium")
    except Exception:  # noqa: BLE001 - unknown is fine: the profile keeps its version
        version = None
    _engine_versions[name] = version
    return version


def sync_engine_version(profile: Profile, engine: str) -> bool:
    """Claim the Chrome version the engine really is.

    A UA saying Chrome 128 on a 151 engine is caught by plain feature detection
    (APIs that only exist in newer builds) and by the Client Hints the binary
    sends itself — GoLogin picks the Orbita build matching the UA for exactly
    this reason. We go the other way: move the claim to the engine. Returns
    whether the profile changed (callers persist it)."""
    version = engine_chrome_version(engine)
    return bool(version) and fp_mod.set_chrome_version(profile.fingerprint, version)


def _sync_and_save(profile: Profile, store, engine: str) -> None:
    if sync_engine_version(profile, engine):
        try:
            store.save(profile)
        except Exception:  # noqa: BLE001 - e.g. a locked vault: still launch coherent
            pass


def cloak_identity_args(profile: Profile, user_data_dir) -> list[str]:
    """CloakBrowser flags that present the profile's own fingerprint.

    The seed pins everything Persona doesn't model (canvas/WebGL/audio noise,
    font metrics) to this profile. A profile CloakBrowser already opened keeps
    the seed it was given then — re-seeding it would swap the device under a
    logged-in session. The UA isn't passed: the binary builds UA *and* Client
    Hints from its own Chromium version, so the two always agree.
    """
    fp = profile.fingerprint
    args: list[str] = []
    if not (Path(user_data_dir) / CLOAK_SEED_FILE).exists() and fp.seed:
        args.append(f"--fingerprint={CLOAK_SEED_MIN + fp.seed % CLOAK_SEED_SPAN}")
    plat = CLOAK_PLATFORMS.get(fp.os)
    if plat is None:
        return args          # Linux/Android: CloakBrowser can't present these
    args += [
        f"--fingerprint-platform={plat}",
        f"--fingerprint-hardware-concurrency={fp.hardware_concurrency}",
        f"--fingerprint-device-memory={fp_mod.navigator_device_memory(fp.device_memory):g}",
        f"--fingerprint-screen-width={fp.screen_width}",
        f"--fingerprint-screen-height={fp.screen_height}",
    ]
    if fp.webgl_vendor and fp.webgl_renderer:
        args += [f"--fingerprint-gpu-vendor={fp.webgl_vendor}",
                 f"--fingerprint-gpu-renderer={fp.webgl_renderer}"]
    return args


CAMOUFOX_OS = {"windows": "windows", "macos": "macos", "linux": "linux"}


def camoufox_fingerprint(profile: Profile, user_data_dir) -> dict:
    """The profile's Camoufox (Firefox) fingerprint — generated once, then reused.

    Without a pinned fingerprint Camoufox salts every launch randomly, so each
    session would be a brand-new device. Camoufox derives fonts, voices, GPU and
    noise seeds from the fingerprint it's given, so pinning this pins them all.
    """
    path = Path(user_data_dir) / CAMOUFOX_FP_FILE
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass   # unreadable pin: regenerate below (a new device, unavoidable)
    from camoufox.fingerprints import Screen, generate_fingerprint

    fp = profile.fingerprint
    os_hint = CAMOUFOX_OS.get(fp.os, "windows")
    try:
        # Keep the screen Persona chose as the upper bound, so the generated
        # device is no bigger than the profile says.
        gen = generate_fingerprint(os=os_hint, screen=Screen(
            max_width=fp.screen_width, max_height=fp.screen_height))
    except Exception:
        gen = generate_fingerprint(os=os_hint)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(gen), encoding="utf-8")
    tmp.replace(path)
    return gen


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
    return _locked(_DRIVERS[name]["fn"])


def _locked(fn: Callable) -> Callable:
    """Wrap a driver so the profile's session lock (see ``locks.py``) is held
    for as long as its browser is open. Every launch path goes through here,
    so a profile can never be open twice, whoever started it."""
    def run(profile, store, *args, keep_open=True, **kwargs):
        lock = locks.acquire(store.user_data_path(profile.id))
        try:
            handles = fn(profile, store, *args, keep_open=keep_open, **kwargs)
        except BaseException:
            lock.release()
            raise
        if not keep_open or not handles:
            lock.release()            # the driver already waited for the close
            return handles
        try:
            handles[1].on("close", lambda *_: lock.release())
        except Exception:
            pass                      # released at process exit instead
        return handles
    run.__wrapped__ = fn
    return run


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
        lock = locks.acquire(store.user_data_path(profile.id))
        try:
            with Camoufox(headless=headless, persistent_context=True,
                          user_data_dir=str(store.user_data_path(profile.id))) as browser:
                yield browser
        finally:
            lock.release()
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
                            keep_open: bool, extra_args=None, engine: str = "playwright"):
    fp = profile.fingerprint
    launch_args = [
        f"--window-size={fp.viewport_width},{fp.viewport_height}",
        "--disable-blink-features=AutomationControlled",
        "--no-first-run",
        "--no-default-browser-check",
        # Headless Chrome otherwise renders WebGL in software (SwiftShader), a
        # well-known headless tell whose limits contradict any real GPU. This
        # makes it use the machine's GPU through the normal backend, like a
        # visible window does.
        *(["--enable-gpu"] if headless else []),
        *_webrtc_arg(profile),
        *_dns_lockdown_arg(profile),
        *_extension_args(profile),
        *profile_launch_args(profile)[0],
        *(extra_args or []),
    ]
    geo = launch_geo(profile)
    geolocation = geo["geolocation"]
    locale, languages = launch_languages(profile, geo)
    fp = replace(fp, locale=locale, languages=languages)
    context_opts: dict = {
        "user_agent": fp.user_agent,
        "locale": fp.locale,
        "timezone_id": geo["timezone"],
        "viewport": {"width": fp.viewport_width, "height": fp.viewport_height},
        "screen": {"width": fp.screen_width, "height": fp.screen_height},
        "is_mobile": fp.is_mobile,
        "has_touch": fp.is_mobile,
        "device_scale_factor": fp_mod.pixel_ratio(fp),
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
        context_opts["proxy"] = browser_proxy(profile.proxy).to_playwright()
    if geolocation:
        # Grant the permission too, so a site that asks gets the coordinates
        # rather than a prompt that would stall an unattended session.
        context_opts["geolocation"] = geolocation
        context_opts["permissions"] = ["geolocation"]

    pw = sync_playwright().start()
    context = pw.chromium.launch_persistent_context(
        user_data_dir=str(store.user_data_path(profile.id)),
        headless=headless,
        args=launch_args,
        # Drop Playwright's automation switch so Chrome doesn't show the
        # "controlled by automated test software" infobar.
        ignore_default_args=["--enable-automation"],
        **context_opts,
    )
    context.add_init_script(build_init_script(fp))
    page = context.pages[0] if context.pages else context.new_page()
    _apply_ua_metadata(context, page, fp, engine_chrome_version(engine))
    _open_startup_urls(context, page, profile)

    if keep_open:
        return pw, context, page
    try:
        if not headless:
            page.wait_for_event("close", timeout=0)
    finally:
        context.close()
        pw.stop()
    return None


@register("playwright", requires="playwright")
def _driver_playwright(profile, store, headless=False, keep_open=True, extra_args=None):
    from playwright.sync_api import sync_playwright
    _sync_and_save(profile, store, "playwright")
    return _launch_playwright_like(sync_playwright, profile, store, headless, keep_open, extra_args)


@register("patchright", requires="patchright")
def _driver_patchright(profile, store, headless=False, keep_open=True, extra_args=None):
    # Patchright is an API-compatible, patched drop-in for Playwright.
    from patchright.sync_api import sync_playwright
    _sync_and_save(profile, store, "patchright")
    return _launch_playwright_like(sync_playwright, profile, store, headless, keep_open, extra_args,
                                   engine="patchright")


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
    user_data = store.user_data_path(profile.id)
    kwargs: dict = {
        "headless": headless,
        "os": os_hint,
        "locale": fp.locale,
        "persistent_context": True,
        "user_data_dir": str(user_data),
        # Same device every launch (Camoufox would otherwise re-roll it).
        "fingerprint": camoufox_fingerprint(profile, user_data),
        "i_know_what_im_doing": True,   # silences the custom-fingerprint warning
    }
    own_args = profile_launch_args(profile)[0]
    if own_args:
        kwargs["args"] = own_args            # Firefox flags, for this engine
    if profile.proxy:
        kwargs["proxy"] = browser_proxy(profile.proxy).to_playwright()
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

    _sync_and_save(profile, store, "cloak")
    fp = profile.fingerprint
    user_data = store.user_data_path(profile.id)
    # Headed: no emulated viewport — the page tracks the real window, which keeps
    # outerWidth >= innerWidth coherent (CloakBrowser's own guidance). Passing
    # no_viewport also stops it maximizing, which on a display bigger than the
    # spoofed screen would make the window larger than the "screen"; the
    # --window-size below keeps it inside.
    # The binary ignores --force-device-scale-factor and takes the DPR from the
    # real display, so headless (no display) gets it emulated with the viewport;
    # headed shows the host's own ratio — the trust check flags a mismatch, e.g.
    # a macOS profile on a non-HiDPI screen.
    window: dict = ({"viewport": {"width": fp.viewport_width, "height": fp.viewport_height},
                     "device_scale_factor": fp_mod.pixel_ratio(fp)}
                    if headless else {"no_viewport": True})
    geo = launch_geo(profile)
    geo_opts: dict = {}
    if geo["geolocation"]:
        # Without this a granted prompt would hand the site the host's real fix.
        geo_opts = {"geolocation": geo["geolocation"], "permissions": ["geolocation"]}
    # We resolved the exit IP ourselves: hand it to WebRTC directly. Only when we
    # couldn't (e.g. SOCKS) let CloakBrowser try its own lookup for WebRTC.
    webrtc_ip = [f"--fingerprint-webrtc-ip={geo['ip']}"] if geo["ip"] else []
    context = cloakbrowser.launch_persistent_context(
        user_data_dir=str(user_data),
        headless=headless,
        proxy=browser_proxy(profile.proxy).to_playwright() if profile.proxy else None,
        **window,
        locale=launch_languages(profile, geo)[0],
        timezone=geo["timezone"],     # the exit IP's zone, not the stored one
        geoip=bool(profile.proxy) and not geo["ip"],
        **geo_opts,
        # CloakBrowser launches with --no-sandbox (its stealth args), which makes
        # Chromium show a local "unsupported command-line flag" infobar. --test-type
        # hides that purely-cosmetic bar; it isn't visible to websites (JS can't
        # read command-line flags), so it doesn't affect the fingerprint.
        args=["--test-type", "--no-first-run", "--no-default-browser-check",
              *cloak_identity_args(profile, user_data), *webrtc_ip,
              f"--window-size={fp.viewport_width},{fp.viewport_height}",
              *_webrtc_arg(profile), *_dns_lockdown_arg(profile),
              *_extension_args(profile), *profile_launch_args(profile)[0], *(extra_args or [])],
    )
    page = context.pages[0] if context.pages else context.new_page()
    _open_startup_urls(context, page, profile)

    if keep_open:
        return None, context, page
    try:
        if not headless:
            page.wait_for_event("close", timeout=0)
    finally:
        context.close()
    return None
