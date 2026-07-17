"""Outbound proxy support for the Peru pipeline (SEACE + OECE).

Azure's outbound IP range is blocked by both prod2.seace.gob.pe and
contratacionesabiertas.oece.gob.pe (confirmed: identical requests return 403
from Azure and 200 through a residential/datacenter proxy in Spain or
Poland). ``OUTBOUND_PROXY_URL`` routes both the ``requests``-based OCDS calls
and the Selenium-based SEACE scraper through that proxy. Leave it unset to
keep calling these hosts directly (e.g. from a machine that isn't blocked).

Chrome has no working command-line flag for an *authenticated* proxy: a
username/password embedded in ``--proxy-server`` is rejected outright
(``ERR_NO_SUPPORTED_PROXIES``), and without credentials the proxy's 407
challenge has no UI to answer in headless mode. ``selenium-wire`` is the
usual workaround, but its vendored mitmproxy TLS interception breaks against
current pyOpenSSL/cryptography releases. Since every target host here is
HTTPS, Chrome only ever needs a CONNECT tunnel through the proxy - it does
its own TLS to the real server once the tunnel is open. So instead of a
TLS-intercepting proxy, a tiny local relay forwards raw CONNECT tunnels to
the upstream proxy with the credentials injected, and Chrome talks to that
relay with no auth of its own.
"""

from __future__ import annotations

import base64
import os
import socket
import threading
from urllib.parse import urlsplit

PROXY_ENV_VAR = "OUTBOUND_PROXY_URL"

_relay_lock = threading.Lock()
_relay_ports: dict[str, int] = {}


def get_proxy_url() -> str:
    return os.getenv(PROXY_ENV_VAR, "").strip()


def requests_proxies() -> dict | None:
    url = get_proxy_url()
    return {"http": url, "https": url} if url else None


def _read_head(sock: socket.socket) -> bytes:
    data = b""
    while not data.endswith(b"\r\n\r\n"):
        chunk = sock.recv(1)
        if not chunk:
            break
        data += chunk
    return data


def _relay_bytes(src: socket.socket, dst: socket.socket) -> None:
    try:
        while True:
            chunk = src.recv(65536)
            if not chunk:
                break
            dst.sendall(chunk)
    except OSError:
        pass
    finally:
        try:
            dst.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def _handle_connection(client_sock: socket.socket, upstream_host: str, upstream_port: int, auth_header: str) -> None:
    upstream_sock = None
    try:
        head = _read_head(client_sock)
        if not head:
            return
        request_line, _, header_block = head.partition(b"\r\n")
        method, target, _version = request_line.decode("latin1").split(" ", 2)
        upstream_sock = socket.create_connection((upstream_host, upstream_port), timeout=20)
        if method.upper() == "CONNECT":
            upstream_sock.sendall(
                f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n"
                f"Proxy-Authorization: {auth_header}\r\nProxy-Connection: keep-alive\r\n\r\n".encode("latin1")
            )
            upstream_response = _read_head(upstream_sock)
            if not (upstream_response.startswith(b"HTTP/1.1 200") or upstream_response.startswith(b"HTTP/1.0 200")):
                client_sock.sendall(upstream_response or b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
                return
            client_sock.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        else:
            headers = [
                line
                for line in header_block.split(b"\r\n")
                if line and not line.lower().startswith(b"proxy-authorization:")
            ]
            headers.append(f"Proxy-Authorization: {auth_header}".encode("latin1"))
            upstream_sock.sendall(request_line + b"\r\n" + b"\r\n".join(headers) + b"\r\n\r\n")
        forward = threading.Thread(target=_relay_bytes, args=(client_sock, upstream_sock), daemon=True)
        backward = threading.Thread(target=_relay_bytes, args=(upstream_sock, client_sock), daemon=True)
        forward.start()
        backward.start()
        forward.join()
        backward.join()
    except Exception:
        pass
    finally:
        for sock in (client_sock, upstream_sock):
            try:
                if sock:
                    sock.close()
            except OSError:
                pass


def _serve(server_sock: socket.socket, upstream_host: str, upstream_port: int, auth_header: str) -> None:
    while True:
        try:
            client_sock, _ = server_sock.accept()
        except OSError:
            return
        threading.Thread(
            target=_handle_connection,
            args=(client_sock, upstream_host, upstream_port, auth_header),
            daemon=True,
        ).start()


def _get_relay_port(proxy_url: str) -> int:
    """Start (or reuse) a local unauthenticated relay in front of proxy_url."""
    with _relay_lock:
        cached = _relay_ports.get(proxy_url)
        if cached:
            return cached
        parts = urlsplit(proxy_url)
        credentials = f"{parts.username}:{parts.password}".encode()
        auth_header = "Basic " + base64.b64encode(credentials).decode()
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind(("127.0.0.1", 0))
        server_sock.listen(128)
        port = server_sock.getsockname()[1]
        threading.Thread(
            target=_serve,
            args=(server_sock, parts.hostname, parts.port, auth_header),
            daemon=True,
        ).start()
        _relay_ports[proxy_url] = port
        return port


def build_chrome_driver(options):
    """Return a Chrome WebDriver, routed through OUTBOUND_PROXY_URL if set."""
    from selenium import webdriver

    proxy_url = get_proxy_url()
    if not proxy_url:
        return webdriver.Chrome(options=options)

    parts = urlsplit(proxy_url)
    if parts.username and parts.password:
        local_port = _get_relay_port(proxy_url)
        options.add_argument(f"--proxy-server=http://127.0.0.1:{local_port}")
    else:
        options.add_argument(f"--proxy-server=http://{parts.hostname}:{parts.port}")
    return webdriver.Chrome(options=options)
