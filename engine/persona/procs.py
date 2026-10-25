"""
Find and end the browser processes that belong to one profile.

The process Persona starts for a launch (``persona launch``) owns the browser,
but the browser is its own process tree. If the launcher dies without closing
it (killed from the dashboard on Windows, a crash, a forced shutdown), Chrome
or Firefox keeps running, holds the profile's user-data dir, and the next
launch fails with "profile in use".

Browser processes are matched by their command line, which always names the
profile's directory (Chromium's ``--user-data-dir=``, Firefox's ``-profile``).
That's how GoLogin re-finds its browser after a self-relaunch, and it works
without having to track every child process.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

# Files a browser leaves in its profile dir while it runs.
_RUNNING_MARKERS = ("SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile",
                    "parent.lock", ".parentlock")


def maybe_running(user_data_dir) -> bool:
    """Cheap pre-check: does the dir carry a browser's "I'm running" marker?"""
    root = Path(user_data_dir)
    return any((root / m).exists() or (root / m).is_symlink() for m in _RUNNING_MARKERS)


def _command_lines() -> list[tuple[int, str]]:
    if sys.platform == "win32":
        ps = ("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine } | "
              "ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }")
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                             capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=20,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        sep = "\t"
    else:
        # -ww: no width limit. Without it ps cuts long command lines (a
        # browser's always are) before the profile path.
        out = subprocess.run(["ps", "-ww", "-eo", "pid=,args="], capture_output=True, text=True,
                             timeout=10).stdout
        sep = None
    rows = []
    for line in out.splitlines():
        pid, _, cmd = line.strip().partition(sep or " ")
        if pid.isdigit():
            rows.append((int(pid), cmd))
    return rows


def browser_pids(user_data_dir) -> list[int]:
    """PIDs of processes whose command line names this profile's directory."""
    target = os.path.normcase(str(Path(user_data_dir).resolve()))
    me = os.getpid()
    out = []
    for pid, cmd in _command_lines():
        if pid == me:
            continue
        line = os.path.normcase(cmd.replace('"', ""))
        # Persona's own launcher names the data dir, never the profile's user-data dir.
        if target in line and ("user-data-dir" in line or "-profile" in line):
            out.append(pid)
    return out


def kill(pids: list[int]) -> int:
    """End these processes (and on Windows their trees). Returns how many."""
    n = 0
    for pid in pids:
        try:
            if sys.platform == "win32":
                r = subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                                   capture_output=True, timeout=15,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                n += r.returncode == 0
            else:
                os.kill(pid, signal.SIGKILL)
                n += 1
        except (OSError, subprocess.SubprocessError):
            pass
    return n


def end_browsers(user_data_dir) -> int:
    """Kill any browser still running on this profile's directory."""
    if not maybe_running(user_data_dir):
        return 0
    try:
        return kill(browser_pids(user_data_dir))
    except (OSError, subprocess.SubprocessError):
        return 0
