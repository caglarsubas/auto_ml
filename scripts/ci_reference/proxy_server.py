"""Host-owned CONNECT allowlist reached only by explicit QEMU guest forwarding."""

import argparse, ipaddress, json, re, select, socket, socketserver, ssl, threading, time, urllib.request, urllib.parse
from pathlib import Path

MAX_HEADER = 16384
HOST = re.compile(r"(?=.{1,253}\Z)[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\Z")


def destination(raw, policy):
    if (
        len(raw) > MAX_HEADER
        or not raw.endswith(b"\r\n\r\n")
        or b"\r\n\r\n" in raw[:-4]
    ):
        raise ValueError("header")
    lines = raw[:-4].decode("ascii").split("\r\n")
    parts = lines[0].split(" ")
    if (
        len(parts) != 3
        or parts[0] != "CONNECT"
        or parts[2] not in {"HTTP/1.0", "HTTP/1.1"}
    ):
        raise ValueError("method")
    host, sep, port = parts[1].rpartition(":")
    host = host.lower()
    if not sep or port != "443" or not HOST.fullmatch(host) or ".." in host:
        raise ValueError("target")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("literal")
    if not any(
        host == h or h.startswith("*.") and host.endswith("." + h[2:]) and host != h[2:]
        for h in policy["hosts"]
    ):
        raise ValueError("host")
    seen = set()
    for line in lines[1:]:
        name, sep, val = line.partition(":")
        name = name.lower()
        if (
            not sep
            or not re.fullmatch("[a-z0-9-]+", name)
            or name in seen
            or any(ord(c) < 32 and c != "\t" or ord(c) > 126 for c in val)
        ):
            raise ValueError("header")
        seen.add(name)
        if (
            name == "transfer-encoding"
            or name == "content-length"
            and val.strip() != "0"
        ):
            raise ValueError("body")
    return host


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("resolver_redirect")


def doh_addresses(host, port, type=socket.SOCK_STREAM):
    # This resolver is fixed host-side, never selected by the guest. Local DNS
    # supplies synthetic benchmarking-range aliases here, not usable public IPs.
    url = "https://dns.google/resolve?" + urllib.parse.urlencode(
        {"name": host, "type": "A", "edns_client_subnet": "0.0.0.0/0"}
    )
    with urllib.request.build_opener(NoRedirect()).open(url, timeout=12) as response:
        raw = response.read(65537)
    if len(raw) > 65536:
        raise ValueError("resolver_size")
    value = json.loads(raw)
    if (
        value.get("Status") != 0
        or value.get("TC") is True
        or value.get("Question") != [{"name": host + ".", "type": 1}]
        and value.get("Question") != [{"name": host, "type": 1}]
    ):
        raise ValueError("resolver_answer")
    return [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", (row["data"], 443))
        for row in value.get("Answer", [])
        if row.get("type") == 1
    ]


def public_addresses(host, resolver=doh_addresses):
    values = resolver(host, 443, type=socket.SOCK_STREAM)
    if not values:
        raise ValueError("DNS")
    for row in values:
        address = ipaddress.ip_address(row[4][0])
        if not address.is_global or address.is_multicast or address.is_unspecified:
            raise ValueError("private_destination")
    return values


def connect_public(host):
    # Connect to the resolved numeric endpoint, never resolve the name again.
    for family, kind, protocol, _, address in public_addresses(host):
        stream = socket.socket(family, kind, protocol)
        stream.settimeout(15)
        try:
            stream.connect(address)
            return stream
        except OSError:
            stream.close()
    raise OSError("destination_unavailable")


def apt_request(raw, policy):
    """Translate one bodyless Debian package GET/HEAD to verified upstream TLS.

    Docker's unchanged Debian Dockerfile uses HTTP apt source URLs. This does
    not provide a general HTTP tunnel or permit guest-selected upstream ports.
    """
    if len(raw) > MAX_HEADER or not raw.endswith(b"\r\n\r\n") or b"\r\n\r\n" in raw[:-4]:
        raise ValueError("header")
    lines = raw[:-4].decode("ascii").split("\r\n")
    method, url, version = lines[0].split(" ")
    parsed = urllib.parse.urlsplit(url)
    if (method not in {"GET", "HEAD"} or version not in {"HTTP/1.0", "HTTP/1.1"}
        or parsed.scheme != "http" or parsed.netloc not in policy.get("apt_https_hosts", [])
        or parsed.username or parsed.password or parsed.fragment or not parsed.path.startswith("/")
        or any(ord(c) < 33 or ord(c) > 126 for c in url)):
        raise ValueError("apt_target")
    host = parsed.netloc
    destination(("CONNECT " + host + ":443 HTTP/1.1\r\n\r\n").encode(), policy)
    headers = []
    seen = set()
    for line in lines[1:]:
        name, sep, value = line.partition(":")
        key = name.lower()
        if (not sep or not re.fullmatch("[a-z0-9-]+", key) or key in seen
            or any(ord(c) < 32 and c != "\t" or ord(c) > 126 for c in value)
            or key in {"transfer-encoding", "authorization", "proxy-authorization", "upgrade"}
            or key == "content-length" and value.strip() != "0"
            or key == "host" and value.strip() != host):
            raise ValueError("apt_header")
        seen.add(key)
        if key not in {"host", "connection", "proxy-connection", "content-length"}:
            headers.append(line)
    path = parsed.path + ("?" + parsed.query if parsed.query else "")
    request = "\r\n".join([method + " " + path + " HTTP/1.1", "Host: " + host,
                            "Connection: close", *headers, "", ""]).encode("ascii")
    return host, request


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        remote = None
        try:
            self.request.settimeout(15)
            raw = b""
            while not raw.endswith(b"\r\n\r\n"):
                chunk = self.request.recv(min(4096, MAX_HEADER + 1 - len(raw)))
                if not chunk:
                    raise ValueError("header")
                raw += chunk
                if len(raw) > MAX_HEADER or b"\r\n\r\n" in raw[:-4]:
                    raise ValueError("header")
            apt = raw.startswith((b"GET ", b"HEAD "))
            host, request = apt_request(raw, self.server.policy) if apt else (destination(raw, self.server.policy), None)
            remote = connect_public(host)
            if apt:
                remote = ssl.create_default_context().wrap_socket(remote, server_hostname=host)
                remote.sendall(request)
            else:
                self.request.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            started = active = time.monotonic()
            size = 0
            while (
                time.monotonic() - started < 600
                and time.monotonic() - active < 120
                and size < 2**31
            ):
                ready, _, _ = ([remote], [], []) if apt and remote.pending() else select.select(
                    [remote] if apt else [self.request, remote],
                    [],
                    [],
                    min(10, 120 - (time.monotonic() - active)),
                )
                for source in ready:
                    data = source.recv(65536)
                    if not data:
                        return
                    (remote if source is self.request else self.request).sendall(data)
                    size += len(data)
                    active = time.monotonic()
        except (OSError, ValueError, UnicodeError):
            if remote is None:
                try:
                    self.request.sendall(
                        b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
                    )
                except OSError:
                    pass
        finally:
            if remote is not None:
                remote.close()


class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    block_on_close = False
    request_queue_size = 32

    def __init__(self, path, policy):
        self.policy = policy
        self.slots = threading.BoundedSemaphore(16)
        super().__init__(path, Handler)

    def process_request(self, request, address):
        if not self.slots.acquire(False):
            request.close()
            return
        try:
            super().process_request(request, address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()


if __name__ == "__main__":
    import os

    p = argparse.ArgumentParser()
    p.add_argument("--socket", required=True)
    p.add_argument("--policy", required=True)
    a = p.parse_args()
    policy = json.loads(Path(a.policy).read_text())
    assert policy["ports"] == [443] and policy["max_connections"] == 16
    with Server(a.socket, policy) as server:
        os.chmod(a.socket, 0o600)
        server.serve_forever(poll_interval=0.5)
