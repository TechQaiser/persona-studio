"""Session hygiene (cache pruning) and profile history snapshots."""

import os
import time
import zipfile

import pytest

from persona import history, locks
from persona.fingerprint import generate
from persona.models import Profile
from persona.store import ProfileStore


def _session(ud):
    """A small fake Chromium user-data dir: real state plus regenerable caches."""
    files = {
        "Default/Cookies": b"cookies-v1",
        "Default/Local Storage/leveldb/000003.log": b"ls",
        "Default/Preferences": b"{}",
        "Default/Cache/Cache_Data/data_0": b"x" * 5000,
        "Default/Code Cache/js/index": b"y" * 3000,
        "GrShaderCache/data_1": b"z" * 2000,
        "SingletonLock": b"",
        locks.LOCK_FILE: b"{}",
    }
    for rel, data in files.items():
        p = ud / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)


def _rels(ud):
    return {rel.as_posix() for _, rel in history.session_files(ud)}


def test_session_files_skip_caches_and_runtime_locks(tmp_path):
    _session(tmp_path)
    assert _rels(tmp_path) == {"Default/Cookies", "Default/Local Storage/leveldb/000003.log",
                               "Default/Preferences"}


def test_prune_frees_caches_and_keeps_state(tmp_path):
    _session(tmp_path)
    assert history.prune(tmp_path) == 10000
    assert not (tmp_path / "Default/Cache").exists()
    assert not (tmp_path / "GrShaderCache").exists()
    assert (tmp_path / "Default/Cookies").read_bytes() == b"cookies-v1"


def test_snapshot_keeps_only_the_newest(tmp_path):
    ud, hist = tmp_path / "ud", tmp_path / "hist"
    _session(ud)
    for i in range(4):
        (ud / "Default/Cookies").write_bytes(f"v{i}".encode())
        assert history.snapshot(ud, hist, "p1", keep=2, force=True)
    snaps = history.list_snapshots(hist, "p1")
    assert len(snaps) == 2
    with zipfile.ZipFile(hist / "p1" / f"{snaps[0]['id']}.zip") as z:
        assert z.read("Default/Cookies") == b"v3"
        assert not any(n.startswith("Default/Cache") for n in z.namelist())


def test_unchanged_session_isnt_snapshotted_twice(tmp_path):
    ud, hist = tmp_path / "ud", tmp_path / "hist"
    _session(ud)
    assert history.snapshot(ud, hist, "p1")
    assert history.snapshot(ud, hist, "p1") is None
    later = time.time() + 5
    os.utime(ud / "Default/Cookies", (later, later))
    assert history.snapshot(ud, hist, "p1")


def test_empty_session_or_history_off_saves_nothing(tmp_path):
    assert history.snapshot(tmp_path / "missing", tmp_path / "h", "p1") is None
    _session(tmp_path / "ud")
    assert history.snapshot(tmp_path / "ud", tmp_path / "h", "p1", keep=0) is None


def test_restore_rolls_back_and_can_be_undone(tmp_path):
    ud, hist = tmp_path / "ud", tmp_path / "hist"
    _session(ud)
    first = history.snapshot(ud, hist, "p1", force=True)
    (ud / "Default/Cookies").write_bytes(b"logged-out")
    (ud / "Default/new-file").write_bytes(b"junk")

    history.restore(ud, hist, "p1", first["id"])
    assert (ud / "Default/Cookies").read_bytes() == b"cookies-v1"
    assert not (ud / "Default/new-file").exists()

    before = [s for s in history.list_snapshots(hist, "p1") if s["reason"] == "before-restore"]
    assert len(before) == 1
    history.restore(ud, hist, "p1", before[0]["id"])
    assert (ud / "Default/Cookies").read_bytes() == b"logged-out"


def test_restore_rejects_unknown_or_path_like_ids(tmp_path):
    with pytest.raises(FileNotFoundError):
        history.restore(tmp_path / "ud", tmp_path / "h", "p1", "nope")
    with pytest.raises(FileNotFoundError):
        history.restore(tmp_path / "ud", tmp_path / "h", "p1", "../p2/x")


# ---- integration with the store / launcher ---------------------------------------

@pytest.fixture()
def store_and_profile(tmp_path):
    store = ProfileStore(tmp_path)
    prof = Profile(name="p", fingerprint=generate(os="windows", seed=1))
    store.save(prof)
    return store, prof


def test_backup_leaves_caches_out(store_and_profile, tmp_path):
    store, prof = store_and_profile
    _session(store.user_data_path(prof.id))
    out = store.backup(prof.id, tmp_path / "b.zip")
    with zipfile.ZipFile(out) as z:
        names = set(z.namelist())
    assert "user-data/Default/Cookies" in names
    assert not any("Cache" in n or locks.LOCK_FILE in n for n in names)


def test_end_session_prunes_and_snapshots(store_and_profile):
    from persona.launcher import end_session
    store, prof = store_and_profile
    ud = store.user_data_path(prof.id)
    _session(ud)
    end_session(prof, store)
    assert not (ud / "Default/Cache").exists()
    assert [s["reason"] for s in history.list_snapshots(store.history_dir, prof.id)] == ["session"]


def test_history_keep_setting(store_and_profile):
    store, _ = store_and_profile
    assert store.get_history_keep() == history.DEFAULT_KEEP
    store.save_config({"history_keep": 0})
    assert store.get_history_keep() == 0


def test_deleting_a_profile_deletes_its_history(store_and_profile):
    store, prof = store_and_profile
    _session(store.user_data_path(prof.id))
    history.snapshot(store.user_data_path(prof.id), store.history_dir, prof.id)
    store.delete(prof.id)
    assert history.list_snapshots(store.history_dir, prof.id) == []


def test_api_history_roundtrip(tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from persona.server import TOKEN_HEADER, create_app

    app = create_app(str(tmp_path), start_scheduler=False)
    c = TestClient(app, base_url="http://localhost", headers={TOKEN_HEADER: app.state.api_token})
    pid = c.post("/api/profiles", json={"name": "x", "os": "Windows"}).json()["id"]
    assert c.post(f"/api/profiles/{pid}/history").status_code == 400   # no session yet

    ud = ProfileStore(tmp_path).user_data_path(pid)
    _session(ud)
    snap = c.post(f"/api/profiles/{pid}/history").json()
    (ud / "Default/Cookies").write_bytes(b"changed")
    r = c.post(f"/api/profiles/{pid}/history/{snap['id']}/restore")
    assert r.status_code == 200
    assert (ud / "Default/Cookies").read_bytes() == b"cookies-v1"
    assert c.post(f"/api/profiles/{pid}/history/missing/restore").status_code == 404

    lock = locks.acquire(ud)
    try:
        assert c.post(f"/api/profiles/{pid}/history/{snap['id']}/restore").status_code == 409
    finally:
        lock.release()

    assert c.put("/api/config", json={"history_keep": 3}).json()["history_keep"] == 3
    assert c.put("/api/config", json={"history_keep": 99}).status_code == 400
