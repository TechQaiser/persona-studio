"""Per-profile storage toggles: what a profile keeps between sessions."""

import pytest

from persona import history
from persona.fingerprint import generate
from persona.models import Profile
from persona.server import to_dashboard_profile, to_engine_profile
from persona.store import ProfileStore


def _touch(root, *rels):
    for rel in rels:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")


def test_default_keeps_everything(tmp_path):
    _touch(tmp_path, "Default/History", "Default/Login Data", "Default/Cookies")
    assert history.normalize_storage(None) == {k: True for k in history.STORAGE_KINDS}
    assert history.apply_storage_policy(tmp_path, {}) == []
    assert (tmp_path / "Default/History").exists()


def test_chromium_kinds_are_cleared_and_cookies_kept(tmp_path):
    _touch(tmp_path, "Default/History", "Default/Visited Links", "Default/Login Data",
           "Default/Local Storage/leveldb/1.log", "Default/Bookmarks", "Default/Cookies")
    removed = history.apply_storage_policy(tmp_path, {"history": False, "passwords": False})
    assert set(removed) == {"Default/History", "Default/Visited Links", "Default/Login Data"}
    assert (tmp_path / "Default/Cookies").exists()
    assert (tmp_path / "Default/Bookmarks").exists()
    assert (tmp_path / "Default/Local Storage").exists()


def test_firefox_shared_files_go_only_when_both_kinds_are_off(tmp_path):
    _touch(tmp_path, "places.sqlite", "storage/default/site/ls/data.sqlite", "logins.json")
    history.apply_storage_policy(tmp_path, {"history": False, "passwords": False})
    assert (tmp_path / "places.sqlite").exists()          # still holds bookmarks
    assert not (tmp_path / "logins.json").exists()
    history.apply_storage_policy(tmp_path, {"history": False, "bookmarks": False,
                                            "local": False, "indexeddb": False})
    assert not (tmp_path / "places.sqlite").exists()
    assert not (tmp_path / "storage/default").exists()


def test_profile_roundtrips_storage():
    prof = Profile(name="p", fingerprint=generate(os="windows", seed=1),
                   storage={"history": False})
    assert Profile.from_dict(prof.to_dict()).storage == {"history": False}
    # profiles saved before the field existed load as "keep everything"
    d = prof.to_dict()
    d.pop("storage")
    assert Profile.from_dict(d).storage == {}


def test_dashboard_conversion_stores_only_what_is_off():
    d = {"id": "a", "name": "x", "os": "Windows",
         "storage": {"history": False, "local": True, "bogus": False}}
    assert to_engine_profile(d).storage == {"history": False}
    back = to_dashboard_profile(to_engine_profile(d))["storage"]
    assert back["history"] is False and back["local"] is True and "bogus" not in back


def test_end_session_applies_the_policy(tmp_path):
    from persona.launcher import end_session
    store = ProfileStore(tmp_path)
    prof = Profile(name="p", fingerprint=generate(os="windows", seed=1),
                   storage={"passwords": False})
    store.save(prof)
    ud = store.user_data_path(prof.id)
    _touch(ud, "Default/Login Data", "Default/Cookies")
    end_session(prof, store)
    assert not (ud / "Default/Login Data").exists()
    snap = history.list_snapshots(store.history_dir, prof.id)[0]
    import zipfile
    with zipfile.ZipFile(store.history_dir / prof.id / f"{snap['id']}.zip") as z:
        assert z.namelist() == ["Default/Cookies"]


def test_cli_storage(tmp_path, capsys):
    from persona.cli import main
    store = ProfileStore(tmp_path)
    prof = Profile(name="p", fingerprint=generate(os="windows", seed=1))
    store.save(prof)
    assert main(["--data-dir", str(tmp_path), "storage", prof.id, "--off", "history", "passwords"]) == 0
    assert store.get(prof.id).storage == {"history": False, "passwords": False}
    assert main(["--data-dir", str(tmp_path), "storage", prof.id, "--on", "history"]) == 0
    assert store.get(prof.id).storage == {"passwords": False}
    assert main(["--data-dir", str(tmp_path), "storage", prof.id, "--off", "cookies"]) == 1
