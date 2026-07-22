"""Data models for fingerprints and profiles."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict, fields
from typing import Optional


@dataclass
class Fingerprint:
    """A complete, internally-consistent browser fingerprint.

    Every field is chosen so the parts agree with one another (see
    ``fingerprint.generate``). The ``seed`` makes canvas/audio noise
    deterministic, so the same profile looks identical across launches.
    """

    os: str
    user_agent: str
    platform: str
    ch_platform: str
    chrome_version: str
    screen_width: int
    screen_height: int
    viewport_width: int
    viewport_height: int
    hardware_concurrency: int
    device_memory: int
    webgl_vendor: str
    webgl_renderer: str
    locale: str
    timezone: str
    languages: list[str]
    is_mobile: bool = False
    seed: int = 0
    # Secondary signals. They have defaults so profiles saved by older versions
    # still load; ``generate()`` fills them from the device archetype.
    fonts: list[str] = field(default_factory=list)   # installed-font probe answers
    cameras: int = 1                                  # enumerateDevices() videoinput
    microphones: int = 1                              # enumerateDevices() audioinput

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Fingerprint":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class Proxy:
    """Proxy configuration for a profile."""

    server: str  # e.g. "http://host:port" or "socks5://host:port"
    username: Optional[str] = None
    password: Optional[str] = None
    country: Optional[str] = None  # ISO code, used to align locale/timezone

    def to_playwright(self) -> dict:
        cfg: dict = {"server": self.server}
        if self.username:
            cfg["username"] = self.username
        if self.password:
            cfg["password"] = self.password
        return cfg

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Proxy":
        return cls(**d)


@dataclass
class Profile:
    """A named browser identity: fingerprint + proxy + metadata + storage."""

    name: str
    fingerprint: Fingerprint
    proxy: Optional[Proxy] = None
    notes: str = ""
    tags: list[str] = field(default_factory=list)
    engine: str = "playwright"  # which launch backend to use (see drivers.py)
    startup_urls: list[str] = field(default_factory=list)  # opened on launch
    extensions: list[str] = field(default_factory=list)  # unpacked extension dirs
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "notes": self.notes,
            "tags": self.tags,
            "engine": self.engine,
            "startup_urls": self.startup_urls,
            "extensions": self.extensions,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "fingerprint": self.fingerprint.to_dict(),
            "proxy": self.proxy.to_dict() if self.proxy else None,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Profile":
        return cls(
            id=d["id"],
            name=d["name"],
            notes=d.get("notes", ""),
            tags=d.get("tags", []),
            engine=d.get("engine", "playwright"),
            startup_urls=d.get("startup_urls", []),
            extensions=d.get("extensions", []),
            created_at=d.get("created_at", time.time()),
            updated_at=d.get("updated_at", time.time()),
            fingerprint=Fingerprint.from_dict(d["fingerprint"]),
            proxy=Proxy.from_dict(d["proxy"]) if d.get("proxy") else None,
        )
