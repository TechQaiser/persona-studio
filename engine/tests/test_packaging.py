"""The packaged app: CLI re-invocation, serving the built dashboard, entry point."""

import sys

import pytest

from persona import runtime


def test_persona_cmd_from_source_and_frozen(monkeypatch):
    assert runtime.persona_cmd() == [sys.executable, "-m", "persona"]
    assert runtime.persona_cmd(unbuffered=True) == [sys.executable, "-u", "-m", "persona"]
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert runtime.persona_cmd(unbuffered=True) == [sys.executable]


def test_bundled_dashboard(tmp_path, monkeypatch):
    monkeypatch.delenv("PERSONA_DASHBOARD_DIR", raising=False)
    assert runtime.bundled_dashboard() is None
    monkeypatch.setenv("PERSONA_DASHBOARD_DIR", str(tmp_path))
    assert runtime.bundled_dashboard() is None              # no index.html yet
    (tmp_path / "index.html").write_text("<html></html>")
    assert runtime.bundled_dashboard() == tmp_path
    monkeypatch.delenv("PERSONA_DASHBOARD_DIR")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path.parent), raising=False)
    (tmp_path.parent / "dashboard").mkdir()
    (tmp_path.parent / "dashboard" / "index.html").write_text("x")
    assert runtime.bundled_dashboard() == tmp_path.parent / "dashboard"


def test_server_serves_the_dashboard_and_still_guards_the_api(tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from persona.server import TOKEN_HEADER, create_app

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>persona dashboard</html>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    own = "http://localhost:8787"
    app = create_app(str(tmp_path / "data"), start_scheduler=False,
                     extra_origins=[own], dashboard_dir=str(dist))
    c = TestClient(app, base_url="http://localhost:8787")

    assert "persona dashboard" in c.get("/").text
    assert c.get("/assets/app.js").text == "console.log(1)"
    assert c.get("/api/profiles").status_code == 401                 # API still locked
    token = c.get("/api/token").json()["token"]                      # same origin, no Origin
    assert c.get("/api/token", headers={"Origin": own}).status_code == 200
    assert c.get("/api/token", headers={"Origin": "https://evil.example"}).status_code == 403
    assert c.get("/api/profiles", headers={TOKEN_HEADER: token}).status_code == 200
    assert c.get("/", headers={"Host": "evil.example"}).status_code == 403   # rebinding


def test_no_dashboard_means_no_static_routes(tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from persona.server import create_app
    app = create_app(str(tmp_path), start_scheduler=False, dashboard_dir=str(tmp_path / "missing"))
    assert TestClient(app, base_url="http://localhost").get("/").status_code == 401


def test_app_with_arguments_is_the_cli(tmp_path, monkeypatch, capsys):
    from persona import app
    monkeypatch.setattr(sys, "argv", ["PersonaStudio.exe", "--data-dir", str(tmp_path), "list"])
    assert app.main() == 0


def test_sparse_profiles_get_every_field_the_dashboard_reads(tmp_path):
    # A profile posted with only a name used to blank the whole dashboard
    # (the list called p.tags.map on undefined).
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    import json
    from fastapi.testclient import TestClient
    from persona.server import TOKEN_HEADER, create_app
    app = create_app(str(tmp_path), start_scheduler=False)
    c = TestClient(app, base_url="http://localhost", headers={TOKEN_HEADER: app.state.api_token})
    made = c.post("/api/profiles", json={"name": "bare"}).json()
    for field in ("tags", "folder", "os", "screen", "userAgent", "webglRenderer", "locale", "storage"):
        assert made.get(field) is not None, field
    assert made["tags"] == [] and made["folder"] == "Unfiled"
    # and an old record missing tags still lists cleanly
    path = tmp_path / "dashboard" / f"{made['id']}.json"
    if path.exists():
        rec = json.loads(path.read_text())
        rec.pop("tags", None)
        path.write_text(json.dumps(rec))
        row = next(p for p in c.get("/api/profiles").json() if p["id"] == made["id"])
        assert row["tags"] == []
