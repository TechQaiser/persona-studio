"""Local-API hardening: token, CORS allowlist and Host-header (DNS rebinding) checks.

A web page open in the user's everyday browser can reach localhost, so the API
must not answer it. Skipped cleanly when FastAPI isn't installed."""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from persona.server import TOKEN_FILE, TOKEN_HEADER, _host_name, create_app

DASH = "http://localhost:5173"
EVIL = "https://evil.example"


@pytest.fixture()
def app(tmp_path):
    return create_app(str(tmp_path), start_scheduler=False)


@pytest.fixture()
def anon(app):
    return TestClient(app, base_url="http://localhost")


def test_api_requires_token(anon, app):
    assert anon.get("/api/profiles").status_code == 401
    assert anon.get("/api/profiles", headers={TOKEN_HEADER: "wrong"}).status_code == 401
    ok = anon.get("/api/profiles", headers={TOKEN_HEADER: app.state.api_token})
    assert ok.status_code == 200


def test_mutations_blocked_without_token(anon):
    assert anon.post("/api/profiles", json={"name": "x"}).status_code == 401
    assert anon.post("/api/profiles/any/launch").status_code == 401
    assert anon.get("/api/profiles/any/cookies").status_code == 401


def test_health_stays_open(anon):
    assert anon.get("/api/health").json()["ok"] is True


def test_token_given_to_dashboard_origin_only(anon, app):
    r = anon.get("/api/token", headers={"Origin": DASH})
    assert r.status_code == 200 and r.json()["token"] == app.state.api_token
    assert r.headers["access-control-allow-origin"] == DASH
    assert anon.get("/api/token", headers={"Origin": EVIL}).status_code == 403


def test_token_written_to_data_dir(tmp_path, app):
    assert (tmp_path / TOKEN_FILE).read_text(encoding="utf-8") == app.state.api_token


def test_token_is_fresh_per_start(tmp_path):
    a = create_app(str(tmp_path), start_scheduler=False).state.api_token
    b = create_app(str(tmp_path), start_scheduler=False).state.api_token
    assert a != b and len(a) >= 32


def test_cors_rejects_foreign_origin(anon):
    pre = {"Origin": EVIL, "Access-Control-Request-Method": "POST",
           "Access-Control-Request-Headers": TOKEN_HEADER}
    r = anon.options("/api/profiles", headers=pre)
    assert r.headers.get("access-control-allow-origin") != EVIL
    pre["Origin"] = DASH
    r = anon.options("/api/profiles", headers=pre)
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] == DASH


def test_dns_rebinding_host_rejected(app):
    rebound = TestClient(app, base_url="http://evil.example:8787",
                         headers={TOKEN_HEADER: app.state.api_token})
    assert rebound.get("/api/profiles").status_code == 403
    assert rebound.get("/api/token").status_code == 403


def test_extra_origins_and_hosts(tmp_path, monkeypatch):
    monkeypatch.setenv("PERSONA_ALLOWED_ORIGINS", "http://studio.lan:5173")
    app = create_app(str(tmp_path), start_scheduler=False, extra_hosts=["studio.lan"])
    c = TestClient(app, base_url="http://studio.lan:8787")
    assert c.get("/api/token", headers={"Origin": "http://studio.lan:5173"}).status_code == 200


def test_fixed_token_via_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PERSONA_API_TOKEN", "pinned-token")
    assert create_app(str(tmp_path), start_scheduler=False).state.api_token == "pinned-token"


def test_host_name_parsing():
    assert _host_name("localhost:8787") == "localhost"
    assert _host_name("127.0.0.1") == "127.0.0.1"
    assert _host_name("[::1]:8787") == "[::1]"
    assert _host_name("[::1]") == "[::1]"
