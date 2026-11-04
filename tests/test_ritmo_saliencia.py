import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np
import pytest

from pipeline import ritmo, saliencia

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg")


def test_quiet_stretches_and_silences():
    change = np.array([0.1] * 8 + [0.0] * 60 + [0.1] * 8)        # 2 s moving, 15 s still, 2 s moving
    assert ritmo.quiet_stretches(change, 12) == [(2.0, 17.0)]
    assert ritmo.quiet_stretches(change, 16) == []
    db = np.array([-20.0] * 40 + [-60.0] * 12 + [-20.0] * 200)    # 3 s quiet after 10 s of voice
    assert ritmo.silences(db, 2.5, 63.0) == [(10.0, 13.0)]
    assert ritmo.silences(db, 2.5, 25.0) == []                   # within the end screen: not checked


@needs_ffmpeg
def test_analyse_finds_the_still_stretch_and_the_pause(tmp_path):
    video = tmp_path / "v.mp4"
    # 20 s moving test pattern, then 16 s of a frozen frame, then 26 s moving again; voice tone with a 4 s gap
    subprocess.run(["ffmpeg", "-v", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=10:duration=20",
                    "-f", "lavfi", "-i", "color=c=gray:size=320x180:rate=10:duration=16",
                    "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=10:duration=26",
                    "-f", "lavfi", "-i", "sine=f=220:duration=62",
                    "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v];"
                    "[3:a]volume='if(between(t,28,32),0,1)':eval=frame[a]",
                    "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)], check=True)
    result = ritmo.analyse(video, {"quiet_seconds": 12, "silence_seconds": 2.5})
    quiet = [x for x in result["found"] if x["kind"] == "quieto"]
    silent = [x for x in result["found"] if x["kind"] == "silencio"]
    assert len(quiet) == 1 and 19 <= quiet[0]["start"] <= 21 and 35 <= quiet[0]["end"] <= 37
    assert len(silent) == 1 and 27.5 <= silent[0]["start"] <= 28.5
    assert 0.6 < result["moving"] < 0.85 and result["longestQuiet"] >= 15
    text = ritmo.markdown("x", result)
    assert "sin nada nuevo en pantalla" in text and "la voz calla" in text
    assert "1 tramo quieto" in ritmo.summary(result)


def _picture(kind: str) -> np.ndarray:
    rng = np.random.default_rng(1)
    if kind == "focus":                      # dark background, one bright red disc
        image = np.full((720, 1280, 3), (40, 30, 25), np.uint8)
        cv2.circle(image, (640, 360), 150, (40, 40, 230), -1)
        return image
    if kind == "flat":
        return np.full((720, 1280, 3), 128, np.uint8)
    noise = rng.integers(0, 255, (72, 128, 3), dtype=np.uint8)       # blocky noise: busy even when small
    return cv2.resize(noise, (1280, 720), interpolation=cv2.INTER_NEAREST)


def test_measure_prefers_one_clear_spot():
    focus, flat, busy = (saliencia.measure(_picture(k)) for k in ("focus", "flat", "busy"))
    assert focus["score"] > busy["score"] and focus["score"] > flat["score"]
    assert busy["clean"] < 0.2 and focus["clean"] > 0.8
    assert flat["contrast"] < 0.05
    assert "foco claro" in saliencia.why(focus)


def test_order_stills_renames_best_first(tmp_path):
    for n, kind in enumerate(("flat", "busy", "focus"), 1):
        cv2.imwrite(str(tmp_path / f"fotograma-{n}.jpg"), _picture(kind))
    ranked = saliencia.order_stills(tmp_path)
    assert [r["was"] for r in ranked][0] == "fotograma-3.jpg"
    assert sorted(p.name for p in tmp_path.glob("fotograma-*.jpg")) == ["fotograma-1.jpg", "fotograma-2.jpg", "fotograma-3.jpg"]
    best = saliencia.score_file(tmp_path / "fotograma-1.jpg")
    assert best["score"] == ranked[0]["score"]
    assert "| 1 | fotograma-1.jpg |" in (tmp_path / "puntuacion.md").read_text("utf-8")
    assert not list(tmp_path.glob(".orden-*"))


def test_order_stills_empty_folder(tmp_path):
    assert saliencia.order_stills(tmp_path) == []
    assert not (tmp_path / "puntuacion.md").exists()
