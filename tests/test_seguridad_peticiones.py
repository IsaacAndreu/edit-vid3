"""Anyone without a password can neither exhaust the studio nor lock the owner out."""

from __future__ import annotations

import http.client
import json
import threading
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import pytest

from pipeline import web
from tests.test_web import _project


@pytest.fixture
def server(tmp_path):
    _project(tmp_path)
    with patch("time.sleep", lambda s: None):
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), web.make_handler(tmp_path, "clave"))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        yield httpd.server_address[1]
        httpd.shutdown()
        httpd.server_close()


def _post(port, path, body: bytes, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.putrequest("POST", path)
    for k, v in (headers or {}).items():
        conn.putheader(k, v)
    conn.endheaders()
    if body:
        conn.send(body)
    response = conn.getresponse()
    return response.status, response.read()


def test_a_huge_or_negative_body_is_refused_before_reading(server):
    status, _ = _post(server, "/api/login", b"", {"Content-Length": str(300 * 1024 * 1024),
                                                   "Content-Type": "application/json"})
    assert status == 413
    status, _ = _post(server, "/api/login", b"", {"Content-Length": "-1"})
    assert status == 400
    status, _ = _post(server, "/api/login", b"", {"Content-Length": "mucho"})
    assert status == 400
    status, _ = _post(server, "/api/videos", b"", {"Content-Length": str(50 * 1024 * 1024)})
    assert status == 413


def test_wrong_passwords_from_one_address_never_lock_out_another(server):
    bad = json.dumps({"password": "mala"}).encode()
    for _ in range(10):
        status, _ = _post(server, "/api/login", bad, {"Content-Length": str(len(bad)), "X-Forwarded-For": "203.0.113.9"})
    assert status == 403
    status, _ = _post(server, "/api/login", bad, {"Content-Length": str(len(bad)), "X-Forwarded-For": "203.0.113.9"})
    assert status == 429                                                   # that address waits
    good = json.dumps({"password": "clave"}).encode()
    status, _ = _post(server, "/api/login", good, {"Content-Length": str(len(good)), "X-Forwarded-For": "198.51.100.4"})
    assert status == 200                                                   # the owner, elsewhere, gets in

