"""Right athlete on screen: on-screen captions (strong) and faces (clear cases only)."""

from pathlib import Path

from pipeline.identity import Checker, IdentityCache, caption_verdict, named_in, surname
from pipeline.context import RunContext
from pipeline.schemas import Shot

BROLL = {"visualIntent": "gymnast", "queries": ["a", "b", "c"], "queriesLocal": ["d"]}


def line(text, x0, y0, x1, y1):
    return (text, (x0, y0, x1, y1))


SCOREBOARD = [line("134GBR米DV6.0", 533, 878, 845, 915), line("JARMAN", 525, 929, 674, 963),
              line("PARIS2024", 196, 934, 290, 963), line("QOMEG", 744, 777, 867, 811)]


def test_a_caption_naming_someone_else_rejects_the_clip():
    assert "JARMAN" in caption_verdict([SCOREBOARD, SCOREBOARD, []], ["Carlos Yulo"])
    assert caption_verdict([SCOREBOARD, [], []], ["Carlos Yulo"]) is None          # once is not enough


def test_the_named_athlete_on_the_caption_keeps_it():
    ours = [line("PHIYULO", 500, 900, 700, 940), line("134GBR", 500, 850, 700, 890), line("JARMAN", 500, 950, 700, 990)]
    assert caption_verdict([ours, ours], ["Carlos Yulo"]) is None


def test_surname_firstname_lines_and_venues():
    french = [line("POCHON Antoine", 100, 100, 400, 140), line("FRASCA Loris", 100, 150, 400, 190)]
    assert "POCHON" in caption_verdict([french, french], ["Carlos Yulo"])
    venue = [line("DOHA", 100, 100, 250, 140), line("PHI", 1500, 900, 1580, 940), line("OMEGA", 1400, 950, 1580, 990)]
    assert caption_verdict([venue, venue, venue], ["Carlos Yulo"]) is None        # far from the code, or a sponsor


def test_who_a_shot_is_about():
    shot = Shot.model_validate({"id": "s001", "type": "broll", "startWord": 0, "endWord": 1, "start": 0, "end": 2,
                                "text": "Y entonces Yulo miró a Uchimura", "chapter": 0,
                                "broll": {**BROLL, "entities": ["Carlos Yulo"]}})
    assert named_in(shot, ["Carlos Yulo", "Kohei Uchimura", "Simone Biles"]) == ["Carlos Yulo", "Kohei Uchimura"]
    assert surname("Rebeca Andrade") == "ANDRADE"


def test_faces_are_not_judged_without_a_reliable_portrait_for_everyone(tmp_path):
    checker = Checker(RunContext.create("t", root=tmp_path, config={"fallback": {}}), [])
    checker._refs = {"Carlos Yulo": object(), "Kohei Uchimura": None}
    assert checker.face_verdict([object()], ["Carlos Yulo", "Kohei Uchimura"]) is None


def test_verdicts_are_cached(tmp_path):
    ctx = RunContext.create("t", root=tmp_path, config={"fallback": {}})
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x")
    calls = []

    class Fake:
        def check(self, path, kind, names):
            calls.append(path)
            return "el rótulo en pantalla dice JARMAN, no YULO"

    cache = IdentityCache(ctx)
    assert "JARMAN" in cache.get(Fake(), clip, "video", ["Carlos Yulo"])
    assert "JARMAN" in IdentityCache(ctx).get(Fake(), clip, "video", ["Carlos Yulo"])   # from work/t/identity.json
    assert len(calls) == 1
