"""Backup/restore round-trips a profile *and* its browser session (user-data)."""

from persona.fingerprint import generate
from persona.models import Profile
from persona.store import ProfileStore


def _seed_profile(store, name="Acct"):
    prof = store.save(Profile(name=name, fingerprint=generate(os="windows", seed=7)))
    # Simulate a browser session on disk (cookies, localStorage, …).
    ud = store.user_data_path(prof.id)
    (ud / "Default").mkdir(parents=True, exist_ok=True)
    (ud / "Default" / "Cookies").write_bytes(b"session-bytes")
    return prof


def test_backup_then_restore_brings_back_profile_and_session(tmp_path):
    src = ProfileStore(tmp_path / "a")
    prof = _seed_profile(src)
    archive = tmp_path / "acct.zip"
    assert src.backup(prof.id, archive) == archive
    assert archive.exists()

    # Restore into a completely separate data dir.
    dst = ProfileStore(tmp_path / "b")
    restored = dst.restore(archive)
    assert restored.id == prof.id and restored.name == "Acct"
    got = dst.get(prof.id)
    assert got is not None and got.fingerprint.seed == 7
    assert (dst.user_data_path(prof.id) / "Default" / "Cookies").read_bytes() == b"session-bytes"


def test_backup_missing_profile_returns_none(tmp_path):
    store = ProfileStore(tmp_path)
    assert store.backup("nope", tmp_path / "x.zip") is None


def test_restore_with_new_id_makes_a_copy(tmp_path):
    src = ProfileStore(tmp_path / "a")
    prof = _seed_profile(src)
    archive = tmp_path / "acct.zip"
    src.backup(prof.id, archive)

    copy = src.restore(archive, new_id=True)
    assert copy.id != prof.id                       # a fresh identity slot
    # Both the original and the copy now exist, each with its own session.
    assert {p.id for p in src.list()} >= {prof.id, copy.id}
    assert (src.user_data_path(copy.id) / "Default" / "Cookies").read_bytes() == b"session-bytes"
