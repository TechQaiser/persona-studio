"""
HTTP API for the dashboard.

The React dashboard is a thin front-end; this module is the bridge that lets it
drive the *real* engine. It wraps :class:`ProfileStore`, the fingerprint
generator/validator and the launcher behind a small JSON API, and it manages the
lifecycle of launched browsers.

Design notes
------------
* The dashboard has a richer profile shape than the engine (folders, per-signal
  spoof modes, media counts, …). To keep the UI lossless we store the dashboard
  profile JSON as-is in ``<data-dir>/dashboard`` and only convert to an engine
  :class:`Fingerprint`/:class:`Profile` at launch time.
* Launching runs ``persona launch <id>`` as a subprocess. That sidesteps the
  hazards of driving Playwright's sync API from inside an async web server, and
  makes "stop" a clean process terminate. A profile is "running" as long as its
  subprocess is alive.

Run it with:  ``persona serve``  (see ``cli.py``).
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from . import cookies as cookies_mod
from . import devices
from .fingerprint import generate, validate
from .models import Fingerprint, Profile, Proxy
from .store import ProfileStore


def _require_fastapi():
    try:
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401
    except ImportError as e:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "The API server needs FastAPI and Uvicorn.\n"
            'Install them with:  pip install -e ".[api]"'
        ) from e


# --------------------------------------------------------------------------
# OS name mapping between the dashboard ("Windows") and engine ("windows").
# --------------------------------------------------------------------------
OS_TO_ENGINE = {"Windows": "windows", "macOS": "macos", "Linux": "linux", "Android": "android"}
OS_TO_DASH = {v: k for k, v in OS_TO_ENGINE.items()}


class DashboardStore:
    """Persists dashboard-shaped profile dicts, one JSON file per profile."""

    def __init__(self, root: Path):
        self.dir = root / "dashboard"
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, pid: str) -> Path:
        return self.dir / f"{pid}.json"

    def list(self) -> list[dict]:
        out = []
        for f in sorted(self.dir.glob("*.json")):
            try:
                out.append(json.loads(f.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                continue
        return sorted(out, key=lambda p: p.get("_created", 0))

    def get(self, pid: str) -> Optional[dict]:
        f = self._path(pid)
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None

    def save(self, prof: dict) -> dict:
        if not prof.get("id"):
            prof["id"] = uuid.uuid4().hex[:12]
        prof.setdefault("_created", time.time())
        self._path(prof["id"]).write_text(json.dumps(prof, indent=2), encoding="utf-8")
        return prof

    def delete(self, pid: str) -> bool:
        f = self._path(pid)
        if not f.exists():
            return False
        f.unlink()
        return True


class ProxyPool:
    """A managed list of proxies the dashboard can import, test and assign."""

    def __init__(self, root: Path):
        self.path = root / "proxies.json"

    def list(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []

    def _save(self, items: list[dict]):
        self.path.write_text(json.dumps(items, indent=2), encoding="utf-8")

    def add_many(self, proxies: list[dict]) -> list[dict]:
        items = self.list()
        seen = {(p["host"], str(p["port"])) for p in items}
        added = []
        for pr in proxies:
            key = (pr["host"], str(pr["port"]))
            if key in seen:
                continue
            entry = {**pr, "id": uuid.uuid4().hex[:12], "status": "untested"}
            items.append(entry)
            seen.add(key)
            added.append(entry)
        self._save(items)
        return added

    def get(self, pid: str) -> Optional[dict]:
        return next((p for p in self.list() if p.get("id") == pid), None)

    def update(self, pid: str, patch: dict) -> Optional[dict]:
        items = self.list()
        out = None
        for p in items:
            if p.get("id") == pid:
                p.update(patch)
                out = p
        if out:
            self._save(items)
        return out

    def delete(self, pid: str) -> bool:
        items = self.list()
        kept = [p for p in items if p.get("id") != pid]
        if len(kept) == len(items):
            return False
        self._save(kept)
        return True


def _vendor_for(renderer: str) -> str:
    """Guess a WebGL vendor string from a renderer string's GPU family."""
    r = (renderer or "").lower()
    for token, name in (("nvidia", "NVIDIA"), ("radeon", "AMD"), ("amd", "AMD"),
                        ("intel", "Intel"), ("apple", "Apple"),
                        ("adreno", "Qualcomm"), ("qualcomm", "Qualcomm"),
                        ("mali", "ARM"), ("arm", "ARM")):
        if token in r:
            return f"Google Inc. ({name})"
    return "Google Inc."


def _engine_webgl(os_key: str, dash_renderer: str, dash_vendor: str = "") -> tuple[str, str]:
    """Resolve a dashboard profile's GPU into an engine WebGL vendor/renderer.

    The dashboard string is passed through as-is (not remapped to the curated
    pool), so a real GPU written by `persona align` survives the round-trip and
    the profile keeps matching its browser. Only a blank renderer falls back to
    a curated default."""
    renderer = (dash_renderer or "").strip()
    vendor = (dash_vendor or "").strip()
    if not renderer:
        return (devices.WEBGL.get(os_key) or devices.WEBGL["windows"])[0]
    return (vendor or _vendor_for(renderer)), renderer


def _parse_lines(raw) -> list[str]:
    """Accept a newline-separated string (or a list) and return clean entries."""
    if not raw:
        return []
    parts = raw if isinstance(raw, list) else raw.splitlines()
    return [p.strip() for p in parts if p.strip()]


def _parse_startup_urls(raw) -> list[str]:
    """Accept a newline/comma/space-separated string (or list) of URLs and
    return a clean list, adding a scheme where one is missing."""
    if isinstance(raw, str):
        raw = raw.replace(",", "\n")
    urls = []
    for u in _parse_lines(raw):
        if "://" not in u and not u.startswith("about:"):
            u = "https://" + u
        urls.append(u)
    return urls


def to_engine_profile(d: dict) -> Profile:
    """Convert a stored dashboard profile dict into an engine :class:`Profile`."""
    os_key = OS_TO_ENGINE.get(d.get("os", "Windows"), "windows")
    is_mobile = os_key == "android"

    try:
        sw, sh = (int(x) for x in str(d.get("screen", "1920x1080")).lower().split("x"))
    except ValueError:
        sw, sh = 1920, 1080
    if is_mobile:
        vw, vh = sw, max(1, sh - 80)
    else:
        vw, vh = sw, max(1, sh - 88)

    locale = d.get("locale", "en-US")
    tz, langs = devices.LOCALES.get(locale, devices.LOCALES["en-US"])
    vendor, renderer = _engine_webgl(os_key, d.get("webglRenderer", ""), d.get("webglVendor", ""))

    fp = Fingerprint(
        os=os_key,
        user_agent=d.get("userAgent") or "",
        platform=devices.NAV_PLATFORM[os_key],
        ch_platform=devices.CH_PLATFORM[os_key],
        chrome_version=d.get("browserVersion", "128.0.0.0"),
        screen_width=sw,
        screen_height=sh,
        viewport_width=vw,
        viewport_height=vh,
        hardware_concurrency=int(d.get("cores", 8)),
        device_memory=int(d.get("memory", 16)),
        fonts=devices.FONTS.get(os_key, []),
        cameras=int(d.get("mediaVideo", 1)),
        microphones=int(d.get("mediaAudio", 1)),
        webgl_vendor=vendor,
        webgl_renderer=renderer,
        locale=locale,
        timezone=d.get("timezone") or tz,
        languages=langs,
        is_mobile=is_mobile,
        seed=int(d.get("seed") or 0) or generate(os=os_key).seed,
    )

    proxy = None
    px = d.get("proxy")
    if px and px.get("host"):
        scheme = {"HTTP": "http", "HTTPS": "http", "SOCKS5": "socks5"}.get(px.get("type", "HTTP"), "http")
        proxy = Proxy(
            server=f"{scheme}://{px['host']}:{px.get('port', '')}".rstrip(":"),
            username=px.get("user") or None,
            password=px.get("pass") or None,
            country=px.get("country") or None,
        )

    return Profile(
        id=d.get("id") or "unsaved",
        name=d.get("name", "profile"),
        fingerprint=fp,
        proxy=proxy,
        notes=d.get("notes", ""),
        tags=d.get("tags", []),
        engine=d.get("engine", "playwright"),
        startup_urls=_parse_startup_urls(d.get("startupUrls")),
        extensions=_parse_lines(d.get("extensions")),
    )


def _proxy_to_dash(proxy) -> Optional[dict]:
    """Turn an engine Proxy into the dashboard's proxy dict."""
    if not proxy or not proxy.server:
        return None
    server = proxy.server
    scheme = "http"
    if "://" in server:
        scheme, server = server.split("://", 1)
    host, _, port = server.partition(":")
    kind = {"http": "HTTP", "https": "HTTPS", "socks5": "SOCKS5", "socks4": "SOCKS4"}.get(scheme.lower(), "HTTP")
    return {"type": kind, "host": host, "port": port,
            "user": proxy.username or "", "pass": proxy.password or "",
            "country": proxy.country or ""}


def to_dashboard_profile(prof: Profile) -> dict:
    """Convert an engine :class:`Profile` into a dashboard-shaped dict.

    The reverse of :func:`to_engine_profile` — used when the engine produces a
    profile (an import) that the dashboard then owns and displays."""
    fp = prof.fingerprint
    return {
        "name": prof.name,
        "folder": "Facebook Ads",
        "status": "stopped",
        "os": OS_TO_DASH.get(fp.os, "Windows"),
        "engine": prof.engine or "playwright",
        "browser": "Chrome",
        "browserVersion": fp.chrome_version,
        "userAgent": fp.user_agent,
        "screen": f"{fp.screen_width}x{fp.screen_height}",
        "cores": fp.hardware_concurrency,
        "memory": fp.device_memory,
        "webglVendor": fp.webgl_vendor,
        "webglRenderer": fp.webgl_renderer,
        "canvas": "Noise", "webrtc": "Altered", "audio": "Noise", "fonts": "Masked",
        "locale": fp.locale, "timezone": fp.timezone, "geo": "Prompt",
        "mediaVideo": fp.cameras, "mediaAudio": fp.microphones, "dnt": False,
        "proxy": _proxy_to_dash(prof.proxy),
        "notes": prof.notes or "",
        "tags": list(prof.tags),
        "startupUrls": "\n".join(prof.startup_urls or []),
        "extensions": "\n".join(prof.extensions or []),
        "lastActive": "never",
    }


def _rel_time(ts: Optional[float]) -> str:
    """Human 'last active' label from a unix timestamp."""
    if not ts:
        return "never"
    secs = max(0.0, time.time() - ts)
    if secs < 60:
        return "just now"
    mins = secs / 60
    if mins < 60:
        return f"{int(mins)}m ago"
    hours = mins / 60
    if hours < 24:
        return f"{int(hours)}h ago"
    return f"{int(hours / 24)}d ago"


def dashboard_coherence(d: dict) -> list[str]:
    """Run the real engine validator against a dashboard profile."""
    try:
        return validate(to_engine_profile(d).fingerprint)
    except Exception as e:  # pragma: no cover - defensive
        return [f"could not validate: {e}"]


def create_app(data_dir: Optional[str] = None, start_scheduler: bool = True):
    _require_fastapi()
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware

    from .scheduler import ScheduleStore, due_schedules, next_run_at

    engine_store = ProfileStore(data_dir)
    dash = DashboardStore(engine_store.root)
    pool = ProxyPool(engine_store.root)
    sched = ScheduleStore(engine_store.root)
    running: dict[str, subprocess.Popen] = {}
    attached: dict[str, dict] = {}   # pid -> CDP connection info while attached

    app = FastAPI(title="Persona API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def is_running(pid: str) -> bool:
        proc = running.get(pid)
        if proc is None:
            return False
        if proc.poll() is not None:      # exited (browser was closed)
            running.pop(pid, None)
            # Session just ended — record when it was last active.
            stored = dash.get(pid)
            if stored is not None:
                stored["_last_active"] = time.time()
                dash.save(stored)
            return False
        return True

    def decorate(d: dict) -> dict:
        # Attach live run state. Coherence is computed by the dashboard itself
        # (its meter mirrors the validator), so we don't duplicate it here.
        d = dict(d)
        running_now = is_running(d["id"])
        d["status"] = "running" if running_now else "stopped"
        d["lastActive"] = "now" if running_now else _rel_time(d.get("_last_active"))
        return d

    @app.get("/api/health")
    def health():
        return {"ok": True, "version": "0.1.0"}

    @app.get("/api/engines")
    def engines():
        from . import drivers
        return drivers.available()

    @app.get("/api/config")
    def get_config():
        return {"default_engine": engine_store.get_default_engine()}

    @app.put("/api/config")
    def set_config(cfg: dict):
        from . import drivers
        name = cfg.get("default_engine")
        if name is not None:
            if name not in drivers.names():
                raise HTTPException(400, f"unknown engine '{name}'")
            engine_store.set_default_engine(name)
        return {"default_engine": engine_store.get_default_engine()}

    def _remember_engine(profile: dict):
        # "Last engine wins": the engine picked for a profile becomes the
        # default for the next new profile.
        eng = profile.get("engine")
        if eng:
            engine_store.set_default_engine(eng)

    @app.get("/api/profiles")
    def list_profiles():
        return [decorate(p) for p in dash.list()]

    @app.post("/api/profiles")
    def create_profile(profile: dict):
        profile.pop("_new", None)
        if not profile.get("engine"):
            profile["engine"] = engine_store.get_default_engine()
        _remember_engine(profile)
        saved = dash.save(profile)
        return decorate(saved)

    @app.put("/api/profiles/{pid}")
    def update_profile(pid: str, profile: dict):
        if not dash.get(pid):
            raise HTTPException(404, "profile not found")
        profile["id"] = pid
        profile.pop("_new", None)
        _remember_engine(profile)
        return decorate(dash.save(profile))

    @app.delete("/api/profiles/{pid}")
    def delete_profile(pid: str):
        if is_running(pid):
            _stop(pid)
        engine_store.delete(pid)
        if not dash.delete(pid):
            raise HTTPException(404, "profile not found")
        return {"ok": True}

    @app.post("/api/profiles/{pid}/launch")
    def launch_profile(pid: str):
        d = dash.get(pid)
        if not d:
            raise HTTPException(404, "profile not found")
        if is_running(pid):
            return decorate(d)
        # Materialise a real engine profile, then open it in its own process.
        engine_store.save(to_engine_profile(d))
        proc = subprocess.Popen(
            [sys.executable, "-m", "persona", "--data-dir", str(engine_store.root),
             "launch", pid],
        )
        running[pid] = proc
        return decorate(d)

    def _stop(pid: str):
        proc = running.pop(pid, None)
        attached.pop(pid, None)          # forget any CDP session it was serving
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    @app.post("/api/profiles/{pid}/stop")
    def stop_profile(pid: str):
        d = dash.get(pid)
        if not d:
            raise HTTPException(404, "profile not found")
        _stop(pid)
        return decorate(d)

    def _run_cli(*cli_args: str, allow_fail: bool = False) -> str:
        """Run a persona subcommand in its own process (same reasoning as launch:
        keeps sync Playwright out of the web server) and return its output.

        ``allow_fail`` is for commands whose non-zero exit means "the thing you
        asked about is unhealthy", not "the command broke" — a failing proxy test
        still has a result worth showing.
        """
        proc = subprocess.run(
            [sys.executable, "-m", "persona", "--data-dir", str(engine_store.root), *cli_args],
            capture_output=True, text=True,
        )
        if proc.returncode != 0 and not (allow_fail and proc.stdout.strip()):
            raise HTTPException(500, (proc.stdout + proc.stderr).strip() or "command failed")
        return proc.stdout

    def _prepare(pid: str) -> dict:
        """Fetch a dashboard profile, refuse if its session is busy, and make sure
        the engine-side profile exists so a subcommand can open it."""
        d = dash.get(pid)
        if not d:
            raise HTTPException(404, "profile not found")
        if is_running(pid):
            raise HTTPException(409, "stop the profile first — its session is in use")
        engine_store.save(to_engine_profile(d))
        return d

    @app.get("/api/profiles/{pid}/cookies")
    def export_cookies(pid: str):
        _prepare(pid)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "cookies.json"
            _run_cli("cookies", "export", pid, str(out))
            data = json.loads(out.read_text(encoding="utf-8"))
        return {"cookies": data.get("cookies", [])}

    @app.post("/api/profiles/{pid}/cookies")
    def import_cookies(pid: str, body: dict):
        _prepare(pid)
        # Accept either parsed cookies or the raw text of a file the user picked,
        # so the browser doesn't have to know which format it is holding.
        raw = body.get("text")
        if raw is None:
            raw = json.dumps({"cookies": body.get("cookies") or []})
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "cookies.json"
            src.write_text(raw, encoding="utf-8")
            args = ["cookies", "import", pid, str(src)]
            if body.get("clear"):
                args.append("--clear")
            _run_cli(*args)
        return {"ok": True, "imported": len(cookies_mod.parse(raw))}

    @app.post("/api/profiles/{pid}/proxy-test")
    def proxy_test(pid: str):
        _prepare(pid)
        # --json makes the CLI the single implementation for both front doors.
        return json.loads(_run_cli("proxy", "test", pid, "--json", allow_fail=True))

    @app.post("/api/profiles/{pid}/trust")
    def trust(pid: str):
        d = _prepare(pid)
        rep = json.loads(_run_cli("trust", pid, "--json"))
        # Remember the last grade so the Health page can show it without
        # re-launching every profile (a trust run opens a real browser).
        d["_trust"] = {"grade": rep.get("grade"), "score": rep.get("score"),
                       "at": time.time()}
        dash.save(d)
        return rep

    @app.post("/api/profiles/{pid}/tls")
    def tls(pid: str):
        _prepare(pid)
        return json.loads(_run_cli("tls", pid, "--json", allow_fail=True))

    @app.post("/api/profiles/{pid}/dns")
    def dns(pid: str):
        _prepare(pid)
        return json.loads(_run_cli("dns", pid, "--json", allow_fail=True))

    def _free_port() -> int:
        """A currently-unused local TCP port for a DevTools endpoint."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    @app.post("/api/profiles/{pid}/attach")
    def attach_profile(pid: str, body: Optional[dict] = None):
        """Open the profile with a Chrome DevTools endpoint your own automation
        can drive, and return the connection details.

        The browser stays open — attached and 'running' — until it's stopped
        (POST /stop), exactly like a launch. The attach itself runs as a
        subprocess that owns the window; we read the DevTools endpoint's own
        /json/version over HTTP to hand back the WebSocket URL. Pass
        ``{"headless": true}`` to attach without a visible window."""
        from .automation import CHROMIUM_ENGINES, cdp_info, snippets
        d = dash.get(pid)
        if not d:
            raise HTTPException(404, "profile not found")
        if is_running(pid):
            info = attached.get(pid)
            if info:
                return info                  # already attached — idempotent
            raise HTTPException(409, "stop the profile first — its session is in use")
        engine = d.get("engine") or engine_store.get_default_engine()
        if engine not in CHROMIUM_ENGINES:
            raise HTTPException(400, f"the '{engine}' engine has no DevTools to attach "
                                     f"to — use one of: {', '.join(CHROMIUM_ENGINES)}")
        engine_store.save(to_engine_profile(d))
        port = _free_port()
        cli = [sys.executable, "-m", "persona", "--data-dir", str(engine_store.root),
               "attach", pid, "--port", str(port)]
        if (body or {}).get("headless"):
            cli.append("--headless")
        running[pid] = subprocess.Popen(cli)
        try:
            info = cdp_info(port)            # waits for DevTools to answer
        except RuntimeError as e:
            _stop(pid)
            raise HTTPException(500, str(e))
        ws = info.get("webSocketDebuggerUrl", "")
        result = {"pid": pid, "port": port, "wsUrl": ws,
                  "headless": bool((body or {}).get("headless")),
                  "browser": info.get("Browser", ""), "snippets": snippets(port, ws)}
        attached[pid] = result
        return result

    @app.post("/api/profiles/{pid}/warmup")
    def warmup(pid: str, body: Optional[dict] = None):
        d = _prepare(pid)
        body = body or {}
        minutes = float(body.get("minutes", 5))
        cli = [sys.executable, "-m", "persona", "--data-dir", str(engine_store.root),
               "warmup", pid, "--minutes", str(minutes), "--headless"]
        if body.get("preset"):
            cli += ["--preset", str(body["preset"])]
        # Warm-up runs for minutes, so it goes in the background exactly like a
        # launch — the profile shows as running and "stop" ends it.
        running[pid] = subprocess.Popen(cli)
        return decorate(d)

    @app.post("/api/profiles/{pid}/align")
    def align(pid: str):
        """Auto-adjust: rewrite the profile to match what its browser presents,
        then write the aligned values back so the dashboard profile stays put."""
        d = _prepare(pid)
        res = json.loads(_run_cli("align", pid, "--json"))
        fp = res.get("fingerprint") or {}
        if fp.get("os"):
            d["os"] = OS_TO_DASH.get(fp["os"], d.get("os"))
        for src, dst in (("userAgent", "userAgent"), ("browserVersion", "browserVersion"),
                        ("cores", "cores"), ("memory", "memory"), ("screen", "screen"),
                        ("webglVendor", "webglVendor"), ("webglRenderer", "webglRenderer"),
                        ("cameras", "mediaVideo"), ("microphones", "mediaAudio"),
                        ("locale", "locale"), ("timezone", "timezone")):
            if fp.get(src) is not None:
                d[dst] = fp[src]
        after = res.get("after") or {}
        if after.get("grade"):
            d["_trust"] = {"grade": after["grade"], "score": after.get("score"),
                           "at": time.time()}
        res["profile"] = decorate(dash.save(d))
        return res

    @app.post("/api/profiles/batch")
    def batch_create(body: dict):
        """Save many dashboard profiles in one request (bulk create at scale).

        The dashboard generates coherent profiles client-side and posts them in
        chunks; this just persists them, assigning each a fresh unique id."""
        incoming = body.get("profiles") or []
        ids = []
        last_engine = None
        for p in incoming:
            p.pop("_new", None)
            p.pop("id", None)           # always mint a server-side id
            if not p.get("engine"):
                p["engine"] = engine_store.get_default_engine()
            last_engine = p.get("engine")
            ids.append(dash.save(p)["id"])
        if last_engine:
            engine_store.set_default_engine(last_engine)
        return {"created": len(ids), "ids": ids}

    @app.post("/api/profiles/bulk")
    def bulk_update(body: dict):
        """Apply one patch to many profiles — the dashboard's multi-select edit."""
        ids = body.get("ids") or []
        patch = body.get("patch") or {}
        updated = []
        for pid in ids:
            d = dash.get(pid)
            if not d:
                continue
            for key, value in patch.items():
                if key == "addTags":
                    d["tags"] = sorted({*d.get("tags", []), *value})
                elif key == "removeTags":
                    d["tags"] = [t for t in d.get("tags", []) if t not in value]
                elif key == "locale":
                    # Locale drives timezone, so move both or the profile stops
                    # being coherent.
                    d["locale"] = value
                    d["timezone"] = devices.LOCALES.get(value, (d.get("timezone"), None))[0]
                else:
                    d[key] = value
            _remember_engine(d)
            updated.append(decorate(dash.save(d)))
        return updated

    @app.post("/api/fingerprint/validate")
    def validate_fingerprint(profile: dict):
        return {"issues": dashboard_coherence(profile)}

    @app.post("/api/profiles/import")
    def import_profiles(body: dict):
        """Import profiles exported from GoLogin / AdsPower / Multilogin.

        Runs the engine's tolerant importer, converts each result to the
        dashboard shape and saves it, flagging any coherence issues for review."""
        from . import importers
        text = body.get("text") or ""
        try:
            raw = json.loads(text)
        except json.JSONDecodeError:
            raise HTTPException(400, "that file isn't valid JSON")
        exports = importers._unwrap(raw)
        if not exports:
            raise HTTPException(400, "no profiles found in that file")
        results = []
        for exp in exports:
            prof, issues = importers.profile_from_export(exp)
            d = to_dashboard_profile(prof)
            d["_new"] = True
            _remember_engine(d)
            dash.save(d)
            results.append({"name": prof.name, "issues": issues})
        return {"imported": len(results), "results": results}

    # ---- Proxy pool ------------------------------------------------------
    @app.get("/api/proxies")
    def list_proxies():
        return pool.list()

    @app.post("/api/proxies")
    def add_proxies(body: dict):
        from . import proxypool as pp
        incoming = body.get("proxies")
        parsed = incoming if incoming else pp.parse_many(body.get("text") or "")
        if not parsed:
            raise HTTPException(400, "no proxies could be parsed from that input")
        added = pool.add_many(parsed)
        return {"added": len(added), "total": len(pool.list()), "proxies": added}

    @app.delete("/api/proxies/{pid}")
    def delete_proxy(pid: str):
        if not pool.delete(pid):
            raise HTTPException(404, "proxy not found")
        return {"ok": True}

    @app.post("/api/proxies/{pid}/test")
    def test_proxy(pid: str):
        from . import proxypool as pp
        proxy = pool.get(pid)
        if not proxy:
            raise HTTPException(404, "proxy not found")
        res = pp.check(proxy)
        status = "ok" if res.get("ok") else ("skipped" if res.get("ok") is None else "failed")
        pool.update(pid, {"status": status, "lastCheck": res, "checkedAt": time.time()})
        return {**res, "status": status}

    @app.post("/api/proxies/assign")
    def assign_proxies(body: dict):
        """Assign pool proxies across profiles, round-robin, aligning each
        profile's locale/timezone to its proxy country."""
        proxies = [pool.get(i) for i in body.get("proxyIds", [])] if body.get("proxyIds") else pool.list()
        proxies = [p for p in proxies if p]
        if not proxies:
            raise HTTPException(400, "the proxy pool is empty")
        ids = body.get("profileIds")
        targets = [dash.get(i) for i in ids] if ids else dash.list()
        targets = [t for t in targets if t]
        assigned = 0
        for i, prof in enumerate(targets):
            pr = proxies[i % len(proxies)]
            prof["proxy"] = {"type": pr.get("type", "HTTP"), "host": pr["host"], "port": str(pr["port"]),
                             "user": pr.get("user") or "", "pass": pr.get("pass") or "",
                             "country": pr.get("country") or ""}
            cc = (pr.get("country") or "").upper()
            loc = devices.COUNTRY_TO_LOCALE.get(cc)
            if loc:
                prof["locale"] = loc
                prof["timezone"] = devices.LOCALES[loc][0]
            dash.save(prof)
            assigned += 1
        return {"assigned": assigned, "pool": len(proxies)}

    # ---- Scheduled warm-up ----------------------------------------------
    def _spawn_warmup(pid: str, minutes: float, preset: Optional[str]) -> None:
        """Launch a headless warm-up in the background (shared by the endpoint
        and the scheduler). The profile shows as running until it finishes."""
        cli = [sys.executable, "-m", "persona", "--data-dir", str(engine_store.root),
               "warmup", pid, "--minutes", str(minutes), "--headless"]
        if preset:
            cli += ["--preset", str(preset)]
        running[pid] = subprocess.Popen(cli)

    def _decorate_schedule(s: dict) -> dict:
        d = dash.get(s["profileId"])
        nxt = next_run_at(s)
        return {**s, "profileName": (d or {}).get("name", s["profileId"]),
                "nextRun": nxt, "due": nxt <= time.time()}

    @app.get("/api/schedules")
    def list_schedules():
        return [_decorate_schedule(s) for s in sched.list()]

    @app.post("/api/schedules")
    def add_schedule(body: dict):
        pid = body.get("profileId")
        if not pid or not dash.get(pid):
            raise HTTPException(404, "profile not found")
        entry = sched.add(profile_id=pid, every_hours=float(body.get("everyHours", 12)),
                          minutes=float(body.get("minutes", 5)),
                          preset=body.get("preset", "general"),
                          enabled=bool(body.get("enabled", True)), now=time.time())
        return _decorate_schedule(entry)

    @app.put("/api/schedules/{sid}")
    def update_schedule(sid: str, body: dict):
        patch = {k: body[k] for k in ("everyHours", "minutes", "preset", "enabled")
                 if k in body}
        out = sched.update(sid, patch)
        if not out:
            raise HTTPException(404, "schedule not found")
        return _decorate_schedule(out)

    @app.delete("/api/schedules/{sid}")
    def delete_schedule(sid: str):
        if not sched.delete(sid):
            raise HTTPException(404, "schedule not found")
        return {"ok": True}

    # ---- Fingerprint collisions -----------------------------------------
    @app.get("/api/profiles/collisions")
    def profiles_collisions():
        """Profiles that share a fingerprint — a cross-account linkage risk.

        Converts each stored dashboard profile to its engine fingerprint and
        groups the ones that look like the same device."""
        from .collision import find_collisions
        profs = [to_engine_profile(d) for d in dash.list()]
        return {"total": len(profs), "groups": find_collisions(profs)}

    # ---- Health overview -------------------------------------------------
    @app.get("/api/profiles/health")
    def profiles_health():
        """One row per profile with everything the Health page needs, computed
        cheaply. Coherence and proxy are read straight from the stored profile;
        the trust grade is the *cached* one from the last trust/align run (a live
        trust check opens a real browser, too heavy to do for the whole grid)."""
        by_profile: dict[str, dict] = {}
        for s in sched.list():
            # A profile keeps its most-frequent (smallest-interval) schedule row.
            cur = by_profile.get(s["profileId"])
            if cur is None or s.get("everyHours", 1e9) < cur.get("everyHours", 1e9):
                by_profile[s["profileId"]] = s

        profiles = dash.list()
        # Which profiles share a fingerprint with another? (a linkage risk)
        from .collision import find_collisions
        colliding: set[str] = set()
        for g in find_collisions([to_engine_profile(d) for d in profiles]):
            colliding.update(m["id"] for m in g["members"])

        rows = []
        summary = {"total": 0, "running": 0, "coherent": 0, "withProxy": 0,
                   "scheduled": 0, "graded": 0, "colliding": 0, "needsAttention": 0}
        for d in profiles:
            pid = d["id"]
            issues = dashboard_coherence(d)
            px = d.get("proxy") or {}
            has_proxy = bool(px.get("host"))
            trust = d.get("_trust")
            sc = by_profile.get(pid)
            run_now = is_running(pid)
            grade = (trust or {}).get("grade")
            collides = pid in colliding
            # "Needs attention" = something a user would want to fix: incoherent,
            # a known-poor trust grade, or a fingerprint shared with another profile.
            attention = bool(issues) or (grade in ("C", "D")) or collides

            rows.append({
                "id": pid,
                "name": d.get("name", pid),
                "engine": d.get("engine", "playwright"),
                "os": d.get("os", "Windows"),
                "status": "running" if run_now else "stopped",
                "lastActive": "now" if run_now else _rel_time(d.get("_last_active")),
                "coherent": not issues,
                "issues": issues,
                "collides": collides,
                "proxy": {"set": has_proxy, "country": px.get("country") or None,
                          "type": px.get("type") if has_proxy else None},
                "trust": trust,
                "schedule": ({"enabled": sc.get("enabled", True),
                              "everyHours": sc.get("everyHours"),
                              "preset": sc.get("preset")} if sc else None),
                "needsAttention": attention,
            })
            summary["total"] += 1
            summary["running"] += run_now
            summary["coherent"] += not issues
            summary["withProxy"] += has_proxy
            summary["scheduled"] += sc is not None
            summary["graded"] += trust is not None
            summary["colliding"] += collides
            summary["needsAttention"] += attention

        return {"summary": summary, "profiles": rows}

    def _scheduler_tick() -> None:
        """Fire any warm-up that's due and whose profile is free right now."""
        try:
            for s in due_schedules(sched.list(), time.time()):
                pid = s["profileId"]
                d = dash.get(pid)
                if not d or is_running(pid):
                    continue        # gone, or busy — try again next tick
                engine_store.save(to_engine_profile(d))
                _spawn_warmup(pid, s.get("minutes", 5), s.get("preset"))
                sched.mark_run(s["id"], time.time())
        except Exception:           # pragma: no cover - a bad tick must not kill the loop
            pass

    if start_scheduler:
        stop = threading.Event()

        def _loop():
            while not stop.wait(60):     # check once a minute
                _scheduler_tick()

        threading.Thread(target=_loop, daemon=True, name="persona-scheduler").start()

        @app.on_event("shutdown")
        def _stop_scheduler():
            stop.set()

    return app


def serve(host: str = "127.0.0.1", port: int = 8787, data_dir: Optional[str] = None):
    """Start the API server (blocking)."""
    _require_fastapi()
    import uvicorn
    app = create_app(data_dir)
    print(f"Persona API on http://{host}:{port}  (data dir: {ProfileStore(data_dir).root})")
    uvicorn.run(app, host=host, port=port, log_level="info")
