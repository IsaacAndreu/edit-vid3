"""«Material primero», stages 3, 4 and 6, end to end on a top of three entries: downloads (real little clips made
with ffmpeg), the transcription, the voice and the director simulated; the timeline must validate."""

import json
import shutil
import subprocess

import pytest

from pipeline import montaje_mf
from pipeline.context import RunContext
from pipeline.schemas import Timeline

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg")


def _clip(path, seconds, tone=440):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    f"testsrc=s=320x180:r=30:d={seconds}", "-f", "lavfi", "-i", f"sine=frequency={tone}:duration={seconds}",
                    "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(path)], check=True)
    return path


def _voice(text, target):
    seconds = max(1.0, len(text.split()) / 2.5)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    f"sine=frequency=220:duration={seconds}", str(target)], check=True)
    return target


def _segments(n):
    return {"start": 0, "end": 40, "type": "secuencia", "seen": f"persecución {n}", "said": "", "speaker": None}, \
           {"start": 50, "end": 54, "type": "declaracion", "seen": "agente", "said": f"we chased him for hours number {n}",
            "speaker": {"name": None, "role": "policía", "gender": "mujer" if n == 2 else "hombre", "confidence": 0.7}}


EXPEDIENTE = {"title": "Top 3 persecuciones", "kind": "top", "minutes": 4, "items": [
    {"n": n, "name": f"Caso {n}", "sources": [{"id": f"src{n}", "url": f"u{n}", "channel": f"Canal {n}", "subtitles": "en",
                                                "segments": list(_segments(n))}]} for n in (1, 2, 3)]}


def _blocks():
    out = []
    for n, number in ((1, 3), (2, 2), (3, 1)):
        seq, dec = f"t{2 * n - 1}", f"t{2 * n}"
        out += [{"type": "tarjeta", "item": n, "number": number, "title": f"Caso {n}"},
                {"type": "narrador", "text": f"El caso {n} duró horas y horas por la autopista.", "refs": [seq]},
                {"type": "secuencia", "ref": seq, "source": f"src{n}", "channel": f"Canal {n}", "start": 0, "end": 8,
                 "seen": f"persecución {n}"},
                {"type": "declaracion", "ref": dec, "source": f"src{n}", "channel": f"Canal {n}", "start": 50, "end": 54,
                 "said": f"we chased him for hours number {n}", "lang": "en", "translation": f"Le perseguimos durante horas {n}",
                 "speaker": None, "role": "policía", "gender": "mujer" if n == 2 else "hombre"},
                {"type": "narrador", "text": "Al final lo detuvieron.", "refs": [seq]}]
    return out


@pytest.fixture
def ctx(tmp_path):
    (tmp_path / "config.yaml").write_text("content: {max_third_party_seconds: 45}\nquotes: {min_match: 0.55}\n"
                                          "material_first: {max_mb: 500}\n")
    c = RunContext.create("top3", root=tmp_path)
    c.write_json("expediente.json", EXPEDIENTE)
    c.write_json("bloques.json", {"title": "Top 3 persecuciones", "kind": "top", "blocks": _blocks()})
    return c


def fetch(tmp_path):
    def get(video_id, start, length, target):
        _clip(target, length, 300 + 100 * int(video_id[-1]))
        return {"duration": length, "hasAudio": True}
    return get


def transcribe(path, lang):
    n = path.name.split("-")[1][-1]                          # «003-src1-50.0.mp4»
    said = f"we chased him for hours number {n}" if n != "2" else "something else entirely was said here"
    return [(w, i * 0.4, i * 0.4 + 0.3) for i, w in enumerate(said.split())]


def director(system, user):
    assert "puesto 3" not in user                            # the number 1 (entry 3) is never in the hook
    return {"cuts": [{"id": "c2", "from": 1, "seconds": 2.5, "word": "PERSECUCIÓN"}, {"id": "c3", "from": 0, "seconds": 3},
                     {"id": "c99", "from": 0, "seconds": 3}, {"id": "c8", "from": 0, "seconds": 20}]}


def test_a_top_of_three_from_blocks_to_a_valid_timeline_with_hook_and_checked_statements(ctx, tmp_path):
    summary = montaje_mf.run(ctx.root, "top3", fetch_fn=fetch(tmp_path), transcribe=transcribe, speak=_voice,
                             ask=director, render=False, log=lambda *_: None)
    timeline = json.loads((ctx.work_dir / "timeline.json").read_text())
    Timeline.model_validate(timeline)
    assert timeline["locale"]["chapter"] == "PUESTO"
    assert timeline["audio"]["sfx"] == [] and "transitions" in timeline          # the defaults the render reads
    assert summary["statementsChecked"][8] < 0.55 and summary["statementsChecked"][3] >= 0.55   # entry 2's did not match
    quotes = [g for g in timeline["groups"] if g["graphic"]["type"] == "quote" and g["id"].startswith("quote-")]
    assert len(quotes) == 2 and quotes[0]["graphic"]["speaker"] == "agente"                       # the role, no name
    assert quotes[0]["graphic"]["lines"][0]["text"].startswith("Le perseguimos")
    cards = [s for s in timeline["shots"] if s["type"] == "chapter"]
    assert [c.get("chapterNumber") for c in cards] == [None, 3, 2, 1]                              # title, then 3-2-1
    hook = [s for s in timeline["shots"][: timeline["shots"].index(cards[0])]]
    assert len(hook) == 2 and all(s["coldOpen"] for s in hook)                                     # c99/c8 refused
    assert any(g["graphic"]["type"] == "kinetic" and g["graphic"]["lines"] == ["PERSECUCIÓN"] for g in timeline["groups"])
    assert all(s["media"]["credit"].startswith("Fuente: Canal") for s in timeline["shots"] if s.get("media"))
    narr = [s for s in timeline["shots"] if s["type"] == "broll" and not s["coldOpen"]]
    assert narr and timeline["audio"]["speech"] and len(timeline["audio"]["voiceGaps"]) == len(hook) + 4 + 2
    assert summary["seconds"] > 20


def test_statements_dubbed_one_voice_per_person_over_the_original():
    blocks = [{"type": "declaracion", "speaker": None, "role": "testigo", "ref": "t1", "gender": "mujer"},
              {"type": "declaracion", "speaker": "Ana Ruiz", "role": "testigo", "ref": "t2", "gender": "mujer"},
              {"type": "declaracion", "speaker": "Ana Ruiz", "role": "testigo", "ref": "t3", "gender": "mujer"},
              {"type": "declaracion", "speaker": None, "role": "policía", "ref": "t4", "gender": "hombre"}]
    catalogue = {"mujeres": [{"voice_id": "m1"}, {"voice_id": "m2"}], "hombres": [{"voice_id": "h1"}]}
    voices = montaje_mf.dub_voices("por_persona", blocks, catalogue)
    assert [voices[p]["voice_id"] for p in range(4)] == ["m1", "m2", "m2", "h1"]                  # Ana keeps hers
    assert set(v["voice_id"] for v in montaje_mf.dub_voices("una_voz", blocks, {"documental": {"voice_id": "d"}}).values()) == {"d"}
    assert montaje_mf.dub_voices("subtitulo", blocks, catalogue) == {}


def test_too_many_megabytes_stop_before_downloading(ctx, tmp_path):
    big = [{"type": "secuencia", "source": "s", "start": 0, "end": 3000}]
    ctx.write_json("bloques.json", {"title": "x", "kind": "top", "blocks": big})
    with pytest.raises(ValueError, match="max_mb"):
        montaje_mf.run(ctx.root, "top3", fetch_fn=lambda *a: None, render=False)


def test_the_format_is_measured_like_the_reference(ctx, tmp_path):
    from pipeline import medir_video

    montaje_mf.run(ctx.root, "top3", fetch_fn=fetch(tmp_path), transcribe=transcribe, speak=_voice, ask=director,
                   render=False, log=lambda *_: None)
    m = medir_video.from_timeline(json.loads((ctx.work_dir / "timeline.json").read_text()))
    assert m["hookSeconds"] == 5.5 and m["otherVoiceShare"] > 0 and m["sources"] == 3 and m["meanShotSeconds"] > 2


def test_news_and_documentary_get_their_own_structure(ctx):
    from pipeline import bloques

    seen = {}

    def ask(system, user):
        seen["system"] = system
        return {"blocks": []}

    ctx.write_json("expediente.json", {**EXPEDIENTE, "kind": "noticia"})
    bloques.write(ctx, ask=ask)
    assert "Estructura de NOTICIA" in seen["system"] and "ORDEN del top" not in seen["system"]


def test_a_dub_voice_named_by_its_channel_takes_that_channels_whole_voice(tmp_path):
    from pipeline import tts

    (tmp_path / "config.yaml").write_text("{}\n")
    tts.set_voice(tmp_path, "buscandolaverdad", {"voice_id": "Spanish_PowerfulSoldier", "provider": "ai84"})
    voice = montaje_mf.catalogue_voice(tmp_path, {"canal": "buscandolaverdad"})
    assert voice["voice_id"] == "Spanish_PowerfulSoldier" and voice["provider"] == "ai84"
    assert montaje_mf.catalogue_voice(tmp_path, {"voice_id": "abc"})["voice_id"] == "abc"
    with pytest.raises(ValueError, match="no tiene voz"):
        montaje_mf.catalogue_voice(tmp_path, {"canal": "nadie"})
