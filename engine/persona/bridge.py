"""
Local proxy bridge for authenticated SOCKS5 upstreams (GoLogin's "gproxy").

Chromium (and Playwright's Firefox) can't send a username/password to a SOCKS5
proxy, so a profile with ``socks5://user:pass@host`` used to fail at launch. The
bridge is a tiny HTTP proxy on ``127.0.0.1:<random port>``: the browser talks
plain HTTP-proxy to it (no credentials), and it opens each connection through
the real SOCKS5 server with the credentials.

Hostnames are handed to the SOCKS server unresolved (ATYP=domain), so name
lookups happen at the proxy's end — no DNS leak from this machine. One bridge
serves every launch that uses the same upstream; it's a daemon thread that lives
as long as the process does. It only listens on loopback.
"""

from __future__ import annotations

import ipaddress
import select
import socket
import struct
import threading
from dataclasses import replace
from typing import Optional
from urllib.parse import urlsplit

from .models import Proxy

_bridges: dict[tuple, "Bridge"] = {}
_lock = threading.Lock()


def needs_bridge(proxy: Optional[Proxy]) -> bool:
    """SOCKS5 with credentials is the one case browsers can't do natively."""
    return bool(proxy and proxy.username
                and proxy.server.lower().split("://", 1)[0] in ("socks5", "socks5h"))


def socks5_connect(upstream: tuple[str, int], user: str, password: str,
                   host: str, port: int, timeout: float = 20) -> socket.socket:
    """Open a TCP connection to host:port through a SOCKS5 server (RFC 1928/1929)."""
    s = socket.create_connection(upstream, timeout=timeout)
    try:
        want = 2 if user else 0                         # user/pass, or no auth
        s.sendall(b"\x05\x01" + bytes([want]))
        ver, method = _recv(s, 2)
        if ver != 5 or method != want:
            raise ConnectionError("SOCKS5 server refused " + (
                "username/password auth" if user else "unauthenticated access"))
        if user:
            u, p = user.encode(), password.encode()
            s.sendall(b"\x01" + bytes([len(u)]) + u + bytes([len(p)]) + p)
            if _recv(s, 2)[1] != 0:
                raise ConnectionError("SOCKS5 authentication failed (check the proxy's username/password)")
        try:
            ip = ipaddress.ip_address(host)
            addr = (b"\x01" if ip.version == 4 else b"\x04") + ip.packed
        except ValueError:                               # a hostname: resolve remotely
            h = host.encode("idna")
            addr = b"\x03" + bytes([len(h)]) + h
        s.sendall(b"\x05\x01\x00" + addr + struct.pack(">H", port))
        ver, rep, _rsv, atyp = _recv(s, 4)
        if rep != 0:
            raise ConnectionError(f"SOCKS5 connect to {host}:{port} failed (code {rep})")
        _recv(s, {1: 4, 4: 16}.get(atyp) or _recv(s, 1)[0])   # bound address
        _recv(s, 2)                                            # bound port
        s.settimeout(None)
        return s
    except Exception:
        s.close()
        raise


def _recv(s: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = s.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("SOCKS5 server closed the connection")
        buf += chunk
    return buf


def _pipe(a: socket.socket, b: socket.socket) -> None:
    try:
        while True:
            ready, _, _ = select.select([a, b], [], [], 300)
            if not ready:
                return
            for s in ready:
                data = s.recv(65536)
                if not data:
                    return
                (b if s is a else a).sendall(data)
    except OSError:
        pass
    finally:
        for s in (a, b):
            try:
                s.close()
            except OSError:
                pass


class Bridge:
    """A loopback HTTP proxy forwarding through one authenticated SOCKS5 server."""

    def __init__(self, proxy: Proxy):
        u = urlsplit(proxy.server)
        self.upstream = (u.hostname, u.port or 1080)
        self.user, self.password = proxy.username or "", proxy.password or ""
        self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv.bind(("127.0.0.1", 0))
        self._srv.listen(128)
        self.port = self._srv.getsockname()[1]
        threading.Thread(target=self._serve, name=f"persona-bridge-{self.port}",
                         daemon=True).start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def _serve(self) -> None:
        while True:
            try:
                client, _ = self._srv.accept()
            except OSError:
                return                       # closed
            threading.Thread(target=self._handle, args=(client,), daemon=True).start()

    def _handle(self, client: socket.socket) -> None:
        try:
            head = b""
            while b"\r\n\r\n" not in head:
                chunk = client.recv(8192)
                if not chunk:
                    client.close()
                    return
                head += chunk
                if len(head) > 65536:
                    raise ConnectionError("request head too large")
            line, _, rest = head.partition(b"\r\n")
            method, target, version = line.decode("latin-1").split(" ", 2)
            if method.upper() == "CONNECT":                      # HTTPS / WSS
                host, _, port = target.rpartition(":")
                up = socks5_connect(self.upstream, self.user, self.password,
                                    host.strip("[]"), int(port))
                client.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
                leftover = head.split(b"\r\n\r\n", 1)[1]
                if leftover:
                    up.sendall(leftover)
            else:                                                # plain HTTP
                u = urlsplit(target)
                up = socks5_connect(self.upstream, self.user, self.password,
                                    u.hostname, u.port or 80)
                path = (u.path or "/") + (f"?{u.query}" if u.query else "")
                up.sendall(f"{method} {path} {version}\r\n".encode("latin-1") + rest)
            _pipe(client, up)
        except Exception as e:  # noqa: BLE001 - tell the browser, don't crash the bridge
            try:
                msg = str(e).splitlines()[0][:200].encode("latin-1", "replace")
                client.sendall(b"HTTP/1.1 502 Bad Gateway\r\nContent-Type: text/plain\r\n"
                               b"Content-Length: " + str(len(msg)).encode() + b"\r\n\r\n" + msg)
            except OSError:
                pass
            client.close()

    def close(self) -> None:
        self._srv.close()


def bridge_for(proxy: Proxy) -> Bridge:
    """The (shared) bridge for this upstream, started on first use."""
    key = (proxy.server, proxy.username, proxy.password)
    with _lock:
        b = _bridges.get(key)
        if b is None:
            b = _bridges[key] = Bridge(proxy)
        return b


def browser_proxy(proxy: Optional[Proxy]) -> Optional[Proxy]:
    """The proxy to hand the browser: the original, or a credential-free
    loopback bridge when the browser couldn't use it directly. The country is
    kept so geo alignment still knows where the proxy claims to be."""
    if not needs_bridge(proxy):
        return proxy
    return replace(proxy, server=bridge_for(proxy).url, username=None, password=None)
