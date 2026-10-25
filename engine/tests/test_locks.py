"""Active-session lock: a profile can only be open in one live process."""

import json
import os
import subprocess
import sys

import pytest

from persona import drivers, locks
from persona.fingerprint import generate
from persona.models import Profile
from persona.store import ProfileStore


def _dead_pid() -> int:
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


def test_second_acquire_is_refused(tmp_path):
    lock = locks.acquire(tmp_path)
    with pytest.raises(locks.ProfileLocked) as e:
        locks.acquire(tmp_path)
    assert e.value.holder["pid"] == os.getpid()
    lock.release()
    locks.acquire(tmp_path).release()            # free again after release


def test_release_is_idempotent_and_removes_the_file(tmp_path):
    lock = locks.acquire(tmp_path)
    assert (tmp_path / locks.LOCK_FILE).exists()
    lock.release()
    lock.release()
    assert not (tmp_path / locks.LOCK_FILE).exists()


def test_stale_lock_from_a_dead_process_is_taken_over(tmp_path):
    (tmp_path / locks.LOCK_FILE).write_text(json.dumps({"pid": _dead_pid(), "started": 0}))
    assert locks.holder(tmp_path) is None
    lock = locks.acquire(tmp_path)
    assert locks.read(tmp_path)["pid"] == os.getpid()
    lock.release()


def test_release_leaves_a_lock_someone_else_took(tmp_path):
    lock = locks.acquire(tmp_path)
    locks.clear(tmp_path)                        # e.g. `persona unlock --force`
    other = {"pid": os.getpid(), "started": 0, "token": -1}
    (tmp_path / locks.LOCK_FILE).write_text(json.dumps(other))
    lock.release()
    assert locks.read(tmp_path) == other


def test_pid_alive():
    assert locks.pid_alive(os.getpid())
    assert not locks.pid_alive(_dead_pid())
    assert not locks.pid_alive(0)


# ---- every driver is wrapped -------------------------------------------------

class _Context:
    def __init__(self):
        self.handlers = []

    def on(self, event, fn):
        assert event == "close"
        self.handlers.append(fn)

    def close(self):
        for fn in self.handlers:
            fn(self)


@pytest.fixture()
def fake_engine():
    calls = {}

    @drivers.register("fake-locktest")
    def _fake(profile, store, headless=False, keep_open=True, extra_args=None):
        calls["held"] = locks.holder(store.user_data_path(profile.id)) is not None
        if calls.get("boom"):
            raise RuntimeError("launch failed")
        return (None, _Context(), None) if keep_open else None

    yield calls
    drivers._DRIVERS.pop("fake-locktest", None)


@pytest.fixture()
def profile_and_store(tmp_path):
    store = ProfileStore(tmp_path)
    prof = Profile(name="p", fingerprint=generate(os="windows", seed=1))
    store.save(prof)
    return prof, store


def test_driver_holds_the_lock_while_open(fake_engine, profile_and_store):
    prof, store = profile_and_store
    pw, ctx, _ = drivers.get("fake-locktest")(prof, store, keep_open=True)
    assert fake_engine["held"]
    with pytest.raises(locks.ProfileLocked):
        drivers.get("fake-locktest")(prof, store, keep_open=True)
    ctx.close()
    assert locks.holder(store.user_data_path(prof.id)) is None


def test_launch_and_wait_releases_on_return(fake_engine, profile_and_store):
    prof, store = profile_and_store
    drivers.get("fake-locktest")(prof, store, keep_open=False)
    assert fake_engine["held"]
    assert locks.holder(store.user_data_path(prof.id)) is None


def test_failed_launch_releases(fake_engine, profile_and_store):
    prof, store = profile_and_store
    fake_engine["boom"] = True
    with pytest.raises(RuntimeError, match="launch failed"):
        drivers.get("fake-locktest")(prof, store, keep_open=True)
    assert locks.holder(store.user_data_path(prof.id)) is None


def test_session_helper_is_locked_too(fake_engine, profile_and_store):
    prof, store = profile_and_store
    with drivers.session(prof, store, engine="fake-locktest"):
        with pytest.raises(locks.ProfileLocked):
            drivers.get("fake-locktest")(prof, store, keep_open=False)
    assert locks.holder(store.user_data_path(prof.id)) is None


# ---- CLI and dashboard --------------------------------------------------------

def test_cli_unlock_clears_only_stale_locks_without_force(profile_and_store, capsys):
    from persona.cli import main
    prof, store = profile_and_store
    lock = locks.acquire(store.user_data_path(prof.id))
    assert main(["--data-dir", str(store.root), "unlock", prof.id]) == 1
    assert locks.holder(store.user_data_path(prof.id))
    assert main(["--data-dir", str(store.root), "unlock", prof.id, "--force"]) == 0
    assert locks.read(store.user_data_path(prof.id)) is None
    lock.release()


def test_dashboard_sees_a_profile_opened_elsewhere(tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from persona.server import TOKEN_HEADER, create_app

    app = create_app(str(tmp_path), start_scheduler=False)
    client = TestClient(app, base_url="http://localhost",
                        headers={TOKEN_HEADER: app.state.api_token})
    pid = client.post("/api/profiles", json={"name": "x", "os": "Windows"}).json()["id"]
    lock = locks.acquire(ProfileStore(tmp_path).user_data_path(pid))
    try:
        row = next(p for p in client.get("/api/profiles").json() if p["id"] == pid)
        assert row["status"] == "running"
        assert row["openElsewhere"] == os.getpid()
        assert client.post(f"/api/profiles/{pid}/stop").status_code == 409
        assert client.get(f"/api/profiles/{pid}/cookies").status_code == 409
    finally:
        lock.release()
    row = next(p for p in client.get("/api/profiles").json() if p["id"] == pid)
    assert row["status"] == "stopped"
