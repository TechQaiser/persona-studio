"""
Scheduled warm-up — keep a profile's session from going stale, unattended.

A profile you log into once and then leave for three weeks looks, on your next
visit, like a browser that was frozen and thawed: no fresh cookies, no recent
history, a session token about to expire. Sites that score risk treat that
"cold" return with suspicion. Scheduled warm-up fixes it by running the ordinary
:mod:`persona.warmup` browse on a recurring interval, so each profile keeps a
believable, up-to-date trail without anyone sitting there clicking.

This module is only the *bookkeeping*: a small JSON-backed store of schedules
and the pure rule for which ones are due. Actually running the warm-up is left
to whoever owns a browser — the API server drives it from a background thread
(see :mod:`persona.server`), and ``persona schedule run-due`` drives it from
cron / Task Scheduler for people who don't run the server.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Optional

# A schedule can't fire more often than this, whatever interval is asked for —
# a runaway "every 0 hours" would just launch browsers back to back.
MIN_INTERVAL_HOURS = 0.25


class ScheduleStore:
    """A JSON-backed list of warm-up schedules, one file for the whole set."""

    def __init__(self, root: Path):
        self.path = Path(root) / "schedules.json"

    def list(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []

    def _save(self, items: list[dict]) -> None:
        self.path.write_text(json.dumps(items, indent=2), encoding="utf-8")

    def get(self, sid: str) -> Optional[dict]:
        return next((s for s in self.list() if s.get("id") == sid), None)

    def add(self, *, profile_id: str, every_hours: float, minutes: float = 5,
            preset: str = "general", enabled: bool = True,
            now: Optional[float] = None) -> dict:
        entry = {
            "id": uuid.uuid4().hex[:12],
            "profileId": profile_id,
            "everyHours": max(MIN_INTERVAL_HOURS, float(every_hours)),
            "minutes": float(minutes),
            "preset": preset or "general",
            "enabled": bool(enabled),
            "lastRun": None,
            "createdAt": now,
        }
        items = self.list()
        items.append(entry)
        self._save(items)
        return entry

    def update(self, sid: str, patch: dict) -> Optional[dict]:
        items = self.list()
        out = None
        for s in items:
            if s.get("id") == sid:
                s.update(patch)
                out = s
        if out:
            self._save(items)
        return out

    def delete(self, sid: str) -> bool:
        items = self.list()
        kept = [s for s in items if s.get("id") != sid]
        if len(kept) == len(items):
            return False
        self._save(kept)
        return True

    def mark_run(self, sid: str, when: float) -> Optional[dict]:
        return self.update(sid, {"lastRun": when})


def next_run_at(schedule: dict) -> float:
    """When this schedule is next due, as a unix timestamp.

    Never run before? Due at creation time (so a new schedule fires on the next
    tick rather than waiting a full interval). Otherwise last run + interval.
    """
    interval = max(MIN_INTERVAL_HOURS, float(schedule.get("everyHours", 1))) * 3600
    last = schedule.get("lastRun")
    if last is None:
        return float(schedule.get("createdAt") or 0)
    return float(last) + interval


def due_schedules(schedules: list[dict], now: float) -> list[dict]:
    """The enabled schedules whose next-run time has arrived. Pure — no clock,
    no browser — so it can be tested directly."""
    return [s for s in schedules
            if s.get("enabled", True) and next_run_at(s) <= now]
