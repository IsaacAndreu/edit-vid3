"""Sound bites: the shots' own roar or shout, 1-2 s under the voice, in sync with the picture."""

import wave
from pathlib import Path

import numpy as np

from pipeline import coldopen
from pipeline.context import RunContext
from pipeline.render import Renderer  # noqa: F401  (import check)
from pipeline.schemas import Timeline
from pipeline.timeline import voice_frame

BROLL = {"visualIntent": "gymnast", "queries": ["a", "b", "c"], "queriesLocal": ["d"]}


def _wav(path: Path, seconds: float, burst: tuple[float, float] | None, base_db: float = -40, burst_db: float = -12):
    rate = 8000
    rng = np.random.default_rng(1)
    x = rng.normal(0, 1, int(seconds * rate)) * 10 ** (base_db / 20)
    if burst:
        a, b = (int(t * rate) for t in burst)
        x[a:b] = rng.normal(0, 1, b - a) * 10 ** (burst_db / 20)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(rate)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
    return path


def test_the_roar_is_found_and_steady_sound_is_not(tmp_path):
    db, hop = coldopen.loudness(_wav(tmp_path / "roar.wav", 5, (3.0, 4.2)))
    window = coldopen.best_window(db, hop, 1.0, [])
    assert 2.9 <= window["at"] <= 3.3 and window["contrast"] > 15
    db, hop = coldopen.loudness(_wav(tmp_path / "music.wav", 5, None, base_db=-15))
    assert coldopen.best_window(db, hop, 1.0, [])["contrast"] < 2


def test_the_narrations_pauses_are_preferred(tmp_path):
    db, hop = coldopen.loudness(_wav(tmp_path / "two.wav", 5, (0.5, 1.5)))
    db[int(3.2 / hop): int(4.2 / hop)] = db[int(0.6 / hop)]            # an equal roar at 3.2 s
    window = coldopen.best_window(db, hop, 1.0, speech=[(0.0, 2.0)])   # the voice talks over the first one
    assert window["at"] >= 3.0 and window["talk"] == 0


class _FakeYouTube:
    def __init__(self, files):
        self.files = files

    def download_range(self, video_id, start, end, *, fmt, prefix, audio_only=False):
        assert audio_only and prefix == "au"
        src = self.files[video_id]
        target = src.parent / f"au_{start:.3f}_{end:.3f}.wav"
        target.write_bytes(src.read_bytes())
        return target


def test_bites_are_picked_spread_and_placed_on_the_voice(tmp_path):
    ctx = RunContext.create("v", root=tmp_path, config={"timeline": {"sound_bites": 2, "bite_gap": 20, "bite_from": 0}})
    shots = [{"id": f"s{i:03d}", "type": "broll", "startWord": i, "endWord": i, "start": 4.0 * i, "end": 4.0 * i + 4,
              "text": "t", "chapter": 0, "broll": BROLL} for i in range(20)]
    selections, files = [], {}
    for i, burst in [(3, (1.0, 2.2)), (4, (2.0, 3.0)), (10, (0.5, 1.5)), (18, None)]:
        selections.append({"shotId": f"s{i:03d}", "status": "selected", "decidedBy": "score", "candidateId": f"yt:vid{i:08d}",
                           "source": "youtube", "kind": "video", "start": 100.0, "end": 104.0, "score": 0.6,
                           "url": "u", "title": "t", "channel": "c", "credit": "Fuente: c"})
        files[f"vid{i:08d}"] = _wav(tmp_path / f"src{i}.wav", 4.5, burst)
    ctx.write_json("shots.json", {"slug": "v", "title": "T", "durationSeconds": 80, "chapters": [], "shots": shots})
    ctx.write_json("selection.json", {"slug": "v", "selections": selections})
    ctx.write_json("fallback.json", {"slug": "v", "items": []})
    ctx.write_json("words.json", {"words": [{"start": 40.0, "end": 41.0}]})
    bites = coldopen.pick_bites(ctx, _FakeYouTube(files))
    assert [b.shotId for b in bites] == ["s003", "s010"]                 # s004 too close to s003; s018 has no peak
    assert abs(bites[0].voiceAt - 13.0) < 0.3 and Path(tmp_path / bites[0].path).is_file()


def test_voice_frames_follow_the_cold_open_and_pauses():
    timeline = Timeline.model_validate({
        "slug": "t", "title": "T", "fps": 30, "width": 1920, "height": 1080, "durationInFrames": 600,
        "shots": [{"id": "s000", "type": "broll", "from": 0, "durationInFrames": 600, "text": "t",
                   "media": {"src": "m.jpg", "kind": "image", "source": "wikimedia", "credit": "Fuente: X"}}],
        "groups": [], "audio": {"voice": "v.mp3", "voiceFrom": 90, "voiceGaps": [(150, 120)]}})
    assert voice_frame(timeline, 2.0) == 150 and voice_frame(timeline, 6.0) == 90 + 180 + 120
