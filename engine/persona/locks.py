"""
Active-session lock: one profile, one running browser.

Opening the same profile twice is the classic "same account, two devices at
once" signal, and two browsers writing one user-data dir corrupt it. The
dashboard already refuses a second launch of a profile *it* started, but a
profile can also be opened by ``persona launch`` in a terminal, by the warm-up
scheduler, or by a dashboard that has since restarted and forgotten.

So the lock lives with the session itself: a small JSON file in the profile's
user-data dir naming the process that holds it. Whoever opens the profile
creates it atomically; a lock whose process is gone is stale and is taken over,
so a crash never leaves a profile stuck.
"""

from __future__ import annotations

import atexit
import json
import os
import socket
import sys
import time
from pathlib import Path
from typing import Optional

LOCK_FILE = ".persona-session.lock"


class ProfileLocked(RuntimeError):
    """The profile is already open in another live process."""

    def __init__(self, holder: dict):
        self.holder = holder
        super().__init__(
            f"This profile is already open (process {holder.get('pid')}, since "
            f"{time.strftime('%H:%M', time.localtime(holder.get('started', 0)))}). "
            "Close that browser first. If nothing is really running, clear the "
            "lock with: persona unlock <profile>"
        )


def pid_alive(pid: int) -> bool:
    """True if a process with this PID is running (no psutil needed)."""
    if not pid or pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.restype = wintypes.HANDLE
        handle = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            # Access denied still means the process exists.
            return ctypes.get_last_error() == 5
        try:
            code = wintypes.DWORD()
            if not k32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True
            return code.value == 259                  # STILL_ACTIVE
        finally:
            k32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _path(user_data_dir) -> Path:
    return Path(user_data_dir) / LOCK_FILE


def read(user_data_dir) -> Optional[dict]:
    """The lock's contents, or None if there is no readable lock."""
    try:
        return json.loads(_path(user_data_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def holder(user_data_dir) -> Optional[dict]:
    """Who holds the profile right now: the lock if its process is alive, else None."""
    info = read(user_data_dir)
    if info and pid_alive(int(info.get("pid") or 0)):
        return info
    return None


def clear(user_data_dir) -> bool:
    """Remove the lock regardless of who holds it. Returns True if one existed."""
    try:
        _path(user_data_dir).unlink()
        return True
    except FileNotFoundError:
        return False


def mark_ready(user_data_dir) -> None:
    """Record that the browser holding this lock is up (the window exists), so
    a supervisor can tell "still starting" from "running". Only the holder's
    own lock is touched."""
    info = read(user_data_dir)
    if not info or info.get("pid") != os.getpid() or info.get("ready"):
        return
    info["ready"] = time.time()
    tmp = _path(user_data_dir).with_suffix(".tmp")
    tmp.write_text(json.dumps(info), encoding="utf-8")
    os.replace(tmp, _path(user_data_dir))


class SessionLock:
    """A held lock. Release it with :meth:`release` (idempotent); it's also
    released when the process exits, so a held lock never outlives its owner."""

    def __init__(self, user_data_dir):
        self.path = _path(user_data_dir)
        self.released = False
        atexit.register(self.release)

    def release(self) -> None:
        if self.released:
            return
        self.released = True
        info = read(self.path.parent)
        # Only remove our own lock: if it was cleared and retaken, leave it.
        if info and info.get("pid") == os.getpid() and info.get("token") == id(self):
            try:
                self.path.unlink()
            except OSError:
                pass


def acquire(user_data_dir) -> SessionLock:
    """Take the profile's lock or raise :class:`ProfileLocked`.

    Creation is atomic (O_EXCL), so two processes racing for the same profile
    can't both win. A stale lock (its process has exited) is replaced.
    """
    path = _path(user_data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(3):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            live = holder(user_data_dir)
            if live:
                raise ProfileLocked(live)
            try:
                path.unlink()                     # stale: its process is gone
            except FileNotFoundError:
                pass
            continue
        lock = SessionLock(user_data_dir)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"pid": os.getpid(), "started": time.time(),
                       "host": socket.gethostname(), "token": id(lock)}, f)
        return lock
    raise ProfileLocked(read(user_data_dir) or {"pid": "?"})
