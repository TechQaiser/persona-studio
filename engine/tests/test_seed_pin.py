"""Dashboard profiles keep one seed, so every launch is the same device.

The seed drives canvas/audio noise (and seeds the engines' pinned identities).
Profiles saved without one used to get a fresh random seed on every launch,
which made each session look like a new device."""

import json

import pytest

from persona.server import DashboardStore, to_engine_profile

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from persona.server import TOKEN_HEADER, create_app  # noqa: E402
from persona.store import ProfileStore  # noqa: E402


class FakeProc:
    """Stands in for the launcher subprocess: it has already exited cleanly."""
    pid = 999999
    returncode = 0

    def __init__(self, *a, **kw):
        pass

    def poll(self):
        return 0


def test_store_gives_a_profile_a_seed_once(tmp_path):
    dash = DashboardStore(tmp_path)
    d = dash.save({"name": "a"})
    seed = d["seed"]
    assert isinstance(seed, int) and seed > 0
    assert dash.save(dash.get(d["id"]))["seed"] == seed
    # The same stored profile converts to the same device every time.
    assert to_engine_profile(dash.get(d["id"])).fingerprint.seed == seed
    assert to_engine_profile(dash.get(d["id"])).fingerprint.seed == seed


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("persona.server.subprocess.Popen", FakeProc)
    app = create_app(str(tmp_path), start_scheduler=False)
    return TestClient(app, base_url="http://localhost",
                      headers={TOKEN_HEADER: app.state.api_token})


def test_old_profile_without_a_seed_launches_as_one_device(tmp_path, client):
    # A profile saved by an older version: no seed on disk.
    pid = "0ld0ld0ld0ld"
    (tmp_path / "dashboard" / f"{pid}.json").write_text(json.dumps(
        {"id": pid, "name": "old", "os": "Windows", "tags": []}), encoding="utf-8")
    engine = ProfileStore(tmp_path)

    assert client.post(f"/api/profiles/{pid}/launch").status_code == 200
    first = engine.get(pid).fingerprint.seed
    stored = DashboardStore(tmp_path).get(pid)["seed"]
    assert first == stored

    assert client.post(f"/api/profiles/{pid}/launch").status_code == 200
    assert engine.get(pid).fingerprint.seed == first


def test_saving_a_copy_without_the_seed_keeps_the_stored_one(client):
    created = client.post("/api/profiles", json={"name": "x", "os": "Windows"}).json()
    seed = created["seed"]
    stale = {k: v for k, v in created.items() if k != "seed"}
    stale["notes"] = "edited"
    updated = client.put(f"/api/profiles/{created['id']}", json=stale).json()
    assert updated["seed"] == seed and updated["notes"] == "edited"


def test_bulk_created_profiles_each_get_their_own_seed(client):
    res = client.post("/api/profiles/batch",
                      json={"profiles": [{"name": f"b{i}", "os": "Windows"} for i in range(5)]})
    seeds = {p["seed"] for p in client.get("/api/profiles").json() if p["id"] in res.json()["ids"]}
    assert len(seeds) == 5
