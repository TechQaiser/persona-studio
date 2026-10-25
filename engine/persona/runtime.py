"""
Where Persona is running from: a source install, or the packaged Windows app.

The server runs browser work in child processes (``persona launch``, the trust
check, warm-ups...). From source that's ``python -m persona``; inside the
packaged ``PersonaStudio.exe`` there is no separate Python, so the exe calls
itself with the same CLI arguments (see :mod:`persona.app`).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional


def frozen() -> bool:
    """True inside the packaged app (PyInstaller)."""
    return bool(getattr(sys, "frozen", False))


def persona_cmd(unbuffered: bool = False) -> list[str]:
    """The command that runs Persona's CLI in a child process."""
    if frozen():
        return [sys.executable]
    return [sys.executable, *(["-u"] if unbuffered else []), "-m", "persona"]


def bundled_dashboard() -> Optional[Path]:
    """The built dashboard to serve alongside the API: the copy inside the
    packaged app, or one named by PERSONA_DASHBOARD_DIR. None if there's none."""
    candidates = []
    if os.environ.get("PERSONA_DASHBOARD_DIR"):
        candidates.append(Path(os.environ["PERSONA_DASHBOARD_DIR"]))
    if frozen():
        candidates.append(Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "dashboard")
    for c in candidates:
        if (c / "index.html").is_file():
            return c
    return None
