"""A change (POST) only from the studio's own pages."""

from __future__ import annotations

import http.client
import json

from tests.test_seguridad_peticiones import _post, server  # noqa: F401  (fixture)


def test_a_change_needs_the_studios_page(server):  # noqa: F811
    good = json.dumps({"password": "clave"}).encode()
    conn = http.client.HTTPConnection("127.0.0.1", server, timeout=10)
    conn.request("POST", "/api/login", good, {"Content-Length": str(len(good))})
    response = conn.getresponse()
    cookie = response.getheader("Set-Cookie").split(";")[0]
    response.read()
    body = json.dumps({"name": "x"}).encode()
    base = {"Content-Length": str(len(body)), "Cookie": cookie, "Content-Type": "application/json"}
    for extra, expected_forbidden in (({}, True), ({"Sec-Fetch-Site": "cross-site"}, True),
                                      ({"Sec-Fetch-Site": "same-site"}, True), ({"Sec-Fetch-Site": "same-origin"}, False),
                                      ({"X-Estudio": "1"}, False)):
        status, text = _post(server, "/api/channels", body, {**base, **extra})
        assert (status == 403 and "Origen" in text.decode()) == expected_forbidden, (extra, status, text)

