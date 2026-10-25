"""Engine setup: progress reporting for the one-time browser downloads."""

import json
import logging
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from persona import engines


def test_emit_and_read_progress(tmp_path, capsys):
    engines.emit("cloak", "download", 10, 100)
    line = capsys.readouterr().out.strip()
    assert line.startswith(engines.PROGRESS_TAG)
    log = tmp_path / "x.log"
    log.write_text("Launching...\n" + line + "\nsomething else\n"
                   + engines.PROGRESS_TAG + '{"engine": "cloak", "stage": "extract", "done": 100, "total": 100}\n')
    assert engines.read_progress(log)["stage"] == "extract"
    assert engines.read_progress(tmp_path / "missing.log") is None
    (tmp_path / "plain.log").write_text("no progress here\n")
    assert engines.read_progress(tmp_path / "plain.log") is None


def test_cloak_watcher_turns_its_log_into_progress(capsys):
    log = logging.getLogger("cloakbrowser")
    tmp = Path(tempfile.gettempdir()) / f"tmp{time.time_ns()}test.zip"
    try:
        with engines.cloak_progress():
            log.info("Downloading from %s", "https://example/cloak.zip")
            log.info("Download progress: %d%% (%d/%d MB)", 0, 0, 2)
            tmp.write_bytes(b"x" * 1024 * 1024)          # the archive being written
            time.sleep(1.6)                               # one heartbeat
            log.info("Extracting to %s", "C:/x")
            log.info("Binary ready: %s", "C:/x/chrome.exe")
    finally:
        tmp.unlink(missing_ok=True)
    recs = [json.loads(l[len(engines.PROGRESS_TAG):]) for l in capsys.readouterr().out.splitlines()
            if l.startswith(engines.PROGRESS_TAG)]
    downloads = [r for r in recs if r["stage"] == "download"]
    assert downloads and downloads[-1]["total"] == 2 * 1024 * 1024
    assert downloads[-1]["done"] >= 1024 * 1024
    assert [r["stage"] for r in recs][-2:] == ["extract", "done"]


def test_cloak_progress_reports_a_failed_download(capsys):
    log = logging.getLogger("cloakbrowser")
    with pytest.raises(OSError):
        with engines.cloak_progress():
            log.info("Downloading from %s", "https://example/cloak.zip")
            raise OSError("connection reset")
    last = [l for l in capsys.readouterr().out.splitlines() if l.startswith(engines.PROGRESS_TAG)][-1]
    rec = json.loads(last[len(engines.PROGRESS_TAG):])
    assert rec["stage"] == "error" and "connection reset" in rec["error"]


def test_status_shape():
    st = engines.status()
    assert {"playwright", "cloak"} <= set(st)
    for s in st.values():
        assert set(s) == {"installed", "ready", "downloadMB"}
        assert s["downloadMB"] == 0 or not s["ready"]


def test_install_rejects_engines_with_nothing_to_download():
    with pytest.raises(RuntimeError):
        engines.install("camoufox")


# ---- dashboard API ----------------------------------------------------------------

FAKE_INSTALL = (
    "import json, sys, time\n"
    "for i in range(0, 101, 25):\n"
    "    print('PERSONA_PROGRESS ' + json.dumps({'engine': 'cloak', 'stage': 'download',"
    " 'done': i, 'total': 100}), flush=True); time.sleep(0.3)\n"
    "print('PERSONA_PROGRESS ' + json.dumps({'engine': 'cloak', 'stage': 'done', 'done': 100, 'total': 100}), flush=True)\n"
)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from persona import drivers, server
    monkeypatch.setattr(drivers, "is_installed", lambda name: True)
    monkeypatch.setattr(engines, "cloak_ready", lambda: False)
    monkeypatch.setattr(server, "persona_cmd", lambda unbuffered=False: [sys.executable, "-c", FAKE_INSTALL])
    app = server.create_app(str(tmp_path), start_scheduler=False)
    return TestClient(app, base_url="http://localhost", headers={server.TOKEN_HEADER: app.state.api_token})


def test_engine_install_job_reports_progress_and_blocks_racing_launches(client):
    st = client.get("/api/engines/status").json()["cloak"]
    assert st["ready"] is False and st["installing"] is False and st["downloadMB"] > 0

    started = client.post("/api/engines/cloak/install").json()
    assert started["installing"] is True
    again = client.post("/api/engines/cloak/install").json()   # no second download
    assert again["installing"] is True

    pid = client.post("/api/profiles", json={"name": "c", "os": "Windows", "engine": "cloak"}).json()["id"]
    r = client.post(f"/api/profiles/{pid}/launch")
    assert r.status_code == 409 and "still downloading" in r.json()["detail"]

    seen = []
    for _ in range(40):
        st = client.get("/api/engines/status").json()["cloak"]
        if st["progress"]:
            seen.append(st["progress"]["stage"])
        if not st["installing"]:
            break
        time.sleep(0.25)
    assert "download" in seen and st["progress"]["stage"] == "done" and st["failed"] is False


def test_unknown_engine_install_is_404(client):
    assert client.post("/api/engines/nope/install").status_code == 404


def test_launch_progress_is_reported_on_the_profile(client, tmp_path, monkeypatch):
    from persona import server
    pid = client.post("/api/profiles", json={"name": "c", "os": "Windows", "engine": "playwright"}).json()["id"]
    slow = ("import json, time\n"
            "print('PERSONA_PROGRESS ' + json.dumps({'engine': 'cloak', 'stage': 'download',"
            " 'done': 5, 'total': 10}), flush=True)\n"
            "time.sleep(30)\n")
    real = subprocess.Popen
    monkeypatch.setattr(server.subprocess, "Popen",
                        lambda *a, **k: real([sys.executable, "-c", slow],
                                             stdout=k.get("stdout"), stderr=k.get("stderr")))
    client.post(f"/api/profiles/{pid}/launch")
    for _ in range(40):
        row = next(p for p in client.get("/api/profiles").json() if p["id"] == pid)
        if row.get("launchProgress"):
            break
        time.sleep(0.25)
    assert row["launchProgress"]["done"] == 5 and row["launchProgress"]["total"] == 10
    client.post(f"/api/profiles/{pid}/stop")
