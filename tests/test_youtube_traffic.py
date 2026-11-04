from __future__ import annotations

import unittest

from pipeline.clients.youtube_traffic import TrafficMeter, format_bytes


class FakeHeaders(dict):
    pass


class FakeResponse:
    def __init__(self, body: bytes, *, content_length: bool) -> None:
        self._body = body
        self.headers = FakeHeaders({"Content-Length": str(len(body))} if content_length else {})

    def read(self, amt: int | None = None) -> bytes:
        if amt is None:
            data, self._body = self._body, b""
        else:
            data, self._body = self._body[:amt], self._body[amt:]
        return data


class FakeYdl:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self._responses = responses

    def urlopen(self, _request: object) -> FakeResponse:
        return self._responses.pop(0)


class TrafficMeterTests(unittest.TestCase):
    def test_wrapped_urlopen_counts_content_length_or_bytes_read(self) -> None:
        meter = TrafficMeter()
        ydl = FakeYdl([FakeResponse(b"x" * 500, content_length=True), FakeResponse(b"y" * 300, content_length=False)])
        meter.wrap_ydl(ydl, "metadata")
        meter.wrap_ydl(ydl, "metadata")  # idempotent

        first = ydl.urlopen("req")
        self.assertEqual(meter.bytes_for("metadata"), 500)
        first.read()
        self.assertEqual(meter.bytes_for("metadata"), 500, "Content-Length responses are not double counted")

        second = ydl.urlopen("req")
        second.read(100)
        second.read()
        self.assertEqual(meter.bytes_for("metadata"), 800)
        self.assertEqual(meter.requests_for("metadata"), 2)

    def test_summary_and_dict(self) -> None:
        meter = TrafficMeter()
        meter.record("metadata", 2 * 1024 * 1024)
        meter.record("download", 10 * 1024 * 1024)
        meter.record("direct", 2048)
        meter.extractions = 3
        meter.info_reuses = 7
        meter.info_refreshes = 1
        meter.clip_downloads = 2
        meter.clip_library_hits = 4
        meter.storyboard_previews = 5
        lines = meter.summary_lines()
        self.assertIn("proxy metadatos 2.0 MB (1 peticiones)", lines[0])
        self.assertIn("proxy descargas 10.0 MB (2 clips)", lines[0])
        self.assertIn("total vía proxy 12.0 MB", lines[0])
        self.assertIn("3 extracciones de info, 7 reutilizaciones, 1 renovaciones", lines[1])
        self.assertIn("4 reutilizados", lines[1])
        payload = meter.as_dict()
        self.assertEqual(payload["proxy_bytes"], 12 * 1024 * 1024)
        self.assertEqual(payload["bytes"]["direct"], 2048)
        self.assertEqual(payload["storyboard_previews"], 5)
        self.assertEqual(meter.total_bytes, 12 * 1024 * 1024 + 2048)

    def test_format_bytes(self) -> None:
        self.assertEqual(format_bytes(512), "512 B")
        self.assertEqual(format_bytes(1536), "1.5 KB")
        self.assertEqual(format_bytes(3 * 1024**3), "3.0 GB")


if __name__ == "__main__":
    unittest.main()
