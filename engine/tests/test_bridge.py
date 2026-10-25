"""The local bridge that lets a browser use an authenticated SOCKS5 proxy.

A real (tiny) SOCKS5 server runs in-test, so the handshake, the credentials and
the remote-DNS behaviour are exercised for real — no mocks."""

import socket
import struct
import threading
import urllib.request

import pytest

from persona import bridge
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


def _recv(s, n):
    b = b""
    while len(b) < n:
        b += s.recv(n - len(b))
    return b


@pytest.fixture()
def origin():
    """A plain HTTP server that answers every request with its own request line."""
    def h(c):
        data = c.recv(4096)
        body = data.split(b"\r\n")[0]
        c.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\nConnection: close\r\n\r\n%s" % (len(body), body))
        c.close()
    srv, port = _serve(h)
    yield port
    srv.close()


@pytest.fixture()
def socks(origin):
    """A SOCKS5 server requiring user/pass that maps the name 'origin.test' to the
    origin server. It records the address it was asked for (to prove remote DNS)."""
    asked = []

    def h(c):
        try:
            ver, n = _recv(c, 2)
            methods = _recv(c, n)
            if 2 not in methods:
                c.sendall(b"\x05\xff"); c.close(); return
            c.sendall(b"\x05\x02")
            _recv(c, 1)
            user = _recv(c, _recv(c, 1)[0]).decode()
            pw = _recv(c, _recv(c, 1)[0]).decode()
            if (user, pw) != ("alice", "s3cret"):
                c.sendall(b"\x01\x01"); c.close(); return
            c.sendall(b"\x01\x00")
            _ver, _cmd, _rsv, atyp = _recv(c, 4)
            if atyp == 3:
                host = _recv(c, _recv(c, 1)[0]).decode()
            else:
                host = socket.inet_ntoa(_recv(c, 4))
            port = struct.unpack(">H", _recv(c, 2))[0]
            asked.append((atyp, host, port))
            target = ("127.0.0.1", origin) if host == "origin.test" else (host, port)
            up = socket.create_connection(target)
            c.sendall(b"\x05\x00\x00\x01" + b"\x00" * 6)
            bridge._pipe(c, up)
        except Exception:
            c.close()
    srv, port = _serve(h)
    yield port, asked
    srv.close()


def _fetch(bridge_url, url):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": bridge_url}))
    with opener.open(url, timeout=10) as r:
        return r.status, r.read().decode()


def test_only_authenticated_socks5_needs_a_bridge():
    assert bridge.needs_bridge(Proxy(server="socks5://h:1", username="u", password="p"))
    assert not bridge.needs_bridge(Proxy(server="socks5://h:1"))
    assert not bridge.needs_bridge(Proxy(server="http://h:1", username="u", password="p"))
    assert not bridge.needs_bridge(None)


def test_browser_gets_a_credential_free_loopback_proxy(socks):
    port, _ = socks
    px = Proxy(server=f"socks5://127.0.0.1:{port}", username="alice", password="s3cret", country="DE")
    out = bridge.browser_proxy(px)
    assert out.server.startswith("http://127.0.0.1:") and out.username is None
    assert out.country == "DE"
    assert bridge.browser_proxy(px).server == out.server          # one shared bridge


def test_http_through_bridge_with_remote_dns(socks):
    port, asked = socks
    b = bridge.bridge_for(Proxy(server=f"socks5://127.0.0.1:{port}", username="alice", password="s3cret"))
    status, body = _fetch(b.url, "http://origin.test/hello?x=1")
    assert status == 200 and body == "GET /hello?x=1 HTTP/1.1"
    # The hostname reached the SOCKS server unresolved (ATYP 3 = domain name).
    assert asked[-1] == (3, "origin.test", 80)


def test_connect_tunnel(socks):
    port, asked = socks
    b = bridge.bridge_for(Proxy(server=f"socks5://127.0.0.1:{port}", username="alice", password="s3cret"))
    c = socket.create_connection(("127.0.0.1", b.port))
    c.sendall(b"CONNECT origin.test:443 HTTP/1.1\r\nHost: origin.test:443\r\n\r\n")
    assert c.recv(100).startswith(b"HTTP/1.1 200")
    c.sendall(b"GET /tunnel HTTP/1.1\r\n\r\n")
    assert b"GET /tunnel" in c.recv(4096)
    assert asked[-1] == (3, "origin.test", 443)
    c.close()


def test_bad_credentials_surface_as_502(socks):
    port, _ = socks
    b = bridge.Bridge(Proxy(server=f"socks5://127.0.0.1:{port}", username="alice", password="nope"))
    with pytest.raises(urllib.error.HTTPError) as e:
        _fetch(b.url, "http://origin.test/")
    assert e.value.code == 502 and b"authentication failed" in e.value.read()
    b.close()
