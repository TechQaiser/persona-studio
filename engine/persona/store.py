"""
Profile storage.

Profiles live as individual JSON files under a data directory (default
``~/.persona/profiles``). One file per profile keeps things transparent,
diff-friendly and trivial to back up or sync. Browser user-data (cookies,
localStorage) is kept in a sibling ``user-data/<id>`` directory that the
launcher points the browser at, so sessions persist between runs.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional

from .models import Profile


class ProfileStore:
    def __init__(self, root: Optional[str | Path] = None):
        self.root = Path(root or (Path.home() / ".persona")).expanduser()
        self.profiles_dir = self.root / "profiles"
        self.userdata_dir = self.root / "user-data"
        self.config_path = self.root / "config.json"
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self.userdata_dir.mkdir(parents=True, exist_ok=True)

    # ---- config (small key/value settings) -------------------------------
    # CloakBrowser is the top-priority default: it's the strongest engine.
    DEFAULT_ENGINE = "cloak"

    def get_config(self) -> dict:
        if not self.config_path.exists():
            return {}
        try:
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def save_config(self, cfg: dict) -> dict:
        self.config_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        return cfg

    def get_default_engine(self) -> str:
        """The engine used for new profiles when none is given (persisted)."""
        return self.get_config().get("default_engine") or self.DEFAULT_ENGINE

    def set_default_engine(self, name: str) -> str:
        cfg = self.get_config()
        cfg["default_engine"] = name
        self.save_config(cfg)
        return name

    # ---- paths -----------------------------------------------------------
    def _path(self, profile_id: str) -> Path:
        return self.profiles_dir / f"{profile_id}.json"

    def user_data_path(self, profile_id: str) -> Path:
        p = self.userdata_dir / profile_id
        p.mkdir(parents=True, exist_ok=True)
        return p

    # ---- CRUD ------------------------------------------------------------
    def save(self, profile: Profile) -> Profile:
        profile.updated_at = time.time()
        self._path(profile.id).write_text(
            json.dumps(profile.to_dict(), indent=2), encoding="utf-8"
        )
        return profile

    def get(self, profile_id: str) -> Optional[Profile]:
        path = self._path(profile_id)
        if not path.exists():
            return None
        return Profile.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def find_by_name(self, name: str) -> Optional[Profile]:
        for p in self.list():
            if p.name == name:
                return p
        return None

    def resolve(self, ref: str) -> Optional[Profile]:
        """Look up a profile by id first, then by name."""
        return self.get(ref) or self.find_by_name(ref)

    def list(self) -> list[Profile]:
        out: list[Profile] = []
        for f in sorted(self.profiles_dir.glob("*.json")):
            try:
                out.append(Profile.from_dict(json.loads(f.read_text(encoding="utf-8"))))
            except (json.JSONDecodeError, KeyError):
                continue  # skip corrupt files rather than crash
        return sorted(out, key=lambda p: p.created_at)

    def delete(self, profile_id: str) -> bool:
        path = self._path(profile_id)
        if not path.exists():
            return False
        path.unlink()
        # best-effort cleanup of user-data
        ud = self.userdata_dir / profile_id
        if ud.exists():
            import shutil
            shutil.rmtree(ud, ignore_errors=True)
        return True

    # ---- import / export -------------------------------------------------
    def export(self, profile_id: str, dest: str | Path) -> Optional[Path]:
        prof = self.get(profile_id)
        if not prof:
            return None
        dest = Path(dest)
        dest.write_text(json.dumps(prof.to_dict(), indent=2), encoding="utf-8")
        return dest

    def import_file(self, src: str | Path) -> Profile:
        data = json.loads(Path(src).read_text(encoding="utf-8"))
        prof = Profile.from_dict(data)
        return self.save(prof)
