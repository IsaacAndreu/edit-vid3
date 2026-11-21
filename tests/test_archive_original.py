"""gta2-it: nine shots of one Commons .webm each opened it with ffmpeg, without a User-Agent: all nine failed with a
4XX. The original is downloaded once, with our User-Agent, and every shot is cut from the local copy."""

import subprocess
import threading
from pathlib import Path

from pipeline.sourcing import archive


class FakeResponse:
    def __init__(self, body=b"", size=0):
        self.status_code, self.body, self.headers = 200, body, {"Content-Length": str(size)}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def raise_for_status(self):
        pass

    def iter_content(self, n):
        yield self.body


class FakeSession:
    def __init__(self, body, size):
        self.headers, self.gets, self.body, self.size = {}, 0, body, size

    def head(self, url, **kw):
        return FakeResponse(size=self.size)

    def get(self, url, **kw):
        self.gets += 1
        return FakeResponse(self.body, self.size)


def test_one_download_for_many_shots_with_our_user_agent(tmp_path):
    session = FakeSession(b"video-bytes", 11)
    url = "https://upload.wikimedia.org/x/THE_CITY.webm?utm_source=commons"
    got = []
    threads = [threading.Thread(target=lambda: got.append(archive.original(url, tmp_path, session=session)))
               for _ in range(5)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert session.gets == 1 and len(set(got)) == 1 and got[0].suffix == ".webm"
    assert got[0].read_bytes() == b"video-bytes" and session.headers["User-Agent"] == archive.USER_AGENT


def test_too_big_stays_on_the_network(tmp_path):
    session = FakeSession(b"x", 3_000_000_000)
    assert archive.original("https://example.org/big.webm", tmp_path, session=session) is None and session.gets == 0


def test_cut_uses_the_local_copy(tmp_path, monkeypatch):
    clip = tmp_path / "src.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=160x90:rate=10:duration=3",
                    str(clip)], check=True)
    monkeypatch.setattr(archive, "original", lambda url, folder, **kw: clip)
    target = tmp_path / "archive" / "hd" / "id" / "hd_0.500_1.500.mp4"
    assert archive.cut("https://upload.wikimedia.org/a.webm", 0.5, 1.5, target).is_file()
