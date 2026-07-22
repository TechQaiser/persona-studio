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
import subprocess
import sys
import tempfile
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


def _engine_webgl(os_key: str, dash_renderer: str) -> tuple[str, str]:
    """Map a dashboard GPU label to a real engine WebGL vendor/renderer pair."""
    pool = devices.WEBGL.get(os_key) or devices.WEBGL["windows"]
    if dash_renderer:
        # match on a distinctive token like "RTX 3060", "M1", "Adreno"
        for token in dash_renderer.replace("(", " ").replace(")", " ").split():
            if len(token) < 3:
                continue
            for vendor, renderer in pool:
                if token in renderer:
                    return vendor, renderer
    return pool[0]


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
    vendor, renderer = _engine_webgl(os_key, d.get("webglRenderer", ""))

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


def create_app(data_dir: Optional[str] = None):
    _require_fastapi()
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware

    engine_store = ProfileStore(data_dir)
    dash = DashboardStore(engine_store.root)
    running: dict[str, subprocess.Popen] = {}

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
        _prepare(pid)
        return json.loads(_run_cli("trust", pid, "--json"))

    @app.post("/api/profiles/{pid}/warmup")
    def warmup(pid: str, body: Optional[dict] = None):
        d = _prepare(pid)
        minutes = float((body or {}).get("minutes", 5))
        # Warm-up runs for minutes, so it goes in the background exactly like a
        # launch — the profile shows as running and "stop" ends it.
        running[pid] = subprocess.Popen(
            [sys.executable, "-m", "persona", "--data-dir", str(engine_store.root),
             "warmup", pid, "--minutes", str(minutes), "--headless"],
        )
        return decorate(d)

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

    return app


def serve(host: str = "127.0.0.1", port: int = 8787, data_dir: Optional[str] = None):
    """Start the API server (blocking)."""
    _require_fastapi()
    import uvicorn
    app = create_app(data_dir)
    print(f"Persona API on http://{host}:{port}  (data dir: {ProfileStore(data_dir).root})")
    uvicorn.run(app, host=host, port=port, log_level="info")
