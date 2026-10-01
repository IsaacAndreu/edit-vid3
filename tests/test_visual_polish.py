"""Colour matching, archive look for old footage, pacing moves (slow zoom, emphasis punch-in, chapter pause)."""

import subprocess
from types import SimpleNamespace

import numpy as np

from pipeline.camera import add_zooms, emphasis_words, voice_frame_at, with_chapter_pauses
from pipeline.grade import correction, filters, stats
from pipeline.ingest import title_year
from pipeline.render import shot_filter, zoom_filter
from pipeline.schemas import Timeline, TimelineMedia, TimelineShot, Word
from pipeline.timeline import choose_layout


def test_grade_moves_towards_targets_and_never_tints_black_and_white():
    dark_warm = np.zeros((2, 20, 20, 3), dtype=np.float32)
    dark_warm[..., 0], dark_warm[..., 1], dark_warm[..., 2] = 0.40, 0.25, 0.10
    dark_warm[:, :10] *= 0.5
    c = correction(stats(dark_warm), {"strength": 0.6})
    assert c["brightness"] > 0 and c["red"] < 1 < c["blue"]
    grey = np.full((1, 20, 20, 3), 0.5, dtype=np.float32)
    grey[:, :10] = 0.2
    c = correction(stats(grey), {"strength": 0.6})
    assert c["red"] == 1 and c["blue"] == 1 and c["saturation"] == 1
    assert "colorbalance" in filters(c, "cine") and "colorbalance" not in filters(c, "neutral")


def test_old_or_low_res_footage_goes_archive():
    assert title_year("Olga Korbut 1972 Munich Olympics beam (HD 2016 upload)") == 1972
    assert title_year("Best of 2024") == 2024 and title_year("Top 100 moments") is None
    wide = TimelineMedia(src="a.mp4", kind="video", source="youtube", width=1920, height=1080)
    assert choose_layout("s001", "broll", wide, 0.0, old=True) == "archive"
    assert choose_layout("s001", "broll", wide, 0.0) == "full"
    assert choose_layout("s001", "chapter", wide, 0.0, old=True) == "full"


def _words(texts):
    return SimpleNamespace(words=[Word(index=i, text=t, start=i * 0.5, end=i * 0.5 + 0.4, matched=True,
                                       sentenceEnd=i == len(texts) - 1) for i, t in enumerate(texts)])


def test_emphasis_is_the_loud_figure_or_key_word():
    words = _words(["ganó", "la", "medalla", "en", "1972", "delante", "de", "todos"])
    levels = [-20, -21, -20, -22, -15, -20, -21, -20]
    assert emphasis_words(words, levels, {})[0] == 4
    assert emphasis_words(words, [-20] * 8, {}) == []


def _shot(i, kind="broll", layout="full"):
    return TimelineShot.model_validate({"id": f"s{i:03d}", "type": kind, "from": i * 30, "durationInFrames": 30, "text": "x",
                                        "chapterTitle": "C" if kind == "chapter" else None,
                                        "media": {"src": "a.mp4", "kind": "video", "source": "youtube", "layout": layout, "credit": "Fuente: X",
                                                  "width": 1920, "height": 1080}})


def test_slow_shots_push_in_and_stressed_words_punch_in():
    shots = [_shot(0), _shot(1), _shot(2, layout="card")]
    words = _words(["el", "llanto", "1972", "que", "cambió", "todo"])        # «1972» at 1.0 s → shot s001
    slow, punches = add_zooms(shots, {"s000": "slow"}, words, [-20, -20, -14, -20, -20, -20], 30,
                              {"emphasis_share": 1.0})
    assert slow == 1 and shots[0].media.zoom == [0, 30, 1.08]
    assert punches == 1 and shots[1].media.zoom[2] == 1.07 and shots[2].media.zoom is None


def test_chapter_pause_holds_the_card_and_gaps_the_voice():
    timeline = Timeline.model_validate({
        "slug": "t", "title": "T", "fps": 30, "width": 1920, "height": 1080, "durationInFrames": 90,
        "shots": [s.model_dump(by_alias=True) for s in (_shot(0), _shot(1, "chapter"), _shot(2))],
        "groups": [], "audio": {"voice": "audio/voz.mp3", "speech": [(0, 80)]}})
    out = with_chapter_pauses(timeline, 0.5, 30)
    assert [s.from_ for s in out.shots] == [0, 30, 75] and out.shots[1].durationInFrames == 45
    assert out.shots[1].media.rate == round(30 / 45, 4) and out.durationInFrames == 105
    assert out.audio.voiceGaps == [(30, 15)] and out.audio.speech == [(0, 30), (45, 95)]
    assert voice_frame_at([(30, 15)], 50) == 35


def test_fast_path_draws_zoom_speed_and_archive(tmp_path):
    assert zoom_filter(None, 1920, 1080, 30) == ""
    chain = shot_filter({"layout": "archive", "width": 1440, "height": 1080, "zoom": [0, 60, 1.08], "rate": 0.8}, 45, 30)
    assert "setpts=PTS/0.8000" in chain and "pad=1920:1080" in chain and "crop=1440:1080" in chain
    clip = tmp_path / "c.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=1440x1080:rate=30:duration=1",
                    "-pix_fmt", "yuv420p", str(clip)], check=True)
    out = tmp_path / "o.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(clip), "-filter_complex", f"[0:v]{chain},format=yuv420p[v]",
                    "-map", "[v]", "-frames:v", "45", str(out)], check=True)
    size = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(out)],
                          capture_output=True, text=True).stdout.strip()
    assert size == "1920,1080"
