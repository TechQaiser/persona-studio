"""
Persona -- open-source browser fingerprint & profile manager.

A lightweight, self-hosted alternative to commercial anti-detect browsers for
multi-account management, QA testing and privacy research. Create named browser
profiles, each with a coherent fingerprint and its own proxy and persistent
session, then launch them on demand.

Quick start:

    from persona import ProfileStore, generate, Profile

    store = ProfileStore()
    fp = generate(os="windows", locale="en-US")
    profile = store.save(Profile(name="acct-01", fingerprint=fp))
    # persona launch acct-01   (via the CLI)
"""

from .models import Fingerprint, Profile, Proxy
from .fingerprint import generate, validate, sec_ch_ua
from .store import ProfileStore

__version__ = "0.1.0"

__all__ = [
    "Fingerprint",
    "Profile",
    "Proxy",
    "generate",
    "validate",
    "sec_ch_ua",
    "ProfileStore",
    "__version__",
]
