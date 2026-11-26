"""
Spintax for bulk create: name templates that vary per profile.

A batch named ``Profile-0001 … Profile-0500`` is easy to read, but it labels
every account as one of a series. A template can mix the sequence number with
random parts instead::

    {n}          the profile's number in the batch, zero-padded
    {date}       today's date, 2026-11-26
    {word}       a random word (amber, falcon, harbor, …)
    {name}       a random first name
    {a|b|c}      one of the choices, picked per profile

Templates apply to profile names and tags. Choices can nest
(``{shop|{word}-store}``), and anything in braces that isn't one of these is
left as written. The dashboard's bulk create has the same rules
(``spin()`` in dashboard/src/App.jsx); keep the two in step.
"""

from __future__ import annotations

import random
import re
from datetime import date
from typing import Optional

WORDS = (
    "amber", "anchor", "apple", "arrow", "aspen", "atlas", "birch", "blaze", "breeze",
    "brook", "canyon", "cedar", "cinder", "clover", "comet", "coral", "cosmo", "crest",
    "dawn", "delta", "drift", "ember", "falcon", "fern", "flint", "forest", "frost",
    "garnet", "glade", "granite", "harbor", "hazel", "heron", "indigo", "iris", "ivory",
    "jade", "juniper", "kestrel", "lagoon", "lark", "linen", "lotus", "maple", "meadow",
    "mesa", "mint", "nova", "oak", "olive", "onyx", "orbit", "pebble", "pine", "plume",
    "prairie", "quartz", "raven", "reef", "ridge", "river", "sage", "sierra", "slate",
    "sparrow", "spruce", "summit", "tide", "timber", "topaz", "tulip", "valley", "willow",
)

NAMES = (
    "Aaron", "Adam", "Aisha", "Alex", "Alice", "Amara", "Amir", "Anna", "Ben", "Carla",
    "Chen", "Chloe", "Daniel", "David", "Elena", "Emma", "Ethan", "Fatima", "Felix",
    "Grace", "Hana", "Hassan", "Ivan", "Jack", "James", "Julia", "Kai", "Laila", "Leo",
    "Lina", "Lucas", "Maria", "Maya", "Mia", "Nadia", "Noah", "Nora", "Omar", "Oscar",
    "Priya", "Rafael", "Rosa", "Ryan", "Sara", "Sofia", "Sam", "Tariq", "Tom", "Yara",
    "Yusuf", "Zara", "Zoe",
)

# The innermost {…}: no braces inside it.
_TOKEN = re.compile(r"\{([^{}]*)\}")
_MAX_PASSES = 8   # nesting depth handled; plenty for a name


def has_tokens(text: str) -> bool:
    return bool(_TOKEN.search(text or ""))


def expand(template: str, *, n: Optional[int] = None, pad: int = 0,
           rng: Optional[random.Random] = None, today: Optional[date] = None) -> str:
    """Expand one template for one profile."""
    rng = rng or random.Random()
    day = (today or date.today()).isoformat()

    def one(match: re.Match) -> str:
        body = match.group(1)
        if "|" in body:
            return rng.choice(body.split("|"))
        key = body.strip().lower()
        if key == "n" and n is not None:
            return str(n).zfill(pad)
        if key == "date":
            return day
        if key == "word":
            return rng.choice(WORDS)
        if key == "name":
            return rng.choice(NAMES)
        # Unknown: keep it, marked so the next pass doesn't see it again.
        return "\0" + body + "\1"

    out = template or ""
    for _ in range(_MAX_PASSES):
        new = _TOKEN.sub(one, out)
        if new == out:
            break
        out = new
    return out.replace("\0", "{").replace("\1", "}")


def unique_name(template: str, taken: set, *, n: Optional[int] = None, pad: int = 0,
                rng: Optional[random.Random] = None, tries: int = 25) -> str:
    """Expand ``template`` into a name not in ``taken`` if a few tries allow.

    A template with random parts gets re-rolled on a clash. One that always
    gives the same name (no ``{n}``, nothing random) returns the clash, and the
    caller decides what to do with it."""
    name = expand(template, n=n, pad=pad, rng=rng)
    for _ in range(tries - 1):
        if name not in taken:
            break
        name = expand(template, n=n, pad=pad, rng=rng)
    return name
