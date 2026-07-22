"""Tests for profile persistence."""

from persona import generate, Profile, Proxy
from persona.store import ProfileStore


def make_store(tmp_path):
    return ProfileStore(root=tmp_path)


def test_save_and_get(tmp_path):
    store = make_store(tmp_path)
    prof = Profile(name="acct-01", fingerprint=generate(seed=1))
    store.save(prof)
    loaded = store.get(prof.id)
    assert loaded is not None
    assert loaded.name == "acct-01"
    assert loaded.fingerprint.to_dict() == prof.fingerprint.to_dict()


def test_resolve_by_name_and_id(tmp_path):
    store = make_store(tmp_path)
    prof = Profile(name="named", fingerprint=generate(seed=2))
    store.save(prof)
    assert store.resolve("named").id == prof.id
    assert store.resolve(prof.id).name == "named"
    assert store.resolve("nope") is None


def test_list_is_sorted_by_creation(tmp_path):
    store = make_store(tmp_path)
    a = Profile(name="a", fingerprint=generate(seed=1), created_at=100)
    b = Profile(name="b", fingerprint=generate(seed=2), created_at=200)
    store.save(b)
    store.save(a)
    names = [p.name for p in store.list()]
    assert names == ["a", "b"]


def test_delete(tmp_path):
    store = make_store(tmp_path)
    prof = Profile(name="temp", fingerprint=generate(seed=3))
    store.save(prof)
    assert store.delete(prof.id) is True
    assert store.get(prof.id) is None
    assert store.delete(prof.id) is False


def test_export_import_roundtrip(tmp_path):
    store = make_store(tmp_path)
    prof = Profile(
        name="portable",
        fingerprint=generate(seed=4),
        proxy=Proxy(server="socks5://h:1080", country="US"),
        tags=["client-x"],
        notes="hello",
    )
    store.save(prof)
    out = tmp_path / "exp.json"
    store.export(prof.id, out)

    store2 = make_store(tmp_path / "other")
    imported = store2.import_file(out)
    assert imported.name == "portable"
    assert imported.proxy.server == "socks5://h:1080"
    assert imported.tags == ["client-x"]


def test_user_data_dir_created(tmp_path):
    store = make_store(tmp_path)
    prof = Profile(name="ud", fingerprint=generate(seed=5))
    store.save(prof)
    path = store.user_data_path(prof.id)
    assert path.exists() and path.is_dir()
