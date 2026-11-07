"""The proxy down while searching or analysing is the run's problem, never «this shot has nothing»: it stops the
stage (the video waits and is tried again) and what was written during an outage is redone, not kept as final."""

import json

import pytest

from pipeline.budget import ProxyDown
from pipeline.schemas import ShotCandidates, ShotScores
from pipeline.sourcing import stale_note
from pipeline.sourcing.youtube import GAVE_UP, YouTubeSource
from tests.test_sin_youtube import FakeYouTube, _sourcing
from tests.test_sourcing import BROLL


def test_a_proxy_outage_stops_the_candidates_instead_of_giving_up_on_the_shot(tmp_path, monkeypatch):
    yt = YouTubeSource(root=tmp_path, cache_dir=tmp_path / "cache", config={"min_interval": 0})
    entries = [{"id": f"{c * 11}", "title": "t", "channel": "c", "duration": 200, "width": 1920, "height": 1080}
               for c in "ABCDEFG"]
    monkeypatch.setattr(yt, "search", lambda query: entries)
    monkeypatch.setattr(yt, "info", lambda video_id: (_ for _ in ()).throw(ProxyDown("El proxy x no responde")))
    notes = []
    with pytest.raises(ProxyDown):
        yt.candidates(BROLL, notes)
    assert not any(GAVE_UP in n or "no responde" in n for n in notes)   # not «hard shot: 6 looked at, 0 valid»


def test_candidates_searched_while_the_proxy_was_down_are_searched_again(tmp_path, monkeypatch):
    youtube = FakeYouTube()
    ctx, sourcing = _sourcing(tmp_path, monkeypatch, youtube)
    sourcing.run(ctx)
    sourcing.run(ctx)                                      # cached: nothing searched again
    assert youtube.searched == 1
    path = ctx.work_dir / "candidates" / "s001.json"
    found = json.loads(path.read_text("utf-8"))
    found["notes"] = ["yt:g4ZPw2Oqwn8: El proxy gw.dataimpulse.com no responde: ¿está abierto proxy-youtube en ese PC",
                      f"{GAVE_UP}: 6 vídeos mirados, 0 válidos"]
    found["candidates"] = []
    path.write_text(json.dumps(found), encoding="utf-8")
    sourcing.run(ctx)                                      # written during an outage: not a result, searched again
    assert youtube.searched == 2
    assert ShotCandidates.model_validate_json(path.read_text("utf-8")).candidates
    assert stale_note("El proxy de YouTube (casa) no responde") and stale_note("YouTube bloquea esta conexión") and not stale_note("ok")


def test_scores_written_while_the_proxy_was_down_are_analysed_again(tmp_path):
    from pipeline.analysis import reusable

    path = tmp_path / "s001.json"
    good = ShotScores(shotId="s001", inputsHash="h1", needed=4.0, prompts=["p"], options=[], notes=["3 ventanas"])
    path.write_text(good.model_dump_json(), encoding="utf-8")
    assert reusable(path, ("h1", None)) and not reusable(path, ("h2", None))
    bad = good.model_copy(update={"notes": ["yt:wCuI8412d2g 884.7-898.55: El proxy gw.dataimpulse.com no responde: ¿está abierto"]})
    path.write_text(bad.model_dump_json(), encoding="utf-8")
    assert not reusable(path, ("h1", None))
    assert not reusable(tmp_path / "missing.json", ("h1",))
