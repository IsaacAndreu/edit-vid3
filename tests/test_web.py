from __future__ import annotations

import json
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from pipeline import budget, feedback, mychannel, radar, web
from pipeline.context import RunContext

REPO = Path(__file__).resolve().parent.parent
SCRIPT = "Texto del guion. " * 20


def _project(root: Path) -> None:
    shutil.copy(REPO / "config.yaml", root / "config.yaml")
    shutil.copytree(REPO / "canales", root / "canales")
    (root / "materiales").mkdir()


def _video_with_timeline(root: Path, slug: str = "V1") -> None:
    folder = root / "materiales" / slug
    folder.mkdir(parents=True)
    (folder / "guion.txt").write_text(SCRIPT)
    work = root / "work" / slug
    work.mkdir(parents=True)
    (work / "timeline.json").write_text(json.dumps({"fps": 30, "shots": [
        {"id": "s001", "from": 0, "durationInFrames": 60, "text": "Una frase", "media": {"src": "media/s001.mp4", "kind": "video", "credit": "Fuente: A"}},
        {"id": "s002", "from": 60, "durationInFrames": 60, "text": "Otra frase", "media": {"src": "media_fallback/s002.mp4", "kind": "video", "credit": "Fuente: B"}},
        {"id": "g1", "from": 120, "durationInFrames": 30, "text": "", "media": {}},
    ]}))
    (work / "selection.json").write_text(json.dumps({"selections": [
        {"shotId": "s001", "status": "selected", "decidedBy": "judge", "candidateId": "yt:AAA", "start": 10.0, "end": 12.0,
         "url": "https://youtu.be/AAA", "title": "Vídeo A", "source": "youtube"},
        {"shotId": "s002", "status": "fallback", "decidedBy": "judge"}]}))
    (work / "fallback.json").write_text(json.dumps({"items": [
        {"shotId": "s002", "method": "protagonist-filler", "candidateId": "yt:BBB", "start": 30.0, "end": 33.0,
         "url": "https://youtu.be/BBB", "credit": "Fuente: B", "attribution": "B — \"Vídeo B\": https://youtu.be/BBB", "source": "youtube"}]}))


class BudgetTests(unittest.TestCase):
    def test_today_spending_against_the_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            today = datetime.now(timezone.utc).date().isoformat()
            (root / "work" / "A").mkdir(parents=True)
            (root / "work" / "A" / "costs.json").write_text(json.dumps({"entries": [
                {"at": today + "T01:00:00", "usd": 0.6}, {"at": "2020-01-01T01:00:00", "usd": 9}]}))
            self.assertAlmostEqual(budget.spent_today(root), 0.6)
            self.assertEqual(budget.limit(root, {"budget": {"daily_usd": 2}}), 2.0)
            budget.check(root, {"budget": {"daily_usd": 2}})
            (root / "out").mkdir()
            (root / "out" / "_ajustes.json").write_text(json.dumps({"daily_usd": 0.5}))    # the studio wins
            with self.assertRaises(budget.BudgetReached):
                budget.check(root, {"budget": {"daily_usd": 2}})


class StudioFunctionTests(unittest.TestCase):
    def test_create_video_in_a_channel_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _project(root)
            made = web.create_video(root, {"name": "avion9", "channel": "aviacion", "script": SCRIPT, "serie": "fracasos"})
            folder = root / "materiales" / "aviacion" / "avion9"
            self.assertEqual(made["slug"], "avion9")
            self.assertTrue((folder / "guion.txt").is_file())
            self.assertIn("serie: fracasos", (folder / "config.yaml").read_text())
            self.assertIn("canal: aviacion", (root / "materiales" / "aviacion" / "config.yaml").read_text())
            for bad in ({"name": "con espacio", "script": SCRIPT}, {"name": "x", "script": "corto"},
                        {"name": "avion9", "channel": "aviacion", "script": SCRIPT}, {"name": "y", "channel": "nada", "script": SCRIPT}):
                with self.assertRaises(ValueError):
                    web.create_video(root, bad)
            mp3 = b"ID3" + b"\0" * 20000
            web.save_voice(root, "avion9", mp3)
            self.assertEqual((folder / "voz.mp3").read_bytes(), mp3)
            with self.assertRaises(ValueError):
                web.save_voice(root, "avion9", b"ID3")

    def test_an_empty_channel_folder_is_not_listed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _project(root)
            (root / "materiales" / "atletismo").mkdir(parents=True)
            (root / "materiales" / "atletismo" / "config.yaml").write_text("canal: gimnasia\n")
            web.create_video(root, {"name": "v1", "script": SCRIPT})
            self.assertEqual([v["slug"] for v in web.overview(root)["videos"]], ["v1"])

    def test_settings_keep_my_channels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _project(root)
            out = web.settings(root, {"my_channels": {"gimnasia": " @MiCanal ", "inventado": "@x"}, "paused": True})
            self.assertEqual(out["myChannels"]["gimnasia"], "@MiCanal")
            self.assertTrue(out["paused"])
            self.assertNotIn("inventado", out.get("my_channels", {}))
            self.assertEqual(mychannel.handle_for(root, "gimnasia"), "@MiCanal")


class FeedbackTests(unittest.TestCase):
    def test_labels_block_fragments_and_send_shots_to_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _video_with_timeline(root)
            shots = feedback.shots(root, "V1")
            self.assertEqual([s["id"] for s in shots], ["s001", "s002"])          # graphics without media are left out
            self.assertEqual((shots[0]["method"], shots[1]["method"], shots[1]["title"]), ("judge", "protagonist-filler", "Vídeo B"))
            with self.assertRaises(ValueError):
                feedback.label(root, "V1", "s001", "incorrecta")                 # a reason is needed
            feedback.label(root, "V1", "s001", "incorrecta", "persona_equivocada")
            feedback.label(root, "V1", "s002", "incorrecta", "dibujo_animado")
            fragments = feedback.wrong_fragments(root)
            self.assertTrue(feedback.is_wrong(fragments, "yt:AAA", 14.0, 15.0))      # within the 4 s around it
            self.assertFalse(feedback.is_wrong(fragments, "yt:AAA", 40.0, 42.0))
            self.assertTrue(feedback.is_wrong(fragments, "yt:BBB", 500.0, 502.0))    # a cartoon: the whole source
            self.assertEqual(set(feedback.wrong_shots(root / "work" / "V1")), {"s001", "s002"})
            ctx = RunContext.create("Otro", root=root, config={"judge": {"avoid_other_videos": False}})
            from pipeline.judge import used_elsewhere

            self.assertIn("yt:AAA", used_elsewhere(ctx))
            feedback.label(root, "V1", "s002", None)
            feedback.label(root, "V1", "s002", "correcta")
            summary = feedback.summary(root)
            self.assertEqual(summary["total"], {"correcta": 1, "incorrecta": 1, "dudosa": 0})
            self.assertEqual(summary["reasons"][0]["reason"], "persona_equivocada")
            self.assertEqual(set(feedback.wrong_shots(root / "work" / "V1")), {"s001"})

    def test_fallback_reads_the_revision_only_when_there_is_one(self) -> None:
        from pipeline import fallback

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _video_with_timeline(root)
            ctx = RunContext.create("V1", root=root, config={})
            self.assertNotIn(ctx.work_dir / feedback.REVISION, fallback.inputs(ctx))   # same fingerprint as before
            feedback.label(root, "V1", "s001", "incorrecta", "roto")
            self.assertIn(ctx.work_dir / feedback.REVISION, fallback.inputs(ctx))


class ChannelAnalysisTests(unittest.TestCase):
    def test_heat_map_titles_topics_and_stops(self) -> None:
        now = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
        videos = []
        for i in range(24):
            # March-June, nothing from July on; the CAPITALS titles do 3x the others
            month = 3 + i % 4
            when = datetime(2026, month, 2 + (i // 4) * 4, 19, tzinfo=timezone.utc)
            good = i % 2 == 0
            videos.append({"id": str(i), "title": ("EL SECRETO de" if good else "historia de") + f" algo {i}",
                           "published": (when if good else when + timedelta(days=2, hours=-9)).isoformat(),
                           "duration": 700, "views": 30000 if good else 10000, "thumbnail": "", "url": ""})
        report = mychannel.analyse(videos, {"title": "X", "subscribers": 1000}, "UTC", now=now,
                                   topics=[{"name": "Secretos", "videos": [i for i in range(24) if i % 2 == 0]},
                                           {"name": "Historias", "videos": [i for i in range(24) if i % 2]}])
        self.assertEqual(sum(c["count"] for row in report["heat"] for c in row), 24)
        caps = next(t for t in report["titles"]["traits"] if t["key"] == "caps")
        self.assertGreater(caps["factor"], 2)
        self.assertEqual(report["topics"][0]["name"], "Secretos")
        self.assertIn("meses parado", report["consistencyNote"])
        self.assertEqual(report["numbers"]["hits"], 0)            # 30k vs a 20k median is 1.5x, not a hit
        self.assertTrue(any("mayúsculas" in t for t in report["tips"]))


class RadarTests(unittest.TestCase):
    def test_niche_measure_and_daily_due(self) -> None:
        fake = [{"id": str(i), "title": "t", "views": 50000, "ratio": r, "subscribers": s, "thumbnail": "", "url": ""}
                for i, (r, s) in enumerate([(5, 20000), (4, 2_000_000), (3.5, 50000), (1, 10000), (0.5, None)])]
        with patch("pipeline.lab.outliers", return_value=fake):
            stats = radar.measure(None, None, "algo")
        self.assertEqual((stats["hits"], stats["smallHits"]), (3, 2))
        self.assertGreater(stats["score"], 0)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("pipeline.radar.datetime") as clock:
                clock.now.return_value = datetime(2026, 10, 4, 9)
                self.assertTrue(radar.due(root, {"radar": {"hour": 7}}))
                self.assertFalse(radar.due(root, {"radar": {"hour": 7, "enabled": False}}))
                clock.now.return_value = datetime(2026, 10, 4, 5)
                self.assertFalse(radar.due(root, {"radar": {"hour": 7}}))


class HttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _project(self.root)
        _video_with_timeline(self.root)
        (self.root / "out" / "V1").mkdir(parents=True)
        (self.root / "out" / "V1" / "video-final.mp4").write_bytes(b"0123456789")
        (self.root / "secreto.txt").write_text("no")
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), web.make_handler(self.root, "clave"))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.cookie = ""

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def call(self, path: str, body: dict | None = None, headers: dict | None = None) -> tuple[int, bytes, dict]:
        request = urllib.request.Request(self.base + path, data=json.dumps(body).encode() if body is not None else None,
                                         headers={"Content-Type": "application/json", **({"Cookie": self.cookie} if self.cookie else {}),
                                                  **(headers or {})})
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, response.read(), dict(response.headers)
        except urllib.error.HTTPError as error:
            return error.code, error.read(), dict(error.headers)

    def test_password_session_files_and_review(self) -> None:
        self.assertEqual(self.call("/api/review/V1")[0], 401)
        with patch("pipeline.web.time.sleep"):
            self.assertEqual(self.call("/api/login", {"password": "mala"})[0], 403)
        code, _, headers = self.call("/api/login", {"password": "clave"})
        self.assertEqual(code, 200)
        self.assertIn("HttpOnly", headers["Set-Cookie"])
        self.cookie = headers["Set-Cookie"].split(";")[0]
        code, body, _ = self.call("/api/review/V1")
        self.assertEqual((code, len(json.loads(body)["shots"])), (200, 2))
        code, body, _ = self.call("/files/V1/video-final.mp4", headers={"Range": "bytes=2-4"})
        self.assertEqual((code, body), (206, b"234"))
        self.assertEqual(self.call("/files/V1/..%2F..%2Fsecreto.txt")[0], 404)       # never outside out/<vídeo>/
        self.assertEqual(self.call("/api/review/V1/s001", {"verdict": "dudosa"}, {"Origin": "http://otro.com"})[0], 403)
        self.assertEqual(self.call("/api/review/V1/s001", {"verdict": "dudosa"})[0], 200)
        self.assertEqual(feedback.labels(self.root)["V1/s001"]["verdict"], "dudosa")
        code, body, _ = self.call("/api/video/V1/fix", {})
        self.assertEqual(code, 400)                                     # nothing marked wrong yet
        self.cookie = ""
        with patch("pipeline.web.time.sleep"):
            codes = [self.call("/api/login", {"password": "mala"})[0] for _ in range(11)]
        self.assertEqual((codes[0], codes[-1]), (403, 429))              # guessing is cut off
        self.cookie = "studio=123.falsa"
        self.assertEqual(self.call("/api/errors")[0], 401)


if __name__ == "__main__":
    unittest.main()
