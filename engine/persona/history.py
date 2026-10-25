"""
Session hygiene and profile history.

Two jobs, both run when a browsing session ends:

* **Prune.** Most of a profile's size is caches the browser rebuilds on its own
  (HTTP cache, compiled code, GPU shaders). They carry no identity, so they're
  deleted on close, and left out of backups and snapshots.

* **Snapshot.** The session that remains (cookies, storage, history, logins) is
  zipped into ``<data-dir>/history/<profile-id>/``, keeping the last few. A
  profile can be rolled back to any of them: useful when a site logs you out,
  an account gets flagged after a change, or a session gets corrupted. Restoring
  snapshots the current state first, so a restore can itself be undone.

Everything here works on plain paths, so it's shared by the launcher, the
backup code in :mod:`persona.store` and the API.
"""

from __future__ import annotations

import shutil
import time
import zipfile
from pathlib import Path
from typing import Iterator, Optional

from .locks import LOCK_FILE

# Directories the browser regenerates by itself, relative to the user-data dir.
# Chromium keeps per-profile caches under Default/ and GPU caches at the root;
# Firefox (Camoufox) keeps its HTTP cache in cache2/. Extensions are *not* here:
# Persona doesn't re-download them, so pruning would lose Web Store installs.
JUNK_DIRS = (
    "Default/Cache", "Default/Code Cache", "Default/GPUCache", "Default/DawnCache",
    "Default/DawnGraphiteCache", "Default/DawnWebGPUCache", "Default/Service Worker/CacheStorage",
    "Default/Service Worker/ScriptCache",
    "GrShaderCache", "GraphiteDawnCache", "ShaderCache", "component_crx_cache",
    "cache2", "startupCache", "shader-cache",
)
# Single files that are runtime state, not session state.
SKIP_FILES = {LOCK_FILE, "SingletonLock", "SingletonCookie", "SingletonSocket",
              "lockfile", "parent.lock", ".parentlock"}

DEFAULT_KEEP = 5
_STAMP = "%Y%m%d-%H%M%S"


def _is_junk(rel: Path) -> bool:
    parts = rel.as_posix()
    return any(parts == j or parts.startswith(j + "/") for j in JUNK_DIRS)


def session_files(user_data_dir) -> Iterator[tuple[Path, Path]]:
    """Every file worth keeping in a session, as ``(absolute, relative)`` pairs."""
    root = Path(user_data_dir)
    if not root.exists():
        return
    for f in root.rglob("*"):
        if not f.is_file() or f.name in SKIP_FILES:
            continue
        rel = f.relative_to(root)
        if not _is_junk(rel):
            yield f, rel


def prune(user_data_dir) -> int:
    """Delete the regenerable caches. Returns the bytes freed."""
    root = Path(user_data_dir)
    freed = 0
    for j in JUNK_DIRS:
        d = root / j
        if d.is_dir():
            freed += sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
            shutil.rmtree(d, ignore_errors=True)
    return freed


# ---- per-profile storage policy --------------------------------------------------
# What a profile can choose *not* to keep between sessions. Each kind maps to
# the files that hold it in Chromium (under Default/) and in Firefox (Camoufox).
# Cookies aren't here: they're the session itself. Firefox keeps history and
# bookmarks in one database (places.sqlite), and localStorage and IndexedDB
# both under storage/default, so those go only when *both* kinds are off.
STORAGE_KINDS = {
    "local": "Local storage",
    "indexeddb": "IndexedDB",
    "history": "Browsing history",
    "passwords": "Saved passwords",
    "session": "Open tabs (last session)",
    "bookmarks": "Bookmarks",
    "extensions": "Extensions installed in the browser",
}
_CHROMIUM = {
    "local": ["Default/Local Storage", "Default/Session Storage"],
    "indexeddb": ["Default/IndexedDB", "Default/File System", "Default/blob_storage"],
    "history": ["Default/History", "Default/History-journal", "Default/Visited Links",
                "Default/Top Sites", "Default/Top Sites-journal", "Default/Shortcuts",
                "Default/Shortcuts-journal", "Default/Network Action Predictor",
                "Default/Network Action Predictor-journal"],
    "passwords": ["Default/Login Data", "Default/Login Data-journal",
                  "Default/Login Data For Account", "Default/Login Data For Account-journal"],
    "session": ["Default/Sessions", "Default/Current Session", "Default/Current Tabs",
                "Default/Last Session", "Default/Last Tabs"],
    "bookmarks": ["Default/Bookmarks", "Default/Bookmarks.bak"],
    "extensions": ["Default/Extensions", "Default/Extension State", "Default/Extension Rules",
                   "Default/Extension Scripts", "Default/Local Extension Settings",
                   "Default/Sync Extension Settings"],
}
_FIREFOX = {
    "local": ["webappsstore.sqlite", "webappsstore.sqlite-wal"],
    "passwords": ["logins.json", "logins-backup.json"],
    "session": ["sessionstore.jsonlz4", "sessionstore-backups"],
    "extensions": ["extensions", "extensions.json", "extension-settings.json",
                   "extension-preferences.json"],
}
_FIREFOX_PAIRS = {
    ("history", "bookmarks"): ["places.sqlite", "places.sqlite-wal"],
    ("local", "indexeddb"): ["storage/default"],
}


def normalize_storage(raw) -> dict:
    """A full ``{kind: keep}`` map. Missing or unknown kinds default to *keep*."""
    raw = raw if isinstance(raw, dict) else {}
    return {k: bool(raw.get(k, True)) for k in STORAGE_KINDS}


def apply_storage_policy(user_data_dir, storage) -> list[str]:
    """Delete what the profile chose not to keep. Returns the removed paths."""
    keep = normalize_storage(storage)
    off = {k for k, v in keep.items() if not v}
    if not off:
        return []
    targets = [p for k in off for p in _CHROMIUM.get(k, []) + _FIREFOX.get(k, [])]
    targets += [p for pair, paths in _FIREFOX_PAIRS.items() if set(pair) <= off for p in paths]
    root = Path(user_data_dir)
    removed = []
    for rel in targets:
        path = root / rel
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        elif path.is_file():
            path.unlink(missing_ok=True)
        else:
            continue
        removed.append(rel)
    return removed


# ---- snapshots -----------------------------------------------------------------

def _dir(history_root, profile_id: str) -> Path:
    return Path(history_root) / profile_id


def list_snapshots(history_root, profile_id: str) -> list[dict]:
    """Newest first: ``{id, at, size, reason}`` for each snapshot."""
    d = _dir(history_root, profile_id)
    out = []
    for z in d.glob("*.zip") if d.exists() else ():
        stamp, _, reason = z.stem.partition("_")
        base, _, seq = stamp.partition(".")
        try:
            at = time.mktime(time.strptime(base, _STAMP))
            seq = int(seq or 1)
        except ValueError:
            continue
        out.append({"id": z.stem, "at": at, "size": z.stat().st_size,
                    "reason": reason or "session", "_order": (base, seq)})
    out.sort(key=lambda s: s.pop("_order"), reverse=True)
    return out


def _latest_mtime(user_data_dir) -> float:
    return max((f.stat().st_mtime for f, _ in session_files(user_data_dir)), default=0.0)


def snapshot(user_data_dir, history_root, profile_id: str, keep: int = DEFAULT_KEEP,
             reason: str = "session", force: bool = False) -> Optional[dict]:
    """Zip the session into a new snapshot and trim to the newest ``keep``.

    Skipped (returns None) when the session is empty, ``keep`` is 0, or nothing
    changed since the newest snapshot, so opening a profile and closing it again
    doesn't push a real snapshot out of the history.
    """
    if keep <= 0:
        return None
    files = list(session_files(user_data_dir))
    if not files:
        return None
    existing = list_snapshots(history_root, profile_id)
    if existing and not force:
        newest = _dir(history_root, profile_id) / f"{existing[0]['id']}.zip"
        if _latest_mtime(user_data_dir) <= newest.stat().st_mtime:
            return None
    d = _dir(history_root, profile_id)
    d.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime(_STAMP)
    # Two snapshots in one second get a rising sequence number, never a freed
    # (trimmed) name, so the newest always sorts first.
    seqs = [int(z.stem.partition("_")[0].partition(".")[2] or 1)
            for z in d.glob(f"{stamp}*.zip")]
    n = max(seqs, default=0) + 1
    name = f"{stamp}_{reason}" if n == 1 else f"{stamp}.{n}_{reason}"
    tmp = d / f"{name}.zip.part"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for f, rel in files:
            try:
                z.write(f, arcname=rel.as_posix())
            except OSError:
                pass                              # a file vanished mid-write
    tmp.replace(d / f"{name}.zip")
    for old in list_snapshots(history_root, profile_id)[keep:]:
        (d / f"{old['id']}.zip").unlink(missing_ok=True)
    return next(s for s in list_snapshots(history_root, profile_id) if s["id"] == name)


def restore(user_data_dir, history_root, profile_id: str, snapshot_id: str,
            keep: int = DEFAULT_KEEP) -> dict:
    """Replace the session with a snapshot. The current state is snapshotted
    first (reason ``before-restore``), so this can be undone. The caller must
    make sure the profile isn't open."""
    src = _dir(history_root, profile_id) / f"{snapshot_id}.zip"
    if any(c in snapshot_id for c in "/\\:") or ".." in snapshot_id or not src.is_file():
        raise FileNotFoundError(f"no snapshot '{snapshot_id}' for this profile")
    # Keep one extra so the pre-restore copy can't evict the snapshot we restore.
    snapshot(user_data_dir, history_root, profile_id, keep=keep + 1,
             reason="before-restore", force=True)
    root = Path(user_data_dir)
    if root.exists():
        for child in root.iterdir():
            if child.name == LOCK_FILE:
                continue
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
    root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(src) as z:
        for member in z.namelist():
            target = (root / member).resolve()
            if root.resolve() not in target.parents:
                continue                          # never write outside the dir
            if member.endswith("/"):
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(z.read(member))
    return {"restored": snapshot_id}


def delete_all(history_root, profile_id: str) -> None:
    shutil.rmtree(_dir(history_root, profile_id), ignore_errors=True)
