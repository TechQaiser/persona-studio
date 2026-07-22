"""
Profile probes: does the proxy work, does anything leak, does the identity hold?

Three questions you want answered *before* an account is on the line:

``check_proxy``   Does traffic actually leave through the proxy, and does the
                  exit country/timezone agree with the identity? Needs internet.
``check_leaks``   Does WebRTC hand out an IP the proxy was supposed to hide?
``trust_report``  Would this browser pass an inspection right now? Runs the
                  checks a fingerprinting script would run (webdriver, plugins,
                  UA vs platform, WebGL, fonts, canvas stability…) and scores
                  the result. Fully offline — the page it grades is served from
                  memory, so nothing about the profile touches the network.

A "check" is always ``{"name", "ok", "detail"}`` so the CLI, the API and the
dashboard can render the same list without knowing what each check means.
"""

from __future__ import annotations

import time
from typing import Optional

from .drivers import session
from .models import Profile
from .store import ProfileStore

# Services that echo the caller's IP. Tried in order — free endpoints come and
# go, and a proxy test that fails because one host is down is worse than useless.
IP_ECHO = [
    "https://ipapi.co/json/",
    "https://ipwho.is/",
    "https://api.ipify.org/?format=json",
]

# A blank page served from memory. Fingerprinting APIs want a real secure
# origin (mediaDevices, permissions), but the profile shouldn't have to make a
# request to be graded — so we intercept the navigation and answer it ourselves.
PROBE_URL = "https://persona.probe/"
PROBE_HTML = "<!doctype html><meta charset=utf-8><title>persona probe</title>"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "ok": bool(ok), "detail": detail}


def _serve_probe_page(context):
    """Give the context a page on a real https origin without touching the network."""
    page = context.pages[0] if context.pages else context.new_page()
    page.route("**/*", lambda route: route.fulfill(
        status=200, content_type="text/html", body=PROBE_HTML))
    page.goto(PROBE_URL, wait_until="domcontentloaded", timeout=15000)
    return page


# --------------------------------------------------------------------------
# Proxy + leaks
# --------------------------------------------------------------------------
_IP_JS = """
async (urls) => {
  for (const url of urls) {
    try {
      const res = await fetch(url, { cache: 'no-store' });
      if (!res.ok) continue;
      const text = (await res.text()).trim();
      let data;
      try { data = JSON.parse(text); } catch { data = { ip: text }; }
      const ip = data.ip || data.query || data.IPv4;
      if (!ip) continue;
      return {
        source: url,
        ip,
        country: data.country_code || data.country || data.countryCode || null,
        city: data.city || null,
        timezone: data.timezone?.id || data.timezone || null,
      };
    } catch (e) { /* try the next one */ }
  }
  return null;
}
"""

# Ask the browser for its ICE candidates. If a proxy is in play, any public
# address here is an address the proxy failed to hide.
_WEBRTC_JS = """
() => new Promise((resolve) => {
  const found = new Set();
  let pc;
  try { pc = new RTCPeerConnection({ iceServers: [{ urls: 'stun:stun.l.google.com:19302' }] }); }
  catch (e) { return resolve({ supported: false, ips: [] }); }
  const done = () => { try { pc.close(); } catch (e) {} resolve({ supported: true, ips: [...found] }); };
  pc.onicecandidate = (e) => {
    if (!e.candidate) return done();
    const m = /([0-9]{1,3}(\\.[0-9]{1,3}){3}|[a-f0-9]{1,4}(:[a-f0-9]{0,4}){2,7})/i
      .exec(e.candidate.candidate || '');
    if (m && !m[0].endsWith('.local')) found.add(m[0]);
  };
  try { pc.createDataChannel('probe'); pc.createOffer().then((o) => pc.setLocalDescription(o)); }
  catch (e) { return done(); }
  setTimeout(done, 3000);
})
"""


def _is_private(ip: str) -> bool:
    """Private/link-local addresses are normal to see; public ones are the leak."""
    if ":" in ip:                       # IPv6: fc00::/7 (unique local), fe80::/10
        low = ip.lower()
        return low.startswith(("fc", "fd", "fe8", "fe9", "fea", "feb", "::1"))
    parts = ip.split(".")
    if len(parts) != 4 or not all(p.isdigit() for p in parts):
        return True
    a, b = int(parts[0]), int(parts[1])
    return (a == 10 or a == 127 or (a == 172 and 16 <= b <= 31)
            or (a == 192 and b == 168) or (a == 169 and b == 254))


def check_proxy(profile: Profile, store: ProfileStore,
                engine: Optional[str] = None) -> dict:
    """Route a real request through the profile and report where it came out.

    Works with or without a proxy: without one it simply tells you your own exit
    IP, which is the baseline you compare a proxy against.
    """
    started = time.time()
    with session(profile, store, engine) as context:
        page = context.pages[0] if context.pages else context.new_page()
        try:
            info = page.evaluate(_IP_JS, IP_ECHO)
        except Exception as e:
            return {"ok": False, "error": str(e).splitlines()[0],
                    "proxy": profile.proxy.server if profile.proxy else None,
                    "checks": []}
        leaks = check_leaks(profile, store, context=context, exit_ip=(info or {}).get("ip"))

    latency = int((time.time() - started) * 1000)
    if not info:
        return {"ok": False, "error": "no IP service answered — is the proxy reachable?",
                "proxy": profile.proxy.server if profile.proxy else None,
                "latencyMs": latency, "checks": leaks["checks"]}

    fp = profile.fingerprint
    checks = [_check("Traffic reaches the internet", True,
                     f"exit IP {info['ip']}" + (f" · {info['city']}" if info.get("city") else ""))]

    want_country = (profile.proxy.country or "").upper() if profile.proxy else ""
    got_country = (info.get("country") or "").upper()
    if want_country:
        checks.append(_check(
            "Exit country matches the proxy setting",
            got_country == want_country,
            f"expected {want_country}, got {got_country or 'unknown'}"))
    elif got_country:
        checks.append(_check("Exit country", True, got_country))

    if info.get("timezone"):
        checks.append(_check(
            "Timezone matches the exit location", info["timezone"] == fp.timezone,
            f"profile says {fp.timezone}, the IP looks like {info['timezone']}"))

    checks += leaks["checks"]
    return {
        "ok": all(c["ok"] for c in checks),
        "proxy": profile.proxy.server if profile.proxy else None,
        "ip": info["ip"],
        "country": got_country or None,
        "city": info.get("city"),
        "timezone": info.get("timezone"),
        "latencyMs": latency,
        "checks": checks,
    }


def check_leaks(profile: Profile, store: ProfileStore, context=None,
                exit_ip: Optional[str] = None, engine: Optional[str] = None) -> dict:
    """Look for IPs WebRTC hands out that the proxy was meant to hide."""
    def run(ctx):
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            return page.evaluate(_WEBRTC_JS)
        except Exception:
            return {"supported": False, "ips": []}

    result = run(context) if context is not None else None
    if result is None:
        with session(profile, store, engine) as ctx:
            result = run(ctx)

    public = [ip for ip in result.get("ips", []) if not _is_private(ip)]
    exposed = [ip for ip in public if not exit_ip or ip != exit_ip]
    detail = ", ".join(exposed) if exposed else "no public address exposed"
    return {
        "webrtcIps": result.get("ips", []),
        "exposed": exposed,
        "checks": [_check("WebRTC does not leak your real IP", not exposed, detail)],
    }


# --------------------------------------------------------------------------
# Trust report
# --------------------------------------------------------------------------
# Everything a fingerprinting script can read in one pass. Kept as one evaluate
# so the page is measured in a single consistent state.
_TRUST_JS = """
async (probe) => {
  const out = {};
  out.webdriver = navigator.webdriver;
  out.webdriverOwn = Object.prototype.hasOwnProperty.call(navigator, 'webdriver');
  out.hasChrome = !!window.chrome;
  out.plugins = navigator.plugins.length;
  out.languages = [...navigator.languages];
  out.platform = navigator.platform;
  out.userAgent = navigator.userAgent;
  out.cores = navigator.hardwareConcurrency;
  out.memory = navigator.deviceMemory;
  out.timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;

  try {
    const gl = document.createElement('canvas').getContext('webgl');
    const ext = gl && gl.getExtension('WEBGL_debug_renderer_info');
    out.webglVendor = ext ? gl.getParameter(37445) : null;
    out.webglRenderer = ext ? gl.getParameter(37446) : null;
  } catch (e) { out.webglVendor = out.webglRenderer = null; }

  // A patched function must still report native code — and so must the
  // machinery doing the masking, or the mask is the tell.
  const native = (fn) => /^function [^(]*\\(\\) \\{ \\[native code\\] \\}$/
    .test(Function.prototype.toString.call(fn));
  out.toStringNative = native(navigator.permissions.query)
    && native(Function.prototype.toString)
    && native(Object.getOwnPropertyDescriptor(Navigator.prototype, 'webdriver').get);

  try {
    const p = await navigator.permissions.query({ name: 'notifications' });
    out.permissionsAgree = p.state === Notification.permission;
  } catch (e) { out.permissionsAgree = false; }

  // Canvas must read the same twice — noise that moves is itself a signal.
  try {
    const c = document.createElement('canvas');
    c.width = 240; c.height = 60;
    const ctx = c.getContext('2d');
    ctx.textBaseline = 'top';
    ctx.font = '14px Arial';
    ctx.fillStyle = '#f60';
    ctx.fillRect(0, 0, 100, 30);
    ctx.fillStyle = '#069';
    ctx.fillText('persona-probe', 2, 15);
    out.canvasStable = c.toDataURL() === c.toDataURL();
    out.canvasEmpty = c.toDataURL().length < 100;
  } catch (e) { out.canvasStable = false; }

  try {
    out.fontKnown = document.fonts.check(`12px "${probe.knownFont}"`);
    out.fontAlien = document.fonts.check(`12px "${probe.alienFont}"`);
  } catch (e) { out.fontKnown = out.fontAlien = null; }

  try {
    const devs = await navigator.mediaDevices.enumerateDevices();
    out.cameras = devs.filter((d) => d.kind === 'videoinput').length;
    out.microphones = devs.filter((d) => d.kind === 'audioinput').length;
  } catch (e) { out.cameras = out.microphones = null; }

  return out;
}
"""

# A font that exists on no mainstream OS. If font probing says it's installed,
# the answer isn't coming from a real font list.
_ALIEN_FONT = "Persona Nonexistent Grotesk"


def trust_report(profile: Profile, store: ProfileStore,
                 engine: Optional[str] = None) -> dict:
    """Grade the profile the way a fingerprinting script would.

    Returns ``{score, grade, checks}``. The score is the share of checks that
    pass, so it moves for a real reason and not on a curve.
    """
    fp = profile.fingerprint
    known_font = fp.fonts[0] if fp.fonts else "Arial"

    with session(profile, store, engine) as context:
        page = _serve_probe_page(context)
        seen = page.evaluate(_TRUST_JS, {"knownFont": known_font, "alienFont": _ALIEN_FONT})

    checks = [
        _check("navigator.webdriver is false", seen["webdriver"] is False,
               f"reads {seen['webdriver']!r}"),
        _check("webdriver isn't an own property of navigator", not seen["webdriverOwn"],
               "real Chrome defines it on the prototype"),
        _check("window.chrome exists", seen["hasChrome"],
               "missing on plain automated Chrome"),
        _check("navigator.plugins isn't empty", seen["plugins"] > 0,
               f"{seen['plugins']} plugin(s)"),
        _check("User-Agent matches the profile", seen["userAgent"] == fp.user_agent,
               seen["userAgent"]),
        _check("navigator.platform matches the OS", seen["platform"] == fp.platform,
               f"expected {fp.platform}, got {seen['platform']}"),
        _check("Languages match the locale", seen["languages"] == list(fp.languages),
               f"expected {fp.languages}, got {seen['languages']}"),
        _check("CPU cores match", seen["cores"] == fp.hardware_concurrency,
               f"expected {fp.hardware_concurrency}, got {seen['cores']}"),
        _check("Device memory matches", seen["memory"] == fp.device_memory,
               f"expected {fp.device_memory}, got {seen['memory']}"),
        _check("Timezone matches the locale", seen["timezone"] == fp.timezone,
               f"expected {fp.timezone}, got {seen['timezone']}"),
        _check("Patched functions still look native", seen["toStringNative"],
               "toString() on a patched function must read '[native code]'"),
        _check("permissions.query agrees with Notification.permission",
               seen["permissionsAgree"]),
        _check("Canvas reads the same twice", bool(seen.get("canvasStable")),
               "noise that changes between reads is a detection signal"),
    ]

    # WebGL and font/media spoofing only apply to the Chromium engines — Camoufox
    # brings its own, so a mismatch there isn't a fault of this profile.
    engine_name = engine or profile.engine or "playwright"
    if engine_name != "camoufox":
        checks.append(_check(
            "WebGL renderer matches the GPU",
            seen["webglRenderer"] == fp.webgl_renderer,
            f"expected {fp.webgl_renderer}, got {seen['webglRenderer']}"))
        if seen.get("fontKnown") is not None:
            checks.append(_check(
                "Font probing answers from this OS's font set",
                bool(seen["fontKnown"]) and not seen["fontAlien"],
                f"'{known_font}' should exist, '{_ALIEN_FONT}' should not"))
        if seen.get("cameras") is not None:
            checks.append(_check(
                "Media devices match the profile",
                seen["cameras"] == fp.cameras and seen["microphones"] == fp.microphones,
                f"expected {fp.cameras} camera(s)/{fp.microphones} mic(s), "
                f"got {seen['cameras']}/{seen['microphones']}"))

    passed = sum(1 for c in checks if c["ok"])
    score = round(100 * passed / len(checks))
    grade = "A" if score >= 95 else "B" if score >= 85 else "C" if score >= 70 else "D"
    return {"score": score, "grade": grade, "passed": passed,
            "total": len(checks), "checks": checks}
