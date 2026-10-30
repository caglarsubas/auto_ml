import ipaddress, socket, tempfile, threading, unittest
from pathlib import Path
from unittest.mock import patch
import proxy_server as p

POLICY = {
    "hosts": ["github.com", "*.actions.githubusercontent.com"],
    "ports": [443],
    "max_connections": 16,
}


class ProxyTests(unittest.TestCase):
    def test_debian_package_HTTP_is_single_request_to_TLS_origin(self):
        policy = {**POLICY, "hosts": [*POLICY["hosts"], "deb.debian.org"], "apt_https_hosts": ["deb.debian.org"]}
        host, request = p.apt_request(b"GET http://deb.debian.org/debian/dists/stable/InRelease HTTP/1.1\r\nHost: deb.debian.org\r\nProxy-Connection: keep-alive\r\n\r\n", policy)
        self.assertEqual(host, "deb.debian.org")
        self.assertIn(b"GET /debian/dists/stable/InRelease HTTP/1.1\r\n", request)
        self.assertIn(b"Connection: close\r\n", request)
        self.assertNotIn(b"Proxy-Connection", request)
        for url in ["http://127.0.0.1/a", "http://deb.debian.org:80/a", "http://evil.invalid/a", "http://x@deb.debian.org/a", "https://deb.debian.org/a", "http://deb.debian.org/a#fragment"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                p.apt_request(("GET "+url+" HTTP/1.1\r\n\r\n").encode(), policy)
        for header in ["Host: other.invalid", "Authorization: secret", "Transfer-Encoding: chunked", "Content-Length: 4", "X: a\r\nX: b"]:
            with self.subTest(header=header), self.assertRaises(ValueError):
                p.apt_request(("GET http://deb.debian.org/debian/ HTTP/1.1\r\n"+header+"\r\n\r\n").encode(), policy)

    def test_exact_and_suffix(self):
        for host in ["github.com", "pipe.actions.githubusercontent.com"]:
            self.assertEqual(
                p.destination(
                    f"CONNECT {host}:443 HTTP/1.1\r\nHost: {host}\r\n\r\n".encode(),
                    POLICY,
                ),
                host,
            )

    def test_reject_targets_methods_and_spoofing(self):
        for target in [
            "127.0.0.1:443",
            "[::1]:443",
            "github.com:80",
            "github.com:0443",
            "github.com.:443",
            "github.com.evil.invalid:443",
            "user@github.com:443",
            "github.com/path:443",
            "foo..actions.githubusercontent.com:443",
            "actions.githubusercontent.com:443",
        ]:
            with self.subTest(target=target), self.assertRaises(ValueError):
                p.destination(f"CONNECT {target} HTTP/1.1\r\n\r\n".encode(), POLICY)
        with self.assertRaises(ValueError):
            p.destination(b"GET https://github.com/ HTTP/1.1\r\n\r\n", POLICY)

    def test_headers_and_body_fences(self):
        for tail in [
            "Content-Length: 1",
            "Transfer-Encoding: chunked",
            "Host: a\r\nHost: b",
            "X: \x00",
            "X: \x01",
            "bad header",
        ]:
            with self.subTest(tail=tail), self.assertRaises(ValueError):
                p.destination(
                    (
                        "CONNECT github.com:443 HTTP/1.1\r\n" + tail + "\r\n\r\n"
                    ).encode(),
                    POLICY,
                )
        for raw in [b"CONNECT github.com:443 HTTP/1.1\r\n\r\nextra", b"X" * 16385]:
            with self.assertRaises(ValueError):
                p.destination(raw, POLICY)

    def test_private_rebinding_and_nonpublic_IPs(self):
        for ip in [
            "127.0.0.1",
            "10.0.0.1",
            "169.254.169.254",
            "192.168.1.1",
            "100.64.0.1",
            "::1",
            "fc00::1",
            "::ffff:127.0.0.1",
            "224.0.0.1",
        ]:

            def resolver(*a, **kw):
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))]

            with self.subTest(ip=ip), self.assertRaises(ValueError):
                p.public_addresses("github.com", resolver)

        def mixed(*a, **kw):
            return [(2, 1, 6, "", ("1.1.1.1", 443)), (2, 1, 6, "", ("10.0.0.1", 443))]

        with self.assertRaises(ValueError):
            p.public_addresses("github.com", mixed)

    def test_DOH_fixed_public_resolver_and_no_redirects(self):
        import io, json

        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                self.close()

        class Opener:
            def open(self, url, timeout):
                self.url = url
                return Response(
                    json.dumps(
                        {
                            "Status": 0,
                            "Question": [{"name": "github.com.", "type": 1}],
                            "Answer": [{"type": 1, "data": "1.1.1.1"}],
                        }
                    ).encode()
                )

        opener = Opener()
        with patch.object(p.urllib.request, "build_opener", return_value=opener):
            rows = p.doh_addresses("github.com", 443)
        self.assertTrue(opener.url.startswith("https://dns.google/resolve?"))
        self.assertIn("edns_client_subnet=0.0.0.0%2F0", opener.url)
        self.assertEqual(rows[0][4], ("1.1.1.1", 443))
        with self.assertRaises(ValueError):
            p.NoRedirect().redirect_request(None, None, None, None, None, None)

    def test_connect_uses_checked_numeric_endpoint(self):
        class Stream:
            def settimeout(self, v):
                pass

            def connect(self, a):
                self.endpoint = a

        s = Stream()
        with (
            patch.object(
                p, "public_addresses", return_value=[(2, 1, 6, "", ("1.1.1.1", 443))]
            ),
            patch.object(p.socket, "socket", return_value=s),
        ):
            self.assertIs(p.connect_public("github.com"), s)
        self.assertEqual(s.endpoint, ("1.1.1.1", 443))

    def test_live_unix_request_denied_without_destination_IO(self):
        with tempfile.TemporaryDirectory(prefix="p162-proxy-") as d:
            path = str(Path(d) / "proxy.sock")
            with p.Server(path, POLICY) as srv:
                thread = threading.Thread(target=srv.serve_forever, daemon=True)
                thread.start()
                with patch.object(
                    p, "connect_public", side_effect=AssertionError("must not connect")
                ):
                    c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    c.settimeout(3)
                    c.connect(path)
                    c.sendall(b"CONNECT unauthorized.invalid:443 HTTP/1.1\r\n\r\n")
                    self.assertTrue(c.recv(1024).startswith(b"HTTP/1.1 403"))
                    c.close()
                srv.shutdown()
                thread.join(3)


if __name__ == "__main__":
    unittest.main()
