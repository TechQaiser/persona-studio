"""
Profile probes: does the proxy work, does anything leak, does the identity hold?

Three questions you want answered *before* an account is on the line:

``check_proxy``   Does traffic actually leave through the proxy, and does the
                  exit country/timezone agree with the identity? Needs internet.
``check_leaks``   Does WebRTC hand out an IP the proxy was supposed to hide?
``check_tls``     What does the TLS/HTTP2 handshake look like, and does it read
                  as a real Chromium? This is the one layer JavaScript can never
                  touch — a server sees it *before* any page code runs — so it's
                  the honest test of whether the engine, not the injected script,
                  is doing the work. Needs internet.
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

# Services that reflect the caller's TLS/HTTP2 fingerprint back as JSON. Read
# through the browser, so it's the browser's real handshake (and proxy) we see.
# Formats differ, so the parser is defensive; order is by how much they return.
TLS_ECHO = [
    "https://tls.peet.ws/api/all",          # ja3 + ja4 + http2, richest
    "https://check.ja3.zone/",              # {hash, fingerprint}
    "https://tools.scrapfly.io/api/fp/ja3",  # {ja3, ...}
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
        dns = check_dns(profile, store, context=context, exit_ip=(info or {}).get("ip"))
        tls = check_tls(profile, store, context=context, engine=engine)

    latency = int((time.time() - started) * 1000)
    if not info:
        return {"ok": False, "error": "no IP service answered — is the proxy reachable?",
                "proxy": profile.proxy.server if profile.proxy else None,
                "latencyMs": latency,
                "checks": leaks["checks"] + dns["checks"] + tls["checks"]}

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
    checks += dns["checks"]
    checks += tls["checks"]
    return {
        "ok": all(c["ok"] for c in checks),
        "proxy": profile.proxy.server if profile.proxy else None,
        "ip": info["ip"],
        "country": got_country or None,
        "city": info.get("city"),
        "timezone": info.get("timezone"),
        "latencyMs": latency,
        "dnsCountries": dns.get("countries"),
        "ja3Hash": tls.get("ja3Hash"),
        "ja4": tls.get("ja4"),
        "checks": checks,
    }


# The echo services don't send CORS headers, so a fetch() from page script is
# blocked. Navigating the page straight to the endpoint sidesteps that — it's a
# top-level request, and the handshake is still the browser's real one — then we
# read the JSON out of the rendered body.
_TLS_PARSE = """
() => {
  const raw = document.body ? document.body.innerText : '';
  let d;
  try { d = JSON.parse(raw); } catch (e) { return null; }
  const tls = d.tls || d;
  const ja3 = tls.ja3 || d.ja3 || d.fingerprint || null;
  const ja3Hash = tls.ja3_hash || d.ja3_hash || d.hash || d.ja3_digest || null;
  const ja4 = tls.ja4 || d.ja4 || (d.ja4_r ? String(d.ja4_r).split('_')[0] : null);

  // Cipher count from the ja3 string's 2nd field (GREASE is stripped there per
  // spec, so this is the "real" suite count).
  let cipherCount = 0;
  if (ja3 && ja3.includes(',')) {
    cipherCount = (ja3.split(',')[1] || '').split('-').filter(Boolean).length;
  } else if (tls.ciphers) {
    cipherCount = tls.ciphers.length;
  }

  // GREASE (RFC 8701) is stripped from ja3/ja4, so look at the raw response:
  // services that list ciphers name it ("TLS_GREASE…") or show a 0x?a?a value.
  // greaseKnown tells us whether the service exposed ciphers at all — if it
  // only gave a ja3 string, absence of GREASE means nothing.
  const greaseKnown = /cipher/i.test(raw) || /grease/i.test(raw);
  const grease = /grease/i.test(raw) || /0x[0-9a-f]a[0-9a-f]a/i.test(raw);

  return {
    ja3, ja3Hash, ja4,
    http2: (d.http2 && (d.http2.akamai_fingerprint_hash || d.http2.akamai_fingerprint)) || null,
    grease, greaseKnown, cipherCount,
  };
}
"""


def _read_tls(page) -> Optional[dict]:
    for url in TLS_ECHO:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            info = page.evaluate(_TLS_PARSE)
            if info and (info.get("ja3Hash") or info.get("ja4")):
                info["source"] = url
                return info
        except Exception:
            continue   # service down or unreachable — try the next
    return None


def check_tls(profile: Profile, store: ProfileStore, context=None,
              engine: Optional[str] = None) -> dict:
    """Read the profile's TLS/HTTP2 handshake back from an echo service.

    This is the layer the whole "JS injection isn't enough" argument is about:
    the TLS ClientHello is sent before the browser has a document, so no page
    script — ours or an anti-detect browser's — can alter it. What shapes it is
    the engine's network stack. Chromium-based engines (playwright, patchright,
    cloak) send Chrome's real handshake because they *are* Chromium; the value
    of checking is to confirm nothing downstream (a proxy that terminates TLS,
    an odd build) has changed it into a tell.
    """
    def run(ctx):
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        return _read_tls(page)

    info = run(context) if context is not None else None
    if info is None and context is None:
        with session(profile, store, engine) as ctx:
            info = run(ctx)

    if not info:
        return {"ok": False, "error": "no TLS echo service answered",
                "checks": [_check("TLS fingerprint readable", False,
                                  "tls.peet.ws / browserleaks unreachable")]}

    ja4 = info.get("ja4") or ""
    checks = [_check("TLS handshake reaches a real endpoint", True,
                     f"JA3 {info['ja3Hash'] or '?'}" + (f" · JA4 {ja4}" if ja4 else ""))]

    # These are the pre-JS tells a server-side detector reads before any page
    # script runs. A real modern browser negotiates TLS 1.3 and HTTP/2; a
    # scripted TLS client (python, go, a misconfigured impersonator) usually
    # can't reproduce both. JA4's first block encodes exactly this ("t13…h2").
    if ja4:
        checks.append(_check(
            "Negotiates TLS 1.3 (browser-grade)", ja4.startswith("t13"),
            f"JA4 starts '{ja4[:4]}', not 't13'"))
        checks.append(_check(
            "Speaks HTTP/2 like a browser", "h2" in ja4.split("_")[0],
            "no h2 in the ALPN — browsers negotiate it, most scripts don't"))

    # GREASE is Chrome/Chromium's signature (RFC 8701). Only assert it when the
    # service actually exposed the cipher list — otherwise its absence is just
    # the ja3 spec stripping it, not a real finding.
    if info.get("greaseKnown"):
        checks.append(_check(
            "Sends GREASE like a real Chrome", bool(info.get("grease")),
            "no GREASE values — this isn't a stock Chromium ClientHello"))

    if info.get("cipherCount"):
        checks.append(_check(
            "Cipher suite list is browser-shaped", info["cipherCount"] >= 10,
            f"only {info['cipherCount']} suite(s); real Chrome offers ~15"))

    return {
        "ok": all(c["ok"] for c in checks),
        "ja3": info.get("ja3"),
        "ja3Hash": info.get("ja3Hash"),
        "ja4": info.get("ja4"),
        "http2": info.get("http2"),
        "grease": info.get("grease") if info.get("greaseKnown") else None,
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
# DNS leak
# --------------------------------------------------------------------------
# A DNS *leak* is when the browser's name lookups skip the proxy and go to your
# own ISP's resolver — so even with the proxy hiding your IP, the sites you
# resolve are visible to (and geo-located at) your real network. The honest way
# to see it is from outside the browser: bash.ws hands out a test id, watches
# which resolver IPs actually query a batch of unique subdomains, and reports
# each one's country/ASN. If a resolver sits in your real country instead of the
# proxy's, that's the leak. Needs internet.
_DNS_ID_URL = "https://bash.ws/id"
_DNS_SUB = "https://{i}.{id}.bash.ws/"
_DNS_RESULT = "https://bash.ws/dnsleak/test/{id}?json"

_DNS_JS = """
async ({idUrl, subTmpl, resultTmpl, n}) => {
  let id;
  try { id = (await (await fetch(idUrl, {cache:'no-store'})).text()).trim(); }
  catch (e) { return {error: 'could not reach the DNS test service'}; }
  if (!id) return {error: 'no test id issued'};
  // Fire N lookups at unique subdomains. We don't care about the responses
  // (no-cors, failures ignored) — the point is to make the browser *resolve*
  // each name so the service can see which resolver did it.
  const jobs = [];
  for (let i = 1; i <= n; i++) {
    const u = subTmpl.replace('{i}', i).replace('{id}', id);
    jobs.push(fetch(u, {mode:'no-cors', cache:'no-store'}).catch(() => {}));
  }
  await Promise.all(jobs);
  try {
    const rows = await (await fetch(resultTmpl.replace('{id}', id), {cache:'no-store'})).json();
    return {id, rows};
  } catch (e) { return {error: 'could not read the DNS result', id}; }
}
"""


def _grade_dns(rows: list, proxy_country: Optional[str], exit_ip: Optional[str] = None) -> dict:
    """Score observed resolvers against the proxy. Pure — no browser — so it can
    be tested without the network.

    bash.ws rows carry a ``type``: ``"ip"`` is the request's own exit IP,
    ``"dns"`` is a resolver that was seen doing the lookups, ``"conclusion"`` is
    a summary line we ignore. We grade the ``"dns"`` rows.
    """
    resolvers = [r for r in rows if (r.get("type") or "").lower() == "dns"]
    countries = sorted({(r.get("country_code") or r.get("country") or "?") for r in resolvers})
    asns = sorted({str(r.get("asn")) for r in resolvers if r.get("asn")})

    checks = [_check("DNS resolution was observed", bool(resolvers),
                     f"{len(resolvers)} resolver(s) seen"
                     + (f" in {', '.join(countries)}" if countries else ""))]

    want = (proxy_country or "").upper()
    if want and resolvers:
        # With a proxy, every resolver should sit in the proxy's country. Any
        # resolver elsewhere is a name lookup that escaped the tunnel.
        strays = [r for r in resolvers
                  if (r.get("country_code") or "").upper() and (r.get("country_code") or "").upper() != want]
        checks.append(_check(
            "DNS stays inside the proxy country (no ISP leak)",
            not strays,
            f"expected all in {want}, but saw {', '.join(countries)}"
            if strays else f"all resolvers in {want}"))
    elif resolvers:
        # No proxy country to compare against — there's nothing to "leak" past,
        # so this is just the baseline: which resolvers your traffic uses.
        checks.append(_check("DNS resolvers (baseline, no proxy country set)", True,
                             ", ".join(countries) or "unknown"))

    return {
        "ok": all(c["ok"] for c in checks),
        "resolvers": [{"ip": r.get("ip"), "country": r.get("country"),
                       "countryCode": r.get("country_code"), "asn": r.get("asn")}
                      for r in resolvers],
        "countries": countries,
        "asns": asns,
        "checks": checks,
    }


def check_dns(profile: Profile, store: ProfileStore, context=None,
              exit_ip: Optional[str] = None, engine: Optional[str] = None) -> dict:
    """Check whether the profile's DNS lookups leak past the proxy.

    Works without a proxy too — then it simply reports which resolvers your
    traffic uses, the baseline you compare a proxied run against.
    """
    def run(ctx):
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            return page.evaluate(_DNS_JS, {"idUrl": _DNS_ID_URL, "subTmpl": _DNS_SUB,
                                           "resultTmpl": _DNS_RESULT, "n": 8})
        except Exception as e:
            return {"error": str(e).splitlines()[0]}

    result = run(context) if context is not None else None
    if result is None:
        with session(profile, store, engine) as ctx:
            result = run(ctx)

    if not result or result.get("error") or not isinstance(result.get("rows"), list):
        return {"ok": False, "error": (result or {}).get("error") or "no DNS result",
                "checks": [_check("DNS leak test reachable", False,
                                  (result or {}).get("error") or "bash.ws unreachable")]}

    country = (profile.proxy.country if profile.proxy else None)
    return _grade_dns(result["rows"], country, exit_ip)


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
  out.screenW = screen.width;
  out.screenH = screen.height;
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

  // Font presence by width measurement — the technique real fingerprinters
  // use. document.fonts.check() is unreliable here: a real Chromium (e.g.
  // CloakBrowser, which doesn't run our patch) answers "yes" for *any* family
  // because it always has a fallback, so it can't tell a real font from a
  // made-up one. Rendering a string in the candidate font vs. a base fallback
  // and comparing widths does tell them apart.
  try {
    const host = document.body || document.documentElement;
    const span = document.createElement('span');
    span.style.cssText = 'position:absolute;left:-9999px;top:-9999px;font-size:72px;white-space:nowrap;';
    span.textContent = 'mmmmmmmmmmlli WwMiI0129@';
    host.appendChild(span);
    const bases = {};
    for (const g of ['monospace', 'serif', 'sans-serif']) { span.style.fontFamily = g; bases[g] = span.offsetWidth; }
    const installed = (fam) => {
      for (const g of ['monospace', 'serif', 'sans-serif']) {
        span.style.fontFamily = '"' + fam + '",' + g;
        if (span.offsetWidth !== bases[g]) return true;
      }
      return false;
    };
    out.fontKnown = installed(probe.knownFont);
    out.fontAlien = installed(probe.alienFont);
    host.removeChild(span);
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

# Ask the page which of a candidate list of fonts actually render. Under the
# Chromium stealth engine this is answered by our patched document.fonts.check
# (so it returns the profile's declared set); under cloak/camoufox it hits the
# real OS font list — which is exactly what the aligner wants to read back.
_FONT_PROBE_JS = """
(fonts) => {
  const out = [];
  try {
    const host = document.body || document.documentElement;
    const span = document.createElement('span');
    span.style.cssText = 'position:absolute;left:-9999px;top:-9999px;font-size:72px;white-space:nowrap;';
    span.textContent = 'mmmmmmmmmmlli WwMiI0129@';
    host.appendChild(span);
    const bases = {};
    for (const g of ['monospace', 'serif', 'sans-serif']) { span.style.fontFamily = g; bases[g] = span.offsetWidth; }
    for (const f of fonts) {
      for (const g of ['monospace', 'serif', 'sans-serif']) {
        span.style.fontFamily = '"' + f + '",' + g;
        if (span.offsetWidth !== bases[g]) { out.push(f); break; }
      }
    }
    host.removeChild(span);
  } catch (e) {}
  return out;
}
"""


def _observe(profile: Profile, store: ProfileStore, engine: Optional[str] = None,
             font_candidates: Optional[list] = None) -> dict:
    """Open the profile and read back everything a fingerprinting script can see.

    Optionally probe ``font_candidates`` to learn which fonts the browser can
    actually render (used by the aligner to discover the real OS font set)."""
    fp = profile.fingerprint
    known_font = fp.fonts[0] if fp.fonts else "Arial"
    with session(profile, store, engine) as context:
        page = _serve_probe_page(context)
        seen = page.evaluate(_TRUST_JS, {"knownFont": known_font, "alienFont": _ALIEN_FONT})
        if font_candidates:
            seen["fontsRendered"] = page.evaluate(_FONT_PROBE_JS, font_candidates)
    return seen


def _grade(fp, seen: dict, engine_name: str) -> dict:
    """Score an observation against a fingerprint. Pure — no browser — so the
    aligner can grade a would-be fingerprint against the same observation."""
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
    if engine_name != "camoufox":
        checks.append(_check(
            "WebGL renderer matches the GPU",
            seen["webglRenderer"] == fp.webgl_renderer,
            f"expected {fp.webgl_renderer}, got {seen['webglRenderer']}"))

        # Prefer the full font probe when we have it (the aligner passes it): it
        # lets us re-grade a rewritten font set against the same observation.
        known_font = fp.fonts[0] if fp.fonts else "Arial"
        if "fontsRendered" in seen:
            rendered = set(seen["fontsRendered"])
            font_known = bool(fp.fonts) and known_font in rendered
            font_alien = _ALIEN_FONT in rendered
        else:
            font_known = seen.get("fontKnown")
            font_alien = seen.get("fontAlien")
        if font_known is not None:
            checks.append(_check(
                "Font probing answers from this OS's font set",
                bool(font_known) and not font_alien,
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


def trust_report(profile: Profile, store: ProfileStore,
                 engine: Optional[str] = None) -> dict:
    """Grade the profile the way a fingerprinting script would.

    Returns ``{score, grade, checks}``. The score is the share of checks that
    pass, so it moves for a real reason and not on a curve.
    """
    seen = _observe(profile, store, engine)
    engine_name = engine or profile.engine or "playwright"
    return _grade(profile.fingerprint, seen, engine_name)


# --------------------------------------------------------------------------
# Auto-adjust: align the profile to what the browser actually presents
# --------------------------------------------------------------------------
import re as _re

from . import devices as _devices
from .fingerprint import build_user_agent as _build_ua


def _os_from_platform(platform: str, fallback: str) -> str:
    p = (platform or "").lower()
    if "win" in p:
        return "windows"
    if "mac" in p:
        return "macos"
    if "arm" in p or "android" in p or "aarch" in p:
        return "android"
    if "linux" in p or "x11" in p:
        return "linux"
    return fallback


def _chrome_from_ua(ua: str) -> Optional[str]:
    m = _re.search(r"Chrome/(\d+\.\d+\.\d+\.\d+)", ua or "")
    return m.group(1) if m else None


def _vendor_from_renderer(renderer: str) -> str:
    r = (renderer or "").lower()
    for token, name in (("nvidia", "NVIDIA"), ("amd", "AMD"), ("radeon", "AMD"),
                        ("intel", "Intel"), ("apple", "Apple"),
                        ("adreno", "Qualcomm"), ("qualcomm", "Qualcomm"),
                        ("mali", "ARM"), ("arm", "ARM")):
        if token in r:
            return f"Google Inc. ({name})"
    return "Google Inc."


def align_to_reality(profile: Profile, store: ProfileStore,
                     engine: Optional[str] = None) -> dict:
    """Make the profile's declared fingerprint match what the browser really
    shows, then re-grade it.

    The trust checker fails whenever the *declared* identity and the *presented*
    one disagree. That gap is unavoidable with an engine that renders the host's
    real hardware (e.g. CloakBrowser shows this machine's GPU/CPU because it
    patches at the C++ level, not from Persona's JS). Rather than paper over it,
    this reads back platform, CPU, memory, GPU, screen, languages, fonts and
    media, and rewrites the fingerprint to those values — regenerating the OS
    identity (UA, platform) when the machine turns out to be a different OS than
    the profile claimed. Afterwards the browser and the profile tell one story,
    so a detector sees no contradiction.

    Returns ``{before, after, changed, checks, os, fingerprint}``.
    """
    all_fonts = sorted({f for pool in _devices.FONTS.values() for f in pool})
    seen = _observe(profile, store, engine, font_candidates=all_fonts)
    fp = profile.fingerprint
    engine_name = engine or profile.engine or "playwright"
    before = _grade(fp, seen, engine_name)

    changed: list[str] = []

    def apply(attr: str, value, label: Optional[str] = None):
        if value is None:
            return
        if getattr(fp, attr) != value:
            setattr(fp, attr, value)
            changed.append(label or attr)

    # 1. Operating system — the root that everything else hangs off.
    os_key = _os_from_platform(seen.get("platform"), fp.os)
    chrome = _chrome_from_ua(seen.get("userAgent")) or fp.chrome_version
    if os_key != fp.os:
        fp.os = os_key
        fp.is_mobile = (os_key == "android")
        changed.append("os")
    fp.chrome_version = chrome
    apply("platform", _devices.NAV_PLATFORM.get(os_key, seen.get("platform")), "platform")
    fp.ch_platform = _devices.CH_PLATFORM.get(os_key, fp.ch_platform)
    apply("user_agent", _build_ua(os_key, chrome), "userAgent")

    # 2. Hardware, straight from the machine.
    apply("hardware_concurrency", seen.get("cores"), "cores")
    apply("device_memory", seen.get("memory"), "memory")
    if seen.get("webglRenderer"):
        apply("webgl_renderer", seen["webglRenderer"], "webglRenderer")
        fp.webgl_vendor = seen.get("webglVendor") or _vendor_from_renderer(seen["webglRenderer"])
    if seen.get("screenW") and seen.get("screenH"):
        if (fp.screen_width, fp.screen_height) != (seen["screenW"], seen["screenH"]):
            fp.screen_width, fp.screen_height = seen["screenW"], seen["screenH"]
            fp.viewport_width = min(fp.viewport_width or fp.screen_width, fp.screen_width)
            fp.viewport_height = min(fp.viewport_height or fp.screen_height, fp.screen_height)
            changed.append("screen")

    # 3. Media + languages, as reported.
    apply("cameras", seen.get("cameras"), "cameras")
    apply("microphones", seen.get("microphones"), "microphones")
    if seen.get("languages") and list(fp.languages) != list(seen["languages"]):
        fp.languages = list(seen["languages"])
        changed.append("languages")

    # 3b. Timezone + locale: match the machine's real clock. An engine that shows
    #     the host timezone (e.g. CloakBrowser) otherwise fails the "timezone
    #     matches" check forever, capping auto-adjust at B. We only move it when a
    #     locale whose canonical zone is that timezone exists, so the profile stays
    #     coherent (locale still implies its timezone).
    tz = seen.get("timezone")
    if tz:
        loc = next((l for l, (z, _lg) in _devices.LOCALES.items() if z == tz), None)
        if loc:
            if fp.timezone != tz:
                fp.timezone = tz
                changed.append("timezone")
            if fp.locale != loc:
                fp.locale = loc
                changed.append("locale")

    # 4. Fonts: keep this OS's fonts that actually render here (a real subset),
    #    falling back to the full OS set if the probe came back empty.
    rendered = set(seen.get("fontsRendered") or [])
    os_fonts = sorted(f for f in _devices.FONTS.get(os_key, []) if f in rendered)
    if not os_fonts:
        os_fonts = sorted(_devices.FONTS.get(os_key, []))
    if sorted(fp.fonts) != os_fonts:
        fp.fonts = os_fonts
        changed.append("fonts")

    store.save(profile)
    # The user-agent is fed to the engine at launch, so it will report the new
    # value next time — grade against that, not the stale observed UA.
    after = _grade(fp, {**seen, "userAgent": fp.user_agent}, engine_name)

    keep = ("score", "grade", "passed", "total")
    return {
        "before": {k: before[k] for k in keep},
        "after": {k: after[k] for k in keep},
        "changed": sorted(set(changed)),
        "checks": after["checks"],
        "os": os_key,
        "fingerprint": {
            "os": fp.os,
            "userAgent": fp.user_agent,
            "browserVersion": fp.chrome_version,
            "platform": fp.platform,
            "cores": fp.hardware_concurrency,
            "memory": fp.device_memory,
            "screen": f"{fp.screen_width}x{fp.screen_height}",
            "webglVendor": fp.webgl_vendor,
            "webglRenderer": fp.webgl_renderer,
            "cameras": fp.cameras,
            "microphones": fp.microphones,
            "languages": list(fp.languages),
            "locale": fp.locale,
            "timezone": fp.timezone,
        },
    }
