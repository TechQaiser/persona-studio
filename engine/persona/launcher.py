"""
Browser launcher.

This is a thin dispatcher: it picks the launch backend named by the profile
(``profile.engine``) and hands off to it. The backends live in ``drivers.py`` —
stock Playwright, patched Playwright (patchright), Camoufox, or any you register.

Every backend applies the profile's identity and uses a *persistent* session tied
to the profile's user-data directory, so cookies and localStorage survive between
launches and each profile behaves like a real, returning user.
"""

from __future__ import annotations

from typing import Optional

from . import drivers
from .models import Profile
from .store import ProfileStore


def launch(profile: Profile, store: ProfileStore, headless: bool = False,
           keep_open: bool = True, engine: Optional[str] = None):
    """Launch a browser wearing ``profile``'s identity via its chosen engine.

    Args:
        engine: override the profile's ``engine`` for this launch. Defaults to
            ``profile.engine`` (which defaults to ``"playwright"``).

    Returns the backend's launch handles when ``keep_open`` is True so a caller
    can drive the session; when False it opens, waits for the window to close,
    then tears everything down.
    """
    name = engine or profile.engine or "playwright"
    driver = drivers.get(name)
    return driver(profile, store, headless=headless, keep_open=keep_open)
