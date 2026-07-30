"""Find profiles that share a fingerprint — a linkage risk.

Two profiles that present the *same* fingerprint can be tied together by a site:
identical WebGL strings, screen, hardware and user-agent read as one device
wearing two hats. If one account gets flagged, the linked ones can go down with
it. The whole point of an anti-detect setup is that each identity looks like a
different machine, so an accidental collision quietly defeats it.

This module is pure logic over engine :class:`~persona.models.Profile` objects —
no browser, no I/O — so it's fast to run over thousands of profiles and easy to
test. ``persona collisions`` and the dashboard Health page both call it.
"""

from __future__ import annotations

from typing import Iterable


# The signals a fingerprinting script reads and can correlate across visits.
# Canvas/audio noise is driven separately by ``seed`` (see ``fingerprint``), so
# two profiles sharing every signal below already look like the same device;
# sharing the seed on top means even the canvas noise is pixel-identical.
_SIGNALS = ("os", "user_agent", "platform", "webgl_vendor", "webgl_renderer",
            "screen_width", "screen_height", "hardware_concurrency", "device_memory")


def signature(fp) -> tuple:
    """The tuple of observable signals that identify a fingerprint.

    Profiles with an equal signature look like the same machine to a
    fingerprinting site (before per-seed canvas noise is even considered)."""
    return tuple(getattr(fp, k) for k in _SIGNALS)


def find_collisions(profiles: Iterable) -> list[dict]:
    """Group profiles that share a fingerprint signature.

    Returns one group per colliding signature, most-linked first::

        {"members":   [{"id", "name", "seed"}, ...],   # 2+ profiles
         "identical": bool,                             # they also share the seed
         "signals":   {signal: value, ...}}             # what they have in common

    ``identical`` is the worst case: same signature *and* same canvas/audio seed,
    so the profiles are byte-for-byte indistinguishable. Unique profiles (a
    signature carried by only one profile) are left out."""
    buckets: dict[tuple, list] = {}
    for p in profiles:
        buckets.setdefault(signature(p.fingerprint), []).append(p)

    groups: list[dict] = []
    for sig, members in buckets.items():
        if len(members) < 2:
            continue
        seeds = {m.fingerprint.seed for m in members}
        groups.append({
            "members": [{"id": m.id, "name": m.name, "seed": m.fingerprint.seed}
                        for m in members],
            "identical": len(seeds) == 1,
            "signals": dict(zip(_SIGNALS, sig)),
        })

    groups.sort(key=lambda g: len(g["members"]), reverse=True)
    return groups


def summary(profiles: Iterable) -> dict:
    """A cheap headline for the Health page: how many profiles collide.

    ``clashing`` counts the individual profiles caught in any group (not the
    number of groups), so "3 of 20 profiles share a fingerprint" reads right."""
    profiles = list(profiles)
    groups = find_collisions(profiles)
    clashing = sum(len(g["members"]) for g in groups)
    return {"total": len(profiles), "groups": len(groups),
            "clashing": clashing, "identical": sum(1 for g in groups if g["identical"])}
