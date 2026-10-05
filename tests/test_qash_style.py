"""The business channel's qash-like look: archive layout, chalkboard fallback, weak shots → graphics."""

import json

from pipeline import graphics, planner, qa
from pipeline.config import PROJECT_ROOT
from pipeline.context import RunContext
from pipeline.schemas import Timeline, TimelineGroup, TimelineMedia, TimelineShot
from pipeline.timeline import chalkboards, choose_layout, key_phrase, weak_sentences

from tests.test_timeline import BROLL  # noqa: E402

MEDIA = {"src": "media/s.mp4", "kind": "video", "source": "youtube", "credit": "Fuente: RTVE"}


def test_narrow_clips_become_archive_only_when_asked():
    narrow = TimelineMedia.model_validate({**MEDIA, "width": 1440, "height": 1080})
    wide = TimelineMedia.model_validate({**MEDIA, "width": 1920, "height": 1080})
    assert choose_layout("s001", "broll", narrow, 0.25) == "card"
    assert choose_layout("s001", "broll", narrow, 0.25, "archive") == "archive"
    assert choose_layout("s001", "broll", wide, 0.0, "archive") == "full"
    photo = TimelineMedia.model_validate({**MEDIA, "kind": "image", "width": 1000, "height": 1000})
    assert choose_layout("s001", "broll", photo, 0.0, "archive") in ("card", "parallax")


def test_key_phrase_keeps_the_scripts_words():
    assert key_phrase("Las regulaciones reducen ingresos.") == "Las regulaciones reducen ingresos"
    long = "No hay luz natural, el casino es un universo cerrado sin relojes ni ventanas para el jugador."
    phrase = key_phrase(long)
    assert 2 <= len(phrase.split()) <= 8 and phrase in long
    assert graphics.said_words(phrase, long)


def _shot(i, media=True, kind="broll"):
    return TimelineShot.model_validate({"id": f"s{i:03d}", "type": kind, "from": i * 60, "durationInFrames": 60,
                                        "text": "El tiempo trabaja para ti, no para el jugador.",
                                        "media": MEDIA if media else None})


def test_chalkboards_cover_empty_shots_and_pass_the_schema():
    shots = [_shot(0), _shot(1, media=False), _shot(2, media=False)]
    busy = TimelineGroup.model_validate({"id": "g1", "kind": "graphic", "from": 120, "durationInFrames": 60,
                                         "graphic": {"type": "kinetic", "lines": ["x"]}})
    boards = chalkboards(shots, [busy], 30)
    assert [b.id for b in boards] == ["board-s001"]                  # s002 already sits under a graphic
    assert boards[0].graphic["board"] is True and boards[0].graphic["lines"]
    base = {"slug": "t", "title": "T", "fps": 30, "width": 1920, "height": 1080, "durationInFrames": 180,
            "audio": {"voice": "audio/voz.mp3"}, "shots": [s.model_dump(by_alias=True) for s in shots]}
    Timeline.model_validate({**base, "groups": [g.model_dump(by_alias=True) for g in [busy, *boards]]})
    try:
        Timeline.model_validate({**base, "groups": [busy.model_dump(by_alias=True)]})
    except ValueError as error:
        assert "s001" in str(error)
    else:
        raise AssertionError("a shot without footage nor board must be rejected")


def test_weak_sentences_are_marked_for_graphics(tmp_path):
    ctx = RunContext.create("t", root=tmp_path, config={"video": {"fps": 30}})
    shot = lambda i, s, e: {"id": f"s{i:03d}", "type": "broll", "startWord": i, "endWord": i, "start": s, "end": e,  # noqa: E731
                            "text": "t", "chapter": 0, "broll": BROLL}
    ctx.write_json("shots.json", {"slug": "t", "title": "T", "durationSeconds": 9.0, "chapters": [],
                                  "shots": [shot(0, 0, 3), shot(1, 3, 6), shot(2, 6, 9)]})
    ctx.write_json("selection.json", {"selections": [{"shotId": "s000", "score": 0.6}, {"shotId": "s001", "score": 0.25}]})
    ctx.write_json("fallback.json", {"slug": "t", "items": [], "unresolved": {"s002": "nada"}})
    sents = [{"n": 0, "start": 0.0, "end": 3.0}, {"n": 1, "start": 3.0, "end": 6.0}, {"n": 2, "start": 6.0, "end": 9.0}]
    assert weak_sentences(ctx, sents) == {1, 2}


def test_business_profile_has_the_qash_look():
    ctx = RunContext.create("Video1", root=PROJECT_ROOT)
    brand = ctx.section("brand")
    assert brand["accent"] == "#19fe5b"
    assert (brand["chapterStyle"], brand["statStyle"], brand["graphicsStyle"]) == ("numbered", "bare", "pizarra")
    # stock only as the last resort (05-10: without it, 80-95 % of the shots ended as chalkboards); never generated
    assert ctx.section("fallback")["pexels"] is True and ctx.section("fallback")["generate"] is False
    images = ctx.section("sourcing")["images"]
    assert not any(images[k]["enabled"] for k in ("wikimedia", "openverse", "pixabay")) and images["web"]["enabled"]
    timeline = ctx.section("timeline")
    assert timeline["narrow_layout"] == "archive" and timeline["pizarra"] is True
    assert ctx.section("graphics")["cover_weak"] is True
    note = ctx.section("planner")["shots_note"]
    assert "telediario" in note and "stat" in note
    gym = RunContext.create("_t", root=PROJECT_ROOT, channel="gimnasia")
    assert not gym.section("timeline").get("pizarra") and gym.section("fallback")["pexels"] is True


def test_graphics_prompt_marks_weak_sentences(monkeypatch):
    seen = {}

    def fake(ctx, **kw):
        seen.update(kw)
        return {"graphics": []}

    monkeypatch.setattr(graphics, "complete_json", fake)
    ctx = RunContext.create("_t", root=PROJECT_ROOT, channel="negocios")
    sents = [{"n": i, "start": 30.0 * i, "end": 30.0 * i + 5, "text": f"frase {i}"} for i in range(6)]
    graphics.plan(ctx, sents, 180, weak={2})
    assert "⚠ frase 2" in seen["user"] and "⚠ frase 1" not in seen["user"]
    assert graphics.WEAK_HINT in seen["system"]


def test_empty_shots_in_a_row_share_one_card_with_the_whole_sentence():
    shots = [_shot(0, media=False), _shot(1, media=False), _shot(2)]
    shots[0] = shots[0].model_copy(update={"text": "Estuvo"})
    shots[1] = shots[1].model_copy(update={"text": "bajo su tutela durante años"})
    boards = chalkboards(shots, [], 30)
    assert len(boards) == 1 and boards[0].from_ == shots[0].from_
    assert boards[0].durationInFrames == shots[0].durationInFrames + shots[1].durationInFrames
    assert " ".join(boards[0].graphic["lines"]) == "Estuvo bajo su tutela durante años"


def test_empty_shots_borrow_far_away_footage_and_flash_their_key_words():
    from pipeline.timeline import fill_empty_shots, punch_words

    assert punch_words("Solo uno de esos oros se vendió por 176.321 dólares") == "176.321 dólares"
    assert punch_words("La mujer") == ""                                    # nothing striking: just footage
    shots = [_shot(i) for i in range(6)]
    shots[4] = shots[4].model_copy(update={"media": None, "text": "Le llamaban el Gorrión de Minsk"})
    shots[5] = shots[5].model_copy(update={"media": None, "text": "y lo sabía"})
    punches = fill_empty_shots(shots, [], 30)
    assert shots[4].media is not None and shots[4].media.zoom and shots[5].media is not None
    assert shots[4].media.src == shots[0].media.src                          # the clip farthest away in time
    assert len(punches) == 1 and punches[0].graphic["lines"] == ["Gorrión de Minsk"]
    assert punches[0].from_ == shots[4].from_ and punches[0].durationInFrames <= 66


def test_punch_words_never_join_two_sentences():
    from pipeline.timeline import punch_words

    assert punch_words("con el mismo objetivo. Veamos cómo") != "objetivo Veamos"
    assert "Imagina" not in punch_words("Nadie quiere mejorar nada. Imagina a un cliente cualquiera.")
