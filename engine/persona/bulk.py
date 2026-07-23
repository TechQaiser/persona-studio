"""
Multi-profile synchroniser — type once, apply to many.

Running fifty accounts means fifty copies of the same chore: point them all at a
new proxy pool, move them to a stronger engine, add a tag, change the startup
page. This module holds the one function that applies such a change to a single
profile, so the CLI (``persona apply``) and the HTTP API share exactly the same
semantics.

The rule everywhere: a key that isn't in the patch is left alone. That makes a
bulk edit additive and safe to repeat — it never silently resets a field you
didn't mention.
"""

from __future__ import annotations

import random
from typing import Optional

from . import devices
from .fingerprint import build_user_agent, generate
from .models import Profile, Proxy

# Everything a bulk edit is allowed to touch. Deliberately excludes id, name and
# created_at: those are what make a profile itself.
FIELDS = (
    "engine", "notes", "locale", "timezone", "proxy",
    "startup_urls", "extensions", "add_tags", "remove_tags", "regen",
)


def apply_patch(profile: Profile, patch: dict) -> list[str]:
    """Apply ``patch`` to ``profile`` in place; return the fields that changed."""
    changed: list[str] = []

    def touch(field: str, new, current):
        if new is None or new == current:
            return False
        changed.append(field)
        return True

    if touch("engine", patch.get("engine"), profile.engine):
        profile.engine = patch["engine"]

    if touch("notes", patch.get("notes"), profile.notes):
        profile.notes = patch["notes"]

    if touch("startup_urls", patch.get("startup_urls"), profile.startup_urls):
        profile.startup_urls = list(patch["startup_urls"])

    if touch("extensions", patch.get("extensions"), profile.extensions):
        profile.extensions = list(patch["extensions"])

    # "proxy" is meaningful when explicitly set to None (= go direct), so it
    # can't go through touch()'s None-means-absent shortcut.
    if "proxy" in patch:
        new_proxy: Optional[Proxy] = patch["proxy"]
        if new_proxy != profile.proxy:
            profile.proxy = new_proxy
            changed.append("proxy")

    added = [t for t in patch.get("add_tags") or [] if t not in profile.tags]
    removed = [t for t in patch.get("remove_tags") or [] if t in profile.tags]
    if added or removed:
        profile.tags = [t for t in profile.tags + added if t not in removed]
        changed.append("tags")

    # Locale drives timezone and languages, so moving one moves all three —
    # otherwise a bulk locale change would leave every profile incoherent.
    locale = patch.get("locale")
    if locale and locale in devices.LOCALES and locale != profile.fingerprint.locale:
        tz, langs = devices.LOCALES[locale]
        profile.fingerprint.locale = locale
        profile.fingerprint.timezone = tz
        profile.fingerprint.languages = list(langs)
        changed.append("locale")

    if touch("timezone", patch.get("timezone"), profile.fingerprint.timezone):
        profile.fingerprint.timezone = patch["timezone"]

    # A fresh fingerprint, but still this profile's OS and locale: the identity
    # slot (name, tags, session) survives, the device behind it changes.
    if patch.get("regen"):
        profile.fingerprint = generate(
            os=profile.fingerprint.os,
            locale=profile.fingerprint.locale,
            proxy=profile.proxy,
        )
        changed.append("fingerprint")

    return changed


def generate_profiles(
    count: int,
    *,
    oses: Optional[list[str]] = None,
    locales: Optional[list[str]] = None,
    chrome_versions: Optional[list[str]] = None,
    engine: str = "playwright",
    name_prefix: str = "Profile",
    start_index: int = 1,
    pad: int = 4,
    tags: Optional[list[str]] = None,
    mobile: bool = False,
    seed: Optional[int] = None,
) -> list[Profile]:
    """Generate ``count`` coherent profiles, spread across the chosen options.

    Each profile gets its own random seed, so its hardware picks and canvas/audio
    noise are distinct — a thousand profiles look like a thousand devices, not
    one cloned a thousand times. ``oses`` and ``locales`` are cycled through so
    the batch is evenly distributed rather than clumped. This is the engine-side
    counterpart to the dashboard's bulk-create; both produce coherent identities.
    """
    if count < 1:
        return []
    oses = [o.lower() for o in (oses or ["windows"])]
    rng = random.Random(seed)
    out: list[Profile] = []

    for i in range(count):
        os_key = oses[i % len(oses)]
        # Advance the locale on a different stride than the OS, so picking two
        # OSes and two locales yields all four pairings rather than locking
        # Windows to the first locale and macOS to the second.
        locale = locales[(i // len(oses)) % len(locales)] if locales else None
        fp = generate(seed=rng.randint(1, 2**31 - 1), os=os_key, locale=locale,
                      mobile=(mobile or os_key == "android"))
        # Restrict browser versions to the caller's subset if one was given.
        if chrome_versions:
            fp.chrome_version = rng.choice(chrome_versions)
            fp.user_agent = build_user_agent(fp.os, fp.chrome_version)
        name = f"{name_prefix}-{str(start_index + i).zfill(pad)}"
        out.append(Profile(name=name, fingerprint=fp, engine=engine,
                           tags=list(tags or [])))
    return out


def select(profiles: list[Profile], refs: Optional[list[str]] = None,
           tag: Optional[str] = None, everything: bool = False) -> list[Profile]:
    """Pick the profiles a bulk edit should hit: by id/name, by tag, or all."""
    if everything:
        return list(profiles)
    chosen: list[Profile] = []
    if tag:
        chosen = [p for p in profiles if tag in p.tags]
    if refs:
        by_ref = {r for r in refs}
        chosen += [p for p in profiles
                   if (p.id in by_ref or p.name in by_ref) and p not in chosen]
    return chosen
