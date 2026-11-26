"""
Traffic savers: per-profile switches that cut what a session downloads.

Residential and mobile proxies bill by the gigabyte, and on most sites images
and autoplaying video are the bulk of it. A profile can turn off either one:

* ``block_images``: no image is requested at all (``<img>``, CSS backgrounds,
  ``<picture>``). Chromium engines get Blink's own ``imagesEnabled=false``
  setting; Camoufox gets Firefox's image permission.
* ``block_video``: video and audio don't start until the user clicks or presses
  a key on the page. Chromium has no switch for this (its autoplay policy
  always lets muted video play, and muted video is most of the traffic), so a
  small script pauses media that starts without user activation, in every
  frame. It only listens and pauses; no built-in function is replaced. Playwright and
  Patchright run it as an init script; CloakBrowser, where Persona injects no
  JavaScript, loads it as a bundled extension. Camoufox uses Firefox's own
  "block all autoplay" setting.

A site can notice that images or video didn't load, as it would for a user
with a data-saver or an ad blocker, so these are off unless a profile turns
them on.
"""

from __future__ import annotations

from pathlib import Path

ASSETS = Path(__file__).parent / "assets"
EXTENSION_DIR = ASSETS / "traffic-saver"
AUTOPLAY_SCRIPT = EXTENSION_DIR / "autoplay.js"

# Labels shared by the CLI and the API, keyed by the profile attribute.
KINDS = {
    "images": ("block_images", "Images"),
    "video": ("block_video", "Video and audio autoplay"),
}

# Firefox's media.autoplay.default: 0 allow, 1 block audible, 5 block all.
FIREFOX_BLOCK_ALL_AUTOPLAY = 5


def autoplay_script() -> str:
    return AUTOPLAY_SCRIPT.read_text(encoding="utf-8")


def merge_blink_settings(args: list[str], settings: dict[str, str]) -> list[str]:
    """Return ``args`` with ``settings`` added to its ``--blink-settings``.

    Chromium keeps only the last ``--blink-settings`` flag, so a profile's own
    flag and the traffic saver's must become one, or one silently loses."""
    if not settings:
        return list(args)
    merged: dict[str, str] = {}
    rest: list[str] = []
    for arg in args:
        name, _, value = arg.partition("=")
        if name.lower() != "--blink-settings":
            rest.append(arg)
            continue
        for pair in value.split(","):
            key, sep, val = pair.strip().partition("=")
            if key:
                merged[key] = val if sep else "true"
    merged.update(settings)
    return [*rest, "--blink-settings=" + ",".join(f"{k}={v}" for k, v in merged.items())]


def chromium_args(profile, args: list[str]) -> list[str]:
    """The Chromium flags ``args`` becomes once the profile's image saver is applied."""
    if getattr(profile, "block_images", False):
        return merge_blink_settings(args, {"imagesEnabled": "false"})
    return list(args)


def chromium_extensions(profile) -> list[str]:
    """Bundled extension dirs a Chromium engine should load for this profile
    (only CloakBrowser uses this; the Playwright engines take the init script)."""
    return [str(EXTENSION_DIR)] if getattr(profile, "block_video", False) else []


def firefox_options(profile) -> dict:
    """Camoufox launch options for the profile's traffic savers."""
    opts: dict = {}
    if getattr(profile, "block_images", False):
        opts["block_images"] = True
    if getattr(profile, "block_video", False):
        opts["firefox_user_prefs"] = {"media.autoplay.default": FIREFOX_BLOCK_ALL_AUTOPLAY}
    return opts


def describe(profile) -> list[str]:
    """Human labels of the savers this profile has on."""
    return [label for attr, label in KINDS.values() if getattr(profile, attr, False)]
