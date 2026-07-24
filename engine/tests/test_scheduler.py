"""Warm-up schedule bookkeeping: the store round-trips, and the due-rule fires
at the right time. No browser, no clock — a fixed ``now`` is passed in."""

from persona.scheduler import (MIN_INTERVAL_HOURS, ScheduleStore, due_schedules,
                               next_run_at)

HOUR = 3600


def test_add_and_list_round_trip(tmp_path):
    st = ScheduleStore(tmp_path)
    entry = st.add(profile_id="p1", every_hours=12, minutes=7, preset="ads", now=1000)
    assert entry["profileId"] == "p1" and entry["preset"] == "ads"
    assert st.list()[0]["id"] == entry["id"]
    assert st.get(entry["id"])["minutes"] == 7


def test_interval_is_floored(tmp_path):
    st = ScheduleStore(tmp_path)
    entry = st.add(profile_id="p1", every_hours=0, now=0)
    assert entry["everyHours"] == MIN_INTERVAL_HOURS


def test_delete(tmp_path):
    st = ScheduleStore(tmp_path)
    e = st.add(profile_id="p1", every_hours=1, now=0)
    assert st.delete(e["id"]) is True
    assert st.list() == []
    assert st.delete("nope") is False


def test_never_run_is_due_at_creation():
    s = {"id": "x", "profileId": "p", "everyHours": 12, "enabled": True,
         "lastRun": None, "createdAt": 5000}
    assert next_run_at(s) == 5000
    assert due_schedules([s], now=5000) == [s]
    assert due_schedules([s], now=4999) == []


def test_next_run_is_last_plus_interval():
    s = {"id": "x", "profileId": "p", "everyHours": 12, "enabled": True,
         "lastRun": 10_000, "createdAt": 0}
    assert next_run_at(s) == 10_000 + 12 * HOUR
    assert due_schedules([s], now=10_000 + 12 * HOUR) == [s]
    assert due_schedules([s], now=10_000 + 11 * HOUR) == []


def test_disabled_never_due():
    s = {"id": "x", "profileId": "p", "everyHours": 1, "enabled": False,
         "lastRun": None, "createdAt": 0}
    assert due_schedules([s], now=10 ** 9) == []


def test_mark_run_moves_next_due(tmp_path):
    st = ScheduleStore(tmp_path)
    e = st.add(profile_id="p1", every_hours=6, now=0)
    assert due_schedules(st.list(), now=1) == st.list()   # due (never run)
    st.mark_run(e["id"], 1000)
    assert due_schedules(st.list(), now=1000) == []        # not due again yet
    assert due_schedules(st.list(), now=1000 + 6 * HOUR) == st.list()
