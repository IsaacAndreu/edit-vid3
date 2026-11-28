"""Pasted links are only read from public internet addresses, also after each redirect; the editor's cache route
serves pictures and video only."""

from types import SimpleNamespace

import pytest

from pipeline import referencias
from pipeline.referencias import BlockedLink, fetch_text, public_url

PUBLIC = lambda host: ["93.184.216.34"]                                    # noqa: E731


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.5", "192.168.1.10", "169.254.169.254", "::1", "fd00::1",
                                     "0.0.0.0", "100.64.0.1"])
def test_private_addresses_are_never_read(address):
    with pytest.raises(BlockedLink):
        public_url("https://lo-que-sea.example/pagina", resolve=lambda host: [address])


def test_only_http_and_web_ports():
    assert public_url("https://example.com/a", resolve=PUBLIC)
    for url in ("file:///etc/passwd", "ftp://example.com/x", "http://example.com:4416/x", "gopher://x"):
        with pytest.raises(BlockedLink):
            public_url(url, resolve=PUBLIC)


class Response:
    def __init__(self, status, location=None, body=b"<p>hola</p>"):
        self.status_code, self.headers, self.body, self.encoding = status, ({"Location": location} if location else {}), body, "utf-8"

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)

    def iter_content(self, size):
        yield self.body

    def close(self):
        pass


def test_a_redirect_to_a_private_address_is_refused():
    hosts = {"publico.example": ["93.184.216.34"], "interno.example": ["127.0.0.1"]}
    asked = []

    def get(url, **kw):
        asked.append(url)
        return Response(302, "http://interno.example/secreto") if "publico" in url else Response(200)

    with pytest.raises(BlockedLink):
        fetch_text("https://publico.example/x", session=SimpleNamespace(get=get), resolve=lambda h: hosts[h])
    assert asked == ["https://publico.example/x"]                                 # the private one never asked


def test_a_public_page_is_read_and_capped():
    big = b"a" * (referencias.MAX_BYTES + 5000)
    session = SimpleNamespace(get=lambda url, **kw: Response(200, body=big))
    assert len(fetch_text("https://example.com", session=session, resolve=PUBLIC)) == referencias.MAX_BYTES


def test_the_editor_serves_only_media_from_the_cache(tmp_path):
    from pipeline import editor

    (tmp_path / "cache" / "referencias").mkdir(parents=True)
    (tmp_path / "cache" / "referencias" / "x.json").write_text("{}")
    (tmp_path / "cache" / "analysis").mkdir()
    (tmp_path / "cache" / "analysis" / "clip.mp4").write_bytes(b"0")
    ctx = SimpleNamespace(root=tmp_path, work_dir=tmp_path / "work" / "v", slug="v")
    assert editor.respond(ctx, "GET", "/root/cache/referencias/x.json")[0] != "file"
    kind, found, _ = editor.respond(ctx, "GET", "/root/cache/analysis/clip.mp4")
    assert kind == "file" and found.name == "clip.mp4"
