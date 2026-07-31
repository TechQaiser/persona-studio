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


def _make_profile(client, name="Acct", **over):
    body = {"name": name, "os": "Windows", "screen": "1920x1080", "cores": 8,
            "memory": 16, "locale": "en-US", "engine": "cloak"}
    body.update(over)
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


def test_attach_rejects_non_chromium_engine(client):
    # camoufox is Firefox-based — no Chrome DevTools to attach to. The endpoint
    # must reject it *before* launching anything.
    prof = _make_profile(client, "Fox", engine="camoufox")
    r = client.post(f"/api/profiles/{prof['id']}/attach")
    assert r.status_code == 400
    assert "DevTools" in r.json()["detail"]


def test_attach_unknown_profile_404(client):
    assert client.post("/api/profiles/nope/attach").status_code == 404


def test_collisions_endpoint_and_health_flag(client):
    _make_profile(client, "Twin-A")                 # identical default fields ->
    _make_profile(client, "Twin-B")                 # same engine fingerprint
    _make_profile(client, "Solo", os="macOS")       # different device -> unique

    data = client.get("/api/profiles/collisions").json()
    assert data["total"] == 3
    assert len(data["groups"]) == 1
    assert {m["name"] for m in data["groups"][0]["members"]} == {"Twin-A", "Twin-B"}

    # The Health overview mirrors it: a summary count and a per-row flag.
    h = client.get("/api/profiles/health").json()
    assert h["summary"]["colliding"] == 2
    rows = {r["name"]: r for r in h["profiles"]}
    assert rows["Twin-A"]["collides"] is True and rows["Twin-A"]["needsAttention"] is True
    assert rows["Solo"]["collides"] is False


def test_config_exposes_folders_root_and_version(client):
    cfg = client.get("/api/config").json()
    assert "default_engine" in cfg
    assert isinstance(cfg["folders"], list)
    assert cfg["root"] and isinstance(cfg["root"], str)
    assert cfg["version"]
    # A folder a profile lives in shows up even without being created explicitly.
    _make_profile(client, "InFolder", folder="Crypto")
    assert "Crypto" in client.get("/api/config").json()["folders"]


def test_folder_create_rename_delete(client):
    # Create an empty folder — it persists even with no profiles in it.
    assert "Ads" in client.post("/api/folders", json={"name": "Ads"}).json()["folders"]
    assert client.post("/api/folders", json={"name": ""}).status_code == 400

    p = _make_profile(client, "Store", folder="Ads")

    # Rename carries the profile over to the new name.
    r = client.post("/api/folders/rename", json={"from": "Ads", "to": "Marketing"}).json()
    assert "Marketing" in r["folders"] and "Ads" not in r["folders"]
    moved = {row["id"]: row for row in client.get("/api/profiles").json()}
    assert moved[p["id"]]["folder"] == "Marketing"

    # Delete reassigns its profiles to Unfiled rather than dropping them.
    r = client.post("/api/folders/delete", json={"name": "Marketing"}).json()
    assert "Marketing" not in r["folders"]
    after = {row["id"]: row for row in client.get("/api/profiles").json()}
    assert after[p["id"]]["folder"] == "Unfiled"
    assert len(after) == 1                          # profile survived the delete
