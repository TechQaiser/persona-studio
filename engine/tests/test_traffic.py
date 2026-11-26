"""Traffic savers: blocking images and click-to-play video per profile."""

import json

from persona import generate
from persona import traffic
from persona.bulk import apply_patch
from persona.cli import main
from persona.drivers import _extension_args
from persona.models import Profile
from persona.server import to_dashboard_profile, to_engine_profile
from persona.store import ProfileStore


def mk(**kw):
    return Profile(name="x", fingerprint=generate(seed=1), **kw)


def test_off_by_default_and_round_trips():
    p = mk()
    assert (p.block_images, p.block_video) == (False, False)
    back = Profile.from_dict(json.loads(json.dumps(mk(block_images=True, block_video=True).to_dict())))
    assert (back.block_images, back.block_video) == (True, True)


def test_old_profiles_without_the_fields_still_load():
    d = mk().to_dict()
    del d["block_images"], d["block_video"]
    assert Profile.from_dict(d).block_images is False


def test_images_become_a_blink_setting():
    args = traffic.chromium_args(mk(block_images=True), ["--no-first-run"])
    assert args == ["--no-first-run", "--blink-settings=imagesEnabled=false"]
    assert traffic.chromium_args(mk(), ["--no-first-run"]) == ["--no-first-run"]


def test_a_profiles_own_blink_settings_are_merged_not_lost():
    # Chromium keeps only the last --blink-settings flag.
    args = traffic.chromium_args(mk(block_images=True),
                                 ["--blink-settings=hideScrollbars=true,imagesEnabled=true", "--x"])
    blink = [a for a in args if a.startswith("--blink-settings")]
    assert blink == ["--blink-settings=hideScrollbars=true,imagesEnabled=false"]
    assert "--x" in args


def test_video_saver_loads_the_bundled_extension():
    assert traffic.chromium_extensions(mk()) == []
    dirs = traffic.chromium_extensions(mk(block_video=True))
    assert dirs == [str(traffic.EXTENSION_DIR)]
    manifest = json.loads((traffic.EXTENSION_DIR / "manifest.json").read_text(encoding="utf-8"))
    script = manifest["content_scripts"][0]
    # Every frame (cross-origin iframes carry most embedded video), from the start.
    assert script["all_frames"] and script["run_at"] == "document_start"
    for js in script["js"]:
        assert (traffic.EXTENSION_DIR / js).is_file()
    args = _extension_args(mk(block_video=True), dirs)
    assert str(traffic.EXTENSION_DIR.resolve()) in args[1]


def test_autoplay_script_only_listens_and_pauses():
    js = traffic.autoplay_script()
    assert 'addEventListener("play"' in js and "userActivation" in js
    # Nothing on the page's prototypes is replaced (that would be detectable).
    assert "prototype.play =" not in js and "defineProperty" not in js


def test_camoufox_gets_firefox_settings():
    assert traffic.firefox_options(mk()) == {}
    opts = traffic.firefox_options(mk(block_images=True, block_video=True))
    assert opts["block_images"] is True
    assert opts["firefox_user_prefs"] == {"media.autoplay.default": 5}


def test_dashboard_round_trip():
    d = {"id": "a1", "name": "T", "os": "Windows", "blockImages": True, "blockVideo": False}
    prof = to_engine_profile(d)
    assert (prof.block_images, prof.block_video) == (True, False)
    out = to_dashboard_profile(prof)
    assert (out["blockImages"], out["blockVideo"]) == (True, False)


def test_bulk_apply_turns_savers_on_and_off():
    p = mk()
    assert apply_patch(p, {"block_images": True}) == ["block_images"]
    assert p.block_images and not p.block_video
    assert apply_patch(p, {"block_images": True}) == []        # already on
    assert apply_patch(p, {"block_images": False, "block_video": True}) == ["block_images", "block_video"]


def test_cli_traffic_and_apply(tmp_path, capsys):
    store = ProfileStore(tmp_path)
    store.save(mk())
    assert main(["--data-dir", str(tmp_path), "traffic", "x", "--images", "off"]) == 0
    assert store.resolve("x").block_images and not store.resolve("x").block_video
    assert main(["--data-dir", str(tmp_path), "apply", "--all", "--video", "off",
                 "--images", "on", "-y"]) == 0
    prof = store.resolve("x")
    assert (prof.block_images, prof.block_video) == (False, True)
    assert "blocked" in capsys.readouterr().out
