"""
Secret encryption for the profile store.

Profiles are stored as readable JSON on purpose — you can list, search, diff and
back them up without ceremony. But a couple of fields are genuinely sensitive:
proxy passwords, above all. Keeping those in plaintext next to everything else is
the gap SECURITY.md calls out.

So the store encrypts *only the secrets*, leaving the rest of each profile
readable. You get a vault without losing the transparency that makes the store
nice to work with: names, OS, tags stay visible; the proxy password becomes an
opaque token until you unlock with the master password.

The actual cryptography is delegated to the ``cryptography`` package (Fernet:
AES-128-CBC + HMAC, authenticated) so we don't hand-roll a cipher. The key is
derived from the master password with PBKDF2-HMAC-SHA256. Both live behind an
optional extra — the engine core stays dependency-free — and every entry point
degrades gracefully when the package isn't installed.
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import os
from typing import Optional

PBKDF2_ROUNDS = 200_000
# Marks an encrypted string in the stored JSON, so decrypt knows what to touch
# and a value is never double-encrypted.
ENC_PREFIX = "enc:v1:"


class VaultLocked(RuntimeError):
    """Raised when a secret is needed but no (correct) master password is set."""


def available() -> bool:
    """Is the crypto backend installed?"""
    return importlib.util.find_spec("cryptography") is not None


def _require():
    if not available():
        raise RuntimeError(
            "Encrypted storage needs the 'cryptography' package.\n"
            'Install it with:  pip install -e ".[secure]"'
        )


def new_salt() -> str:
    """A fresh random salt (base64) to store alongside the vault."""
    return base64.b64encode(os.urandom(16)).decode("ascii")


def _fernet(password: str, salt_b64: str):
    from cryptography.fernet import Fernet
    salt = base64.b64decode(salt_b64)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return Fernet(base64.urlsafe_b64encode(key))


def is_encrypted(value) -> bool:
    return isinstance(value, str) and value.startswith(ENC_PREFIX)


def encrypt(password: str, salt_b64: str, plaintext: str) -> str:
    _require()
    token = _fernet(password, salt_b64).encrypt(plaintext.encode("utf-8"))
    return ENC_PREFIX + token.decode("ascii")


def decrypt(password: str, salt_b64: str, value: str) -> str:
    _require()
    from cryptography.fernet import InvalidToken
    try:
        token = value[len(ENC_PREFIX):].encode("ascii")
        return _fernet(password, salt_b64).decrypt(token).decode("utf-8")
    except InvalidToken as e:
        raise VaultLocked("wrong master password") from e


def make_verifier(password: str, salt_b64: str) -> str:
    """A token we can later decrypt to confirm a password is correct."""
    return encrypt(password, salt_b64, "persona-vault-ok")


def check_password(password: str, salt_b64: str, verifier: str) -> bool:
    """Does ``password`` match the one the vault was set up with?"""
    try:
        return decrypt(password, salt_b64, verifier) == "persona-vault-ok"
    except VaultLocked:
        return False
