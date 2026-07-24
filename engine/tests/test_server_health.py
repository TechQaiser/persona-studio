"""The schedule and health endpoints, driven through the real app.

These need FastAPI; skipped cleanly when it isn't installed. The scheduler
thread is turned off (``start_scheduler=False``) so nothing launches a browser."""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from persona.server import create_app


@pytest.fixture()
def client(tmp_path):
    app = create_app(str(tmp_path), start_scheduler=False)
    return TestClient(app)


def _make_profile(client, name="Acct"):
    body = {"name": name, "os": "Windows", "screen": "1920x1080", "cores": 8,
            "memory": 16, "locale": "en-US", "engine": "cloak"}
    return client.post("/api/profiles", json=body).json()


def test_schedule_crud(client):
    prof = _make_profile(client)
    r = client.post("/api/schedules", json={"profileId": prof["id"], "everyHours": 12,
                                            "minutes": 6, "preset": "ads"})
    assert r.status_code == 200
    sid = r.json()["id"]
    assert r.json()["profileName"] == "Acct"
    assert r.json()["due"] is True                 # never run -> due now

    assert any(s["id"] == sid for s in client.get("/api/schedules").json())

    r = client.put(f"/api/schedules/{sid}", json={"enabled": False, "preset": "crypto"})
    assert r.json()["enabled"] is False and r.json()["preset"] == "crypto"

    assert client.delete(f"/api/schedules/{sid}").json()["ok"] is True
    assert client.get("/api/schedules").json() == []


def test_schedule_rejects_unknown_profile(client):
    assert client.post("/api/schedules", json={"profileId": "nope"}).status_code == 404


def test_health_overview(client):
    p1 = _make_profile(client, "One")
    _make_profile(client, "Two")
    client.post("/api/schedules", json={"profileId": p1["id"], "everyHours": 8})

    r = client.get("/api/profiles/health")
    assert r.status_code == 200
    data = r.json()
    assert data["summary"]["total"] == 2
    assert data["summary"]["scheduled"] == 1
    rows = {row["name"]: row for row in data["profiles"]}
    assert rows["One"]["schedule"]["everyHours"] == 8
    assert rows["Two"]["schedule"] is None
    # A freshly-created, well-formed profile is coherent and ungraded.
    assert rows["One"]["coherent"] is True
    assert rows["One"]["trust"] is None
    assert rows["One"]["proxy"]["set"] is False
