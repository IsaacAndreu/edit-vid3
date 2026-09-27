from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from pipeline.ingest import normalise_image, normalise_video, probe
from pipeline.schemas import IngestedMedia


def _source(path: Path, *, size: str = "1280x720", rate: int = 25, seconds: int = 8) -> None:
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", f"testsrc2=size={size}:rate={rate}:duration={seconds}",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
         "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(path)],
        check=True,
    )


def _identity_lut(path: Path, size: int = 2) -> None:
    lines = [f"LUT_3D_SIZE {size}"]
    for b in range(size):
        for g in range(size):
            for r in range(size):
                lines.append(f"{r / (size - 1):.1f} {g / (size - 1):.1f} {b / (size - 1):.1f}")
    path.write_text("\n".join(lines) + "\n")


class NormaliseTests(unittest.TestCase):
    def test_video_is_cover_1080p_30fps_silent_and_exact_length(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source, target, lut = Path(tmp) / "hd.mp4", Path(tmp) / "s001.mp4", Path(tmp) / "lut.cube"
            _source(source, size="1280x720")            # 16:9 → cover 1920x1080
            _identity_lut(lut)
            normalise_video(source, target, offset=2.3, duration=3.1, lut=lut, cfg={"preset": "ultrafast"})
            info = probe(target)
        self.assertEqual((info["width"], info["height"]), (1920, 1080))
        self.assertAlmostEqual(info["fps"], 30.0)
        self.assertFalse(info["hasAudio"])
        self.assertAlmostEqual(info["duration"], 93 / 30, delta=0.02)   # round(3.1 * 30) frames

    def test_narrow_video_keeps_its_frame_for_a_card(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / "hd.mp4", Path(tmp) / "s003.mp4"
            _source(source, size="720x1280", seconds=3)  # vertical phone video → fitted, not cropped
            normalise_video(source, target, offset=0.5, duration=2.0, lut=None, cfg={"preset": "ultrafast"})
            info = probe(target)
        self.assertEqual((info["width"], info["height"]), (608, 1080))

    def test_pillarboxed_vertical_video_loses_its_black_bars(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / "hd.mp4", Path(tmp) / "s004.mp4"
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                            "-i", "testsrc2=size=406x720:rate=30:duration=3", "-vf", "pad=1280:720:437:0:black",
                            "-c:v", "libx264", "-preset", "ultrafast", str(source)], check=True)
            normalise_video(source, target, offset=0.5, duration=1.0, lut=None, cfg={"preset": "ultrafast"})
            info = probe(target)
        self.assertLess(info["width"] / info["height"], 0.7)            # a vertical card, not a 16:9 frame

    def test_image_gets_ken_burns_headroom(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / "photo.png", Path(tmp) / "s002.jpg"
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                            "-i", "testsrc2=size=1920x1080:duration=1", "-frames:v", "1", str(source)], check=True)
            normalise_image(source, target, lut=None)
            info = probe(target)
            self.assertEqual((info["width"], info["height"]), (2304, 1296))
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                            "-i", "testsrc2=size=1600x1200:duration=1", "-frames:v", "1", str(source)], check=True)
            normalise_image(source, target, lut=None)           # 4:3 photo → uncropped, for a card
            info = probe(target)
        self.assertEqual((info["width"], info["height"]), (1728, 1296))


class WikimediaTests(unittest.TestCase):
    def test_originals_become_standard_thumbnails(self) -> None:
        from pipeline.ingest import wikimedia_thumbnails

        url = "https://upload.wikimedia.org/wikipedia/commons/1/12/Casa_generalitat_web.jpg?utm_source=x"
        self.assertEqual(wikimedia_thumbnails(url), [
            "https://upload.wikimedia.org/wikipedia/commons/thumb/1/12/Casa_generalitat_web.jpg/1920px-Casa_generalitat_web.jpg",
            "https://upload.wikimedia.org/wikipedia/commons/thumb/1/12/Casa_generalitat_web.jpg/1280px-Casa_generalitat_web.jpg",
        ])
        thumb = "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/X.jpg/1920px-X.jpg"
        self.assertEqual(wikimedia_thumbnails(thumb), [thumb])
        self.assertEqual(wikimedia_thumbnails("https://live.staticflickr.com/1/2.jpg"), ["https://live.staticflickr.com/1/2.jpg"])


class IngestSchemaTests(unittest.TestCase):
    BASE = {"shotId": "s001", "kind": "video", "path": "work/x/media/s001.mp4", "source": "youtube",
            "candidateId": "yt:x", "start": 10, "end": 13, "durationSeconds": 3.0, "width": 1920, "height": 1080,
            "fps": 30, "credit": "Fuente: Canal", "specHash": "h"}

    def test_accepts_a_valid_clip(self) -> None:
        IngestedMedia.model_validate(self.BASE)

    def test_rejects_over_five_seconds_audio_wrong_size_or_bad_credit(self) -> None:
        for change in ({"durationSeconds": 5.2}, {"hasAudio": True}, {"width": 1280, "height": 720}, {"credit": "Canal"}):
            with self.assertRaises(ValidationError, msg=str(change)):
                IngestedMedia.model_validate({**self.BASE, **change})


if __name__ == "__main__":
    unittest.main()
