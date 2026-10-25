"""Proxy quality-of-life: SOCKS4 through the bridge, change-IP URLs, pasted formats."""

import http.server
import socket
import struct
import threading
import urllib.request

import pytest

from persona import bridge, proxypool
from persona.models import Proxy


def _serve(handler):
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(20)

    def loop():
        while True:
            try:
                c, _ = srv.accept()
            except OSError:
                return
            threading.Thread(target=handler, args=(c,), daemon=True).start()
    threading.Thread(target=loop, daemon=True).start()
    return srv, srv.getsockname()[1]


def _recv_until(s, end=b"\x00"):
    b = b""
    while not b.endswith(end):
        b += s.recv(1)
    return b[:-1]


@pytest.fixture()
def origin():
    """A plain TCP 'website' that answers one HTTP request."""
    def handle(c):
        c.recv(65536)
        c.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\nConnection: close\r\n\r\nhello")
        c.close()
    srv, port = _serve(handle)
    yield port
    srv.close()


@pytest.fixture()
def socks4(origin):
    """A real SOCKS4/4a server that records what it was asked for."""
    seen = {}

    def handle(c):
        head = c.recv(8)
        vn, cd, port = head[0], head[1], struct.unpack(">H", head[2:4])[0]
        ip = socket.inet_ntoa(head[4:8])
        seen["user"] = _recv_until(c).decode()
        host = _recv_until(c).decode() if ip.startswith("0.0.0.") else ip
        seen.update(vn=vn, cd=cd, host=host, port=port)
        up = socket.create_connection(("127.0.0.1", origin))
        c.sendall(b"\x00\x5a" + b"\x00" * 6)
        bridge._pipe(c, up)
    srv, port = _serve(handle)
    yield port, seen
    srv.close()


def test_socks4_always_needs_the_bridge():
    assert bridge.needs_bridge(Proxy(server="socks4://h:1"))
    assert bridge.needs_bridge(Proxy(server="socks5://h:1", username="u"))
    assert not bridge.needs_bridge(Proxy(server="socks5://h:1"))
    assert not bridge.needs_bridge(Proxy(server="http://h:1", username="u"))


def test_socks4a_resolves_hostnames_at_the_proxy(socks4, origin):
    port, seen = socks4
    b = bridge.bridge_for(Proxy(server=f"socks4://127.0.0.1:{port}", username="me"))
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": b.url}))
    with opener.open(f"http://site.example:{origin}/", timeout=10) as r:
        assert r.read() == b"hello"
    assert seen == {"vn": 4, "cd": 1, "host": "site.example", "port": origin, "user": "me"}


def test_pool_check_handles_socks4(socks4, monkeypatch, origin):
    port, _ = socks4
    monkeypatch.setattr(proxypool, "_ECHO", [f"http://127.0.0.1:{origin}/"])
    res = proxypool.check({"type": "SOCKS4", "host": "127.0.0.1", "port": port})
    assert res["ok"] is True and res["ip"] == "hello"


# ---- change-IP URL -------------------------------------------------------------

@pytest.fixture()
def vendor():
    calls = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append(self.path)
            code = 500 if "fail" in self.path else 200
            body = b'{"new_ip": "203.0.113.9"}'
            self.send_response(code)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}", calls
    srv.shutdown()


def test_change_ip_calls_the_vendor_and_clears_the_geo_cache(vendor, monkeypatch):
    from persona import geo
    url, calls = vendor
    geo._cache[("x",)] = (0, {"ip": "old"})
    res = proxypool.change_ip(url + "/rotate?key=1")
    assert res == {"ok": True, "status": 200, "body": '{"new_ip": "203.0.113.9"}'}
    assert calls == ["/rotate?key=1"]
    assert geo._cache == {}


def test_change_ip_reports_failures(vendor):
    url, _ = vendor
    assert proxypool.change_ip(url + "/fail")["ok"] is False
    assert proxypool.change_ip("file:///etc/passwd")["ok"] is False
    assert proxypool.change_ip("")["ok"] is False


def test_change_ip_url_round_trips():
    from persona.server import to_dashboard_profile, to_engine_profile
    d = {"id": "a", "name": "x", "os": "Windows",
         "proxy": {"type": "SOCKS4", "host": "h", "port": "1080", "user": "", "pass": "",
                   "country": "US", "changeIpUrl": " https://v.example/r "}}
    prof = to_engine_profile(d)
    assert prof.proxy.server == "socks4://h:1080"
    assert prof.proxy.change_ip_url == "https://v.example/r"
    back = to_dashboard_profile(prof)["proxy"]
    assert back["type"] == "SOCKS4" and back["changeIpUrl"] == "https://v.example/r"
    # proxies saved before the field existed still load
    assert Proxy.from_dict({"server": "http://h:1", "unknown": 1}).change_ip_url is None


def test_api_change_ip(tmp_path, vendor):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from persona.server import TOKEN_HEADER, create_app
    url, calls = vendor
    app = create_app(str(tmp_path), start_scheduler=False)
    c = TestClient(app, base_url="http://localhost", headers={TOKEN_HEADER: app.state.api_token})
    pid = c.post("/api/profiles", json={"name": "x", "os": "Windows", "proxy": {
        "type": "HTTP", "host": "h", "port": "1", "changeIpUrl": url + "/r"}}).json()["id"]
    assert c.post(f"/api/profiles/{pid}/proxy/change-ip").json()["ok"] is True
    bare = c.post("/api/profiles", json={"name": "y", "os": "Windows"}).json()["id"]
    assert c.post(f"/api/profiles/{bare}/proxy/change-ip").status_code == 400

    pool_id = c.post("/api/proxies", json={"text": "1.2.3.4:8080"}).json()["proxies"][0]["id"]
    assert c.post(f"/api/proxies/{pool_id}/change-ip").status_code == 400
    assert c.put(f"/api/proxies/{pool_id}", json={"changeIpUrl": url + "/p"}).json()["changeIpUrl"]
    assert c.post(f"/api/proxies/{pool_id}/change-ip").json()["ok"] is True
    assert calls == ["/r", "/p"]


# ---- pasted formats --------------------------------------------------------------

def test_cli_accepts_every_pasted_format():
    from persona.cli import _parse_proxy
    p = _parse_proxy("1.2.3.4:8080:alice:s3cret", None)
    assert (p.server, p.username, p.password) == ("http://1.2.3.4:8080", "alice", "s3cret")
    p = _parse_proxy("socks5://bob:pw@h.example:1080", "DE")
    assert (p.server, p.username, p.country) == ("socks5://h.example:1080", "bob", "DE")
    assert _parse_proxy("socks4://h:1080", None).server == "socks4://h:1080"
    assert _parse_proxy("h:3128:US", None).country == "US"
    with pytest.raises(RuntimeError):
        _parse_proxy("not a proxy", None)
