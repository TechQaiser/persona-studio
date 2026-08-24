"""HTTP-surface tests: auth, config round-trip and the default extension set.

Unlike test_server.py these drive the real FastAPI app, so they need the
``api`` extra (plus httpx for the test client) and skip without it.
"""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from persona.server import create_app  # noqa: E402
from persona.store import ProfileStore  # noqa: E402


def client(tmp_path, token=None, monkeypatch=None):
    if monkeypatch is not None:
        if token:
            monkeypatch.setenv("PERSONA_API_TOKEN", token)
        else:
            monkeypatch.delenv("PERSONA_API_TOKEN", raising=False)
    return TestClient(create_app(str(tmp_path)))


# ---- authentication -----------------------------------------------------
# The API can create profiles, launch browsers and export cookies. Without a
# token it is only safe because it binds to localhost; anything reachable from
# elsewhere has to be able to demand one.

def test_no_token_configured_keeps_the_api_open(tmp_path, monkeypatch):
    c = client(tmp_path, token=None, monkeypatch=monkeypatch)
    assert c.get("/api/config").status_code == 200


def test_token_is_required_when_configured(tmp_path, monkeypatch):
    c = client(tmp_path, token="s3cret", monkeypatch=monkeypatch)
    assert c.get("/api/config").status_code == 401
    assert c.get("/api/config", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert c.get("/api/config", headers={"Authorization": "Bearer s3cret"}).status_code == 200
    assert c.get("/api/config", headers={"X-Persona-Token": "s3cret"}).status_code == 200


# ---- config -------------------------------------------------------------

def test_config_round_trips_the_new_settings(tmp_path, monkeypatch):
    c = client(tmp_path, token=None, monkeypatch=monkeypatch)
    body = c.put("/api/config", json={"default_extensions": ["/opt/ext/ublock"],
                                      "headless_launch": True}).json()
    assert body["default_extensions"] == ["/opt/ext/ublock"]
    assert body["headless_launch"] is True
    # Persisted, not just echoed back.
    assert ProfileStore(str(tmp_path)).get_default_extensions() == ["/opt/ext/ublock"]


# ---- the default extension set ------------------------------------------

def test_created_profiles_inherit_default_extensions(tmp_path, monkeypatch):
    c = client(tmp_path, token=None, monkeypatch=monkeypatch)
    c.put("/api/config", json={"default_extensions": ["/opt/ext/ublock"]})
    made = c.post("/api/profiles", json={"name": "inherits", "os": "Windows"}).json()
    assert made["extensions"] == "/opt/ext/ublock"


def test_an_explicit_extension_choice_wins(tmp_path, monkeypatch):
    c = client(tmp_path, token=None, monkeypatch=monkeypatch)
    c.put("/api/config", json={"default_extensions": ["/opt/ext/ublock"]})
    made = c.post("/api/profiles", json={"name": "explicit", "os": "Windows",
                                         "extensions": "/opt/ext/other"}).json()
    assert made["extensions"] == "/opt/ext/other"
