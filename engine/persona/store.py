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
import uuid
import zipfile
from pathlib import Path
from typing import Optional

from . import crypto
from .models import Profile


class ProfileStore:
    def __init__(self, root: Optional[str | Path] = None,
                 password: Optional[str] = None):
        self.root = Path(root or (Path.home() / ".persona")).expanduser()
        self.profiles_dir = self.root / "profiles"
        self.userdata_dir = self.root / "user-data"
        self.config_path = self.root / "config.json"
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self.userdata_dir.mkdir(parents=True, exist_ok=True)
        # The master password comes from the caller or the environment, so a
        # launched subprocess inherits it without it ever hitting disk.
        self._password = password or os.environ.get("PERSONA_PASSWORD") or None

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

    # ---- vault (encrypt-at-rest for secrets) -----------------------------
    # The fields worth encrypting: anything that grants access if leaked. Cookies
    # live in Chromium's own encrypted store, so the one in our plaintext JSON is
    # the proxy password.
    SECRET_PATHS = (("proxy", "password"),)

    def vault(self) -> Optional[dict]:
        """The vault descriptor ({salt, verifier}) if a password was ever set."""
        return self.get_config().get("vault")

    def vault_enabled(self) -> bool:
        return self.vault() is not None

    def unlocked(self) -> bool:
        """True when secrets can actually be read/written (right password set)."""
        v = self.vault()
        if not v:
            return True                      # nothing to unlock
        return bool(self._password) and crypto.check_password(
            self._password, v["salt"], v["verifier"])

    def enable_vault(self, password: str) -> int:
        """Turn on the vault and encrypt every existing secret. Returns the count."""
        crypto._require()
        if self.vault_enabled():
            raise RuntimeError("A vault is already set up. Use `vault change` to rotate it.")
        salt = crypto.new_salt()
        cfg = self.get_config()
        cfg["vault"] = {"salt": salt, "verifier": crypto.make_verifier(password, salt)}
        self.save_config(cfg)
        self._password = password
        # Re-save every profile so its secrets get written back encrypted.
        n = 0
        for prof in self.list():
            if any(self._secret_values(prof)):
                self.save(prof)
                n += 1
        return n

    def _secret_values(self, profile: Profile) -> list:
        vals = []
        d = profile.to_dict()
        for a, b in self.SECRET_PATHS:
            sec = (d.get(a) or {}).get(b) if isinstance(d.get(a), dict) else None
            vals.append(sec)
        return vals

    def _apply_secrets(self, data: dict, mode: str) -> dict:
        """Encrypt (mode='enc') or decrypt (mode='dec') the secret fields in a
        profile dict, in place. A no-op when there's no vault."""
        v = self.vault()
        if not v:
            return data
        pw = self._password
        for a, b in self.SECRET_PATHS:
            node = data.get(a)
            if not isinstance(node, dict) or not node.get(b):
                continue
            val = node[b]
            if mode == "enc":
                if pw and self.unlocked() and not crypto.is_encrypted(val):
                    node[b] = crypto.encrypt(pw, v["salt"], val)
            else:  # dec
                if crypto.is_encrypted(val):
                    node[b] = crypto.decrypt(pw, v["salt"], val) if (pw and self.unlocked()) else None
        return data

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
        # Refuse to write a plaintext secret over an encrypted one: if the vault
        # is on but locked, saving would silently downgrade security.
        if self.vault_enabled() and not self.unlocked() and any(self._secret_values(profile)):
            raise crypto.VaultLocked(
                "the vault is locked — unlock with the master password before saving "
                "a profile that has a proxy password")
        data = self._apply_secrets(profile.to_dict(), "enc")
        self._path(profile.id).write_text(json.dumps(data, indent=2), encoding="utf-8")
        return profile

    def get(self, profile_id: str) -> Optional[Profile]:
        path = self._path(profile_id)
        if not path.exists():
            return None
        data = self._apply_secrets(json.loads(path.read_text(encoding="utf-8")), "dec")
        return Profile.from_dict(data)

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
                data = self._apply_secrets(json.loads(f.read_text(encoding="utf-8")), "dec")
                out.append(Profile.from_dict(data))
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

    # ---- backup / restore ------------------------------------------------
    # ``export``/``import_file`` move only the profile *config* (a JSON file).
    # A backup is the whole identity: the config **and** its browser session
    # (cookies, localStorage — everything under user-data), zipped into one
    # portable file you can archive or carry to another machine.
    def backup(self, profile_id: str, dest: str | Path) -> Optional[Path]:
        """Zip a profile and its entire browser session into one file.

        The profile JSON inside the archive holds any proxy password in
        *plaintext* (secrets are decrypted on read), so treat a backup file as
        sensitive — it grants everything the profile does. Returns the path, or
        ``None`` if no such profile exists."""
        prof = self.get(profile_id)
        if not prof:
            return None
        dest = Path(dest)
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("profile.json", json.dumps(prof.to_dict(), indent=2))
            ud = self.userdata_dir / profile_id
            if ud.exists():
                for f in ud.rglob("*"):
                    if f.is_file():
                        z.write(f, arcname=str(Path("user-data") / f.relative_to(ud)))
        return dest

    def restore(self, src: str | Path, new_id: bool = False) -> Profile:
        """Recreate a profile and its session from a :meth:`backup` archive.

        By default the profile keeps its original id, overwriting any profile
        already under that id (a true restore). Pass ``new_id=True`` to bring it
        in as a fresh copy instead — useful for cloning a warmed-up session
        onto a second machine without the two fighting over one id."""
        src = Path(src)
        with zipfile.ZipFile(src, "r") as z:
            data = json.loads(z.read("profile.json").decode("utf-8"))
            prof = Profile.from_dict(data)
            if new_id:
                prof.id = uuid.uuid4().hex[:12]
            self.save(prof)
            ud = self.user_data_path(prof.id)
            for name in z.namelist():
                if not name.startswith("user-data/") or name.endswith("/"):
                    continue
                target = ud / name[len("user-data/"):]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(z.read(name))
        return prof
