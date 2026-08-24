"""Extension loading: the flags a profile's extensions turn into."""

from persona import generate
from persona.drivers import _extension_args
from persona.models import Profile
from persona.store import ProfileStore


def mk(paths):
    return Profile(name="x", fingerprint=generate(seed=1), extensions=paths)


def test_no_extensions_means_no_flags():
    assert _extension_args(mk([])) == []


def test_both_flags_are_emitted(tmp_path):
    ext = tmp_path / "ublock"
    ext.mkdir()
    args = _extension_args(mk([str(ext)]))
    # --load-extension alone would leave every other extension enabled, which
    # would leak identity between profiles.
    assert len(args) == 2
    assert args[0].startswith("--disable-extensions-except=")
    assert args[1].startswith("--load-extension=")
    assert str(ext) in args[1]


def test_multiple_paths_are_comma_joined(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    args = _extension_args(mk([str(a), str(b)]))
    assert args[1].count(",") == 1


def test_missing_folders_are_dropped(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    args = _extension_args(mk([str(real), str(tmp_path / "gone")]))
    assert "gone" not in args[1]
    assert "real" in args[1]


def test_only_missing_folders_means_no_flags(tmp_path):
    assert _extension_args(mk([str(tmp_path / "nope")])) == []


def test_extensions_survive_a_save_round_trip():
    p = mk(["/some/ext"])
    assert Profile.from_dict(p.to_dict()).extensions == ["/some/ext"]


def test_profiles_saved_before_extensions_existed_still_load():
    d = mk([]).to_dict()
    del d["extensions"]
    assert Profile.from_dict(d).extensions == []


# ---- the global default set --------------------------------------------
# Chromium has no browser-wide extension store to hook, so "install once for
# every profile" has to mean "copy onto each profile as it is created".


def test_default_extensions_round_trip(tmp_path):
    store = ProfileStore(tmp_path)
    assert store.get_default_extensions() == []
    store.set_default_extensions(["/opt/ext/ublock"])
    assert ProfileStore(tmp_path).get_default_extensions() == ["/opt/ext/ublock"]


def test_new_profiles_inherit_the_default_set(tmp_path):
    from persona.cli import build_parser
    store = ProfileStore(tmp_path)
    ext = tmp_path / "shared-ext"
    ext.mkdir()
    store.set_default_extensions([str(ext)])

    args = build_parser().parse_args(["create", "inherits"])
    assert args.func(args, store) == 0
    assert store.find_by_name("inherits").extensions == [str(ext)]


def test_bulk_apply_pushes_extensions_onto_existing_profiles(tmp_path):
    # Existing profiles predate the default set, so they need an explicit push.
    from persona.bulk import apply_patch
    prof = Profile(name="old", fingerprint=generate(seed=2))
    assert prof.extensions == []
    assert "extensions" in apply_patch(prof, {"extensions": ["/opt/ext/ublock"]})
    assert prof.extensions == ["/opt/ext/ublock"]
