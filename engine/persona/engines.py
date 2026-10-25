"""
Engine setup: the one-time browser downloads, with progress a UI can show.

Some launch engines fetch their browser the first time they're used:
CloakBrowser downloads its patched Chromium (about 560 MB), Playwright and
Patchright need Chromium (about 170 MB). Done silently inside a profile launch,
that looks like a launch that does nothing for ten minutes. So the download is
reported as it happens: a ``PERSONA_PROGRESS {json}`` line on stdout every
second, which the dashboard reads from the launch (or install) log and turns
into a progress window.

The JSON is ``{engine, stage, done, total, at}``: stage is ``download``,
``extract``, ``done`` or ``error``; done/total are bytes (total 0 while unknown).
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

PROGRESS_TAG = "PERSONA_PROGRESS "
# Approximate one-time download sizes, for the "this will download ..." prompt.
DOWNLOAD_MB = {"cloak": 560, "playwright": 170, "patchright": 170}


def emit(engine: str, stage: str, done: int = 0, total: int = 0, **extra) -> None:
    line = PROGRESS_TAG + json.dumps({"engine": engine, "stage": stage, "done": done,
                                      "total": total, "at": time.time(), **extra})
    print(line, flush=True)


def read_progress(log_path, tail_bytes: int = 16384) -> Optional[dict]:
    """The newest progress record in a log file, or None."""
    try:
        with open(log_path, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - tail_bytes))
            text = f.read().decode("utf-8", "replace")
    except OSError:
        return None
    for line in reversed(text.splitlines()):
        i = line.find(PROGRESS_TAG)
        if i >= 0:
            try:
                return json.loads(line[i + len(PROGRESS_TAG):])
            except ValueError:
                continue
    return None


# ---- what's ready ---------------------------------------------------------------

def _playwright_browsers_dir() -> Path:
    custom = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if custom and custom != "0":
        return Path(custom)
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "ms-playwright"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "ms-playwright"
    return Path.home() / ".cache" / "ms-playwright"


def chromium_ready() -> bool:
    d = _playwright_browsers_dir()
    return d.is_dir() and any(p.name.startswith("chromium-") for p in d.iterdir())


def cloak_ready() -> bool:
    try:
        from cloakbrowser.config import get_binary_path
        return get_binary_path().exists()
    except Exception:
        return False


def status() -> dict:
    """Per engine: is its package installed, and is its browser downloaded?"""
    from . import drivers
    out = {}
    for name in drivers.names():
        installed = drivers.is_installed(name)
        if name == "cloak":
            ready = installed and cloak_ready()
        elif name in ("playwright", "patchright"):
            ready = installed and chromium_ready()
        else:
            ready = installed                  # Camoufox: fetched with `camoufox fetch`
        out[name] = {"installed": installed, "ready": ready,
                     "downloadMB": 0 if ready else DOWNLOAD_MB.get(name, 0)}
    return out


# ---- CloakBrowser: progress from its log + the growing temp file ------------------

_CLOAK_PCT = re.compile(r"Download progress: (\d+)% \((\d+)/(\d+) MB\)")


class _CloakWatcher(logging.Handler):
    """Turns CloakBrowser's download log into PERSONA_PROGRESS lines. It logs
    only every 10%, so between those the size of the archive it's writing (a
    temp file) gives a smooth figure."""

    def __init__(self):
        super().__init__(logging.INFO)
        self.stage: Optional[str] = None
        self.total = 0
        self.started = 0.0
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def emit(self, record: logging.LogRecord) -> None:   # noqa: A003 - logging API
        msg = record.getMessage()
        m = _CLOAK_PCT.search(msg)
        if msg.startswith("Downloading from") and self.stage is None:
            self.stage, self.started = "download", time.time()
            self._thread = threading.Thread(target=self._tick, daemon=True)
            self._thread.start()
        elif m:
            self.total = int(m.group(3)) * 1024 * 1024
        elif msg.startswith("Extracting"):
            self.stage = "extract"
            emit("cloak", "extract", self.total, self.total)
        elif msg.startswith("Binary ready"):
            self.stage = "done"
            emit("cloak", "done", self.total, self.total)

    def _archive_size(self) -> int:
        tmp = Path(tempfile.gettempdir())
        best = 0
        for p in list(tmp.glob("tmp*.zip")) + list(tmp.glob("tmp*.tar.gz")):
            try:
                st = p.stat()
            except OSError:
                continue
            if st.st_mtime >= self.started - 2:
                best = max(best, st.st_size)
        return best

    def _tick(self) -> None:
        while not self._stop.wait(1.0):
            if self.stage != "download":
                continue
            done = self._archive_size()
            emit("cloak", "download", min(done, self.total) if self.total else done, self.total)

    def close(self) -> None:
        self._stop.set()
        super().close()


@contextmanager
def cloak_progress() -> Iterator[None]:
    """Report CloakBrowser's first-run download while the block runs."""
    log = logging.getLogger("cloakbrowser")
    watcher = _CloakWatcher()
    log.addHandler(watcher)
    if log.level == logging.NOTSET or log.level > logging.INFO:
        log.setLevel(logging.INFO)
    try:
        yield
    except BaseException as e:
        if watcher.stage in ("download", "extract"):
            emit("cloak", "error", 0, watcher.total, error=str(e).splitlines()[0][:200])
        raise
    finally:
        log.removeHandler(watcher)
        watcher.close()


# ---- installing ----------------------------------------------------------------------

def install_cloak(attempts: int = 3) -> bool:
    from cloakbrowser.download import ensure_binary
    for i in range(1, attempts + 1):
        try:
            with cloak_progress():
                ensure_binary()
            emit("cloak", "done")
            return True
        except Exception as e:  # noqa: BLE001 - retry
            print(f"Download attempt {i} of {attempts} failed: {e}", flush=True)
    emit("cloak", "error", error="the download kept failing; check your connection and try again")
    return False


_PW_PCT = re.compile(r"(\d+)% of ([\d.]+) ?(MiB|MB|GiB)")


def install_chromium(engine: str = "playwright") -> bool:
    """Fetch Playwright's Chromium (also used by Patchright), reporting progress
    parsed from the installer's own bar."""
    from playwright._impl._driver import compute_driver_executable, get_driver_env
    node, cli = compute_driver_executable()
    emit(engine, "download")
    proc = subprocess.Popen([node, cli, "install", "chromium"], env=get_driver_env(),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace", bufsize=1)
    last = 0.0
    buf = ""
    while True:
        ch = proc.stdout.read(1)
        if not ch:
            break
        if ch in "\r\n":
            m = _PW_PCT.search(buf)
            if m and time.time() - last > 0.5:
                last = time.time()
                total = float(m.group(2)) * (1024 ** 3 if m.group(3) == "GiB" else 1024 ** 2)
                emit(engine, "download", int(total * int(m.group(1)) / 100), int(total))
            elif buf.strip() and not m:
                print(buf.strip(), flush=True)
            buf = ""
        else:
            buf += ch
    ok = proc.wait() == 0
    emit(engine, "done" if ok else "error", **({} if ok else {"error": "Chromium download failed"}))
    return ok


def install(engine: str) -> bool:
    """Download what ``engine`` needs. Returns True when it's ready."""
    if engine == "cloak":
        return cloak_ready() or install_cloak()
    if engine in ("playwright", "patchright", "chromium"):
        return chromium_ready() or install_chromium("playwright" if engine == "chromium" else engine)
    raise RuntimeError(f"Nothing to download for the '{engine}' engine "
                       "(Camoufox: run `camoufox fetch`).")
