"""Launch lifecycle: geo prefetch, the ready signal, start watchdog, orphan cleanup."""

import os
import subprocess
import sys
import threading
import time

import pytest

from persona import drivers, geo, locks, procs
from persona.fingerprint import generate
from persona.models import Profile, Proxy
from persona.store import ProfileStore

CHICAGO = {"ip": "203.0.113.7", "timezone": "America/Chicago", "lat": 41.88, "lon": -87.63,
           "country": "US", "city": "Chicago"}


def setup_function(_):
    geo.clear_cache()


def _proxied(seed=1):
    return Profile(name="g", fingerprint=generate(seed=seed),
                   proxy=Proxy(server="http://h:1", country="US"))


# ---- geo prefetch ----------------------------------------------------------------

def test_prefetch_overlaps_and_launch_geo_reuses_it():
    started, release, calls = threading.Event(), threading.Event(), []

    def slow(px):
        calls.append(1)
        started.set()
        release.wait(5)
        return CHICAGO

    p = _proxied()
    geo.prefetch(p, lookup=slow)
    geo.prefetch(p, lookup=slow)                 # a second prefetch doesn't double up
    assert started.wait(5)
    release.set()
    g = geo.launch_geo(p, lookup=lambda px: 1 / 0)   # must not look up again
    assert g["timezone"] == "America/Chicago" and calls == [1]
    assert geo.launch_geo(p, lookup=lambda px: 1 / 0)["source"] == "exit-ip"   # now cached


def test_prefetch_skips_profiles_without_a_proxy_or_with_a_fresh_cache():
    geo.prefetch(Profile(name="x", fingerprint=generate(seed=1)), lookup=lambda px: 1 / 0)
    p = _proxied()
    geo.launch_geo(p, lookup=lambda px: CHICAGO)
    geo.prefetch(p, lookup=lambda px: 1 / 0)
    assert geo._pending == {}


# ---- ready signal ----------------------------------------------------------------------

def test_mark_ready_only_touches_our_own_lock(tmp_path):
    lock = locks.acquire(tmp_path)
    assert not locks.read(tmp_path).get("ready")
    locks.mark_ready(tmp_path)
    info = locks.read(tmp_path)
    assert info["ready"] and info["pid"] == os.getpid()
    lock.release()

    (tmp_path / locks.LOCK_FILE).write_text('{"pid": 1, "started": 0}')
    locks.mark_ready(tmp_path)
    assert "ready" not in locks.read(tmp_path)


@pytest.fixture()
def fake_engine():
    seen = {}

    @drivers.register("fake-lifecycle")
    def _fake(profile, store, headless=False, keep_open=True, extra_args=None):
        ud = store.user_data_path(profile.id)
        seen["before"] = bool(locks.read(ud).get("ready"))
        drivers._open_startup_urls(None, None, profile)    # what every driver calls once up
        seen["after"] = bool(locks.read(ud).get("ready"))
        return None

    yield seen
    drivers._DRIVERS.pop("fake-lifecycle", None)


def test_drivers_mark_the_launch_ready_once_the_window_exists(fake_engine, tmp_path):
    store = ProfileStore(tmp_path)
    prof = Profile(name="p", fingerprint=generate(seed=1))
    store.save(prof)
    drivers.get("fake-lifecycle")(prof, store, keep_open=False)
    assert fake_engine == {"before": False, "after": True}
    assert prof.id not in drivers._ready_dirs              # forgotten after release


# ---- orphan browsers ---------------------------------------------------------------------

def test_maybe_running_markers(tmp_path):
    assert not procs.maybe_running(tmp_path)
    (tmp_path / "lockfile").write_text("")
    assert procs.maybe_running(tmp_path)


def test_finds_and_ends_a_process_by_its_user_data_dir(tmp_path):
    ud = tmp_path / "user-data" / "abc123"
    ud.mkdir(parents=True)
    # A stand-in "browser": a process whose command line names the profile dir.
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)",
                             f"--user-data-dir={ud}"])
    try:
        deadline = time.time() + 20
        while proc.pid not in procs.browser_pids(ud) and time.time() < deadline:
            time.sleep(0.5)
        assert proc.pid in procs.browser_pids(ud)
        assert procs.browser_pids(tmp_path / "user-data" / "other") == []
        (ud / "lockfile").write_text("")
        assert procs.end_browsers(ud) >= 1
        proc.wait(timeout=15)
    finally:
        if proc.poll() is None:
            proc.kill()


# ---- dashboard watchdog -------------------------------------------------------------------

def test_launch_watchdog_stops_a_launch_that_never_comes_up(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from persona import server

    app = server.create_app(str(tmp_path), start_scheduler=False)
    c = TestClient(app, base_url="http://localhost", headers={server.TOKEN_HEADER: app.state.api_token})
    pid = c.post("/api/profiles", json={"name": "x", "os": "Windows"}).json()["id"]

    # A "launcher" that never marks itself ready.
    real_popen = subprocess.Popen
    monkeypatch.setattr(server.subprocess, "Popen",
                        lambda *a, **k: real_popen([sys.executable, "-c", "import time; time.sleep(60)"],
                                                   stdout=k.get("stdout"), stderr=k.get("stderr")))
    row = c.post(f"/api/profiles/{pid}/launch").json()
    assert row["status"] == "running" and row["ready"] is False

    # The real limits are 60/300 s: jump the watchdog's clock past them.
    t0 = time.time()
    monkeypatch.setattr(server.time, "time", lambda: t0 + 10_000)
    for _ in range(100):
        row = next(p for p in c.get("/api/profiles").json() if p["id"] == pid)
        if row["status"] == "stopped":
            break
        time.sleep(0.2)
    assert row["status"] == "stopped"
    assert "made no progress for 5 minutes" in row["launchError"]
    kinds = [e["kind"] for e in c.get(f"/api/profiles/{pid}/activity").json()["activity"]]
    assert "start-timeout" in kinds


def test_watchdog_spares_a_launch_that_is_still_making_progress(tmp_path, monkeypatch):
    # A first-run engine download takes minutes but keeps writing progress to
    # the launch log; it must not be stopped as "never came up".
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from persona import server

    app = server.create_app(str(tmp_path), start_scheduler=False)
    c = TestClient(app, base_url="http://localhost", headers={server.TOKEN_HEADER: app.state.api_token})
    pid = c.post("/api/profiles", json={"name": "x", "os": "Windows"}).json()["id"]
    chatty = ("import sys, time\n"
              "for i in range(200):\n"
              "    print('Download progress', i, flush=True); time.sleep(0.1)")
    real_popen = subprocess.Popen
    monkeypatch.setattr(server.subprocess, "Popen",
                        lambda *a, **k: real_popen([sys.executable, "-c", chatty],
                                                   stdout=k.get("stdout"), stderr=k.get("stderr")))
    c.post(f"/api/profiles/{pid}/launch")
    t0 = time.time()
    monkeypatch.setattr(server.time, "time", lambda: t0 + 10_000)   # far past the limit
    time.sleep(3)
    row = next(p for p in c.get("/api/profiles").json() if p["id"] == pid)
    assert row["status"] == "running"
    c.post(f"/api/profiles/{pid}/stop")
