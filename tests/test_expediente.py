"""«Material primero», stage 1: research and the case file. API, subtitles and model simulated."""

import json

from pipeline import expediente
from pipeline.context import RunContext

VIDEOS = {
    "orig1": {"title": "Dallas police chase dashcam footage", "channel": "Dallas PD", "views": 900_000},
    "news1": {"title": "Long police chase ends in crash", "channel": "WFAA News", "views": 300_000},
    "top1": {"title": "Top 10 craziest police chases", "channel": "Clips", "views": 9_000_000},
    "doc1": {"title": "The longest chase: documentary", "channel": "Docs", "views": 50_000},
}


class API:
    def __init__(self):
        self.searches = []

    def quota(self):
        return {"left": 100_000}

    def search(self, q, order="", language="", max_results=15, days=0):
        self.searches.append((q, language))
        return list(VIDEOS)

    def videos(self, ids):
        return [{"id": i, "duration": 600, "live": "none", "description": "Officer Mike Ramos talks about the chase.",
                 **VIDEOS[i]} for i in ids if i in VIDEOS]


class YouTube:
    def __init__(self, folder):
        self.folder = folder

    def subtitle_file(self, video_id, lang):
        if video_id == "doc1" or lang != "en":
            return None
        path = self.folder / f"{video_id}.vtt"
        path.write_text("WEBVTT\n\n00:00:10.000 --> 00:00:14.000\nget out of the car now\n\n"
                        "00:00:14.000 --> 00:00:18.000\nit felt like a formula one track\n")
        return path


def ask(system, user):
    if "«material primero»" in system:
        return {"items": [{"n": 1, "name": "Persecución de Dallas", "language": "en", "queries": ["dallas chase dashcam"]}]}
    return {"event_match": 0.9, "segments": [
        {"start": 10, "end": 14, "type": "declaracion", "seen": "agente junto al coche",
         "speaker": {"name": "Mike Ramos", "role": "policía", "evidence": "descripción", "confidence": 0.8}},
        {"start": 14, "end": 18, "type": "declaracion", "seen": "conductor",
         "speaker": {"name": "John Smith", "role": "protagonista", "evidence": "deducido", "confidence": 0.9}},
        {"start": 0, "end": 40, "type": "secuencia", "seen": "persecución desde el helicóptero"},
        {"start": 50, "end": 50.5, "type": "secuencia"}]}


def test_whoever_filmed_it_comes_before_whoever_summarizes_it():
    videos = [{"id": k, "duration": 600, "description": "", **v} for k, v in VIDEOS.items()]
    picked = expediente.pick_sources(videos, 3, set())
    assert [v["id"] for v in picked] == ["orig1", "news1", "doc1"] and "top1" not in [v["id"] for v in picked]


def test_a_name_stays_only_if_the_source_has_it_and_the_sentence_is_read_from_the_subtitles():
    words = [("get", 10, 11), ("out", 11, 12), ("of", 12, 13), ("the", 13, 13.5), ("car", 13.5, 14)]
    segs = expediente.clean_segments(ask("x", ""), words, {"title": "chase", "description": "Officer Mike Ramos"}, 600)
    statement = segs[0]
    assert statement["speaker"]["name"] == "Mike Ramos" and statement["said"] == "get out of the car"
    assert len(segs) == 2                     # the second statement has no subtitles there; the 0.5 s sequence is out
    nameless = expediente.clean_segments(ask("x", ""), words + [("it", 14.5, 15), ("felt", 15, 16)],
                                         {"title": "chase", "description": ""}, 600)
    invented = next(s for s in nameless if s["start"] == 14)
    assert invented["speaker"]["name"] is None and invented["speaker"]["role"] == "protagonista"
    assert invented["speaker"]["droppedName"] == "John Smith"           # «John Smith» is said nowhere in the source


def test_the_case_file_of_a_top_with_its_sources_segments_and_summary(tmp_path):
    (tmp_path / "config.yaml").write_text("material_first: {sources_per_item: 3, keep_for_queue: 0}\n")
    ctx = RunContext.create("top3", root=tmp_path)
    api = API()
    result = expediente.build(ctx, "Top persecuciones más largas", count=1, api=api, youtube=YouTube(tmp_path), ask=ask)
    item = result["items"][0]
    assert [s["id"] for s in item["sources"]] == ["orig1", "news1", "doc1"] and api.searches == [("dallas chase dashcam", "en")]
    orig = item["sources"][0]
    assert orig["subtitles"] == "en" and orig["eventMatch"] == 0.9
    assert orig["segments"][0]["said"] == "get out of the car now" and orig["segments"][0]["speaker"]["name"] == "Mike Ramos"
    assert orig["segments"][1]["speaker"]["name"] is None                     # «John Smith» is in no source text
    assert "sin subtítulos" in item["sources"][2]["note"]                   # the documentary: no captions
    assert result["summary"]["items"][0]["statements"] == 4 and result["apiUnits"] == 102
    assert json.loads((ctx.work_dir / expediente.OUTPUT).read_text())["kind"] == "top"


def test_a_material_first_video_is_created_listed_and_never_taken_by_the_normal_queue(tmp_path):
    import pytest

    from main import pending_slugs

    (tmp_path / "config.yaml").write_text("{}\n")
    (tmp_path / "canales").mkdir()
    (tmp_path / "canales" / "sucesos.yaml").write_text("{}\n")
    (tmp_path / "materiales" / "sucesos").mkdir(parents=True)
    (tmp_path / "materiales" / "sucesos" / "config.yaml").write_text("canal: sucesos\n")
    slug = expediente.create(tmp_path, "Top 3 persecuciones más largas", "sucesos", "top", 3, 6,
                             links=["https://youtu.be/orig1aaaaaa"])
    assert slug == "top-3-persecuciones-mas-largas"
    listed = expediente.videos(tmp_path)
    assert listed[0]["slug"] == slug and listed[0]["count"] == 3 and listed[0]["expediente"] is False
    assert slug not in pending_slugs(tmp_path)                       # no script, no voice: not the normal mode's
    with pytest.raises(ValueError, match="tipo"):
        expediente.create(tmp_path, "Otro título largo", kind="poema")


def test_each_video_remembers_its_way_in_and_experiments_compare_the_ways(tmp_path):
    import yaml

    from pipeline import experimentos, web

    (tmp_path / "config.yaml").write_text("{}\n")
    (tmp_path / "canales").mkdir()
    (tmp_path / "canales" / "gimnasia.yaml").write_text("{}\n")
    web.create_video(tmp_path, {"name": "conguion", "channel": "gimnasia", "script": "Hola. " * 60, "modo": "guion"})
    web.create_video(tmp_path, {"name": "contitulo", "channel": "gimnasia", "script": "Hola. " * 60, "modo": "titulo"})
    web.create_video(tmp_path, {"name": "sinmodo", "channel": "gimnasia", "script": "Hola. " * 60, "modo": "raro"})
    slug = expediente.create(tmp_path, "Top 3 persecuciones largas", kind="top", count=3)
    ways = {s: experimentos.tried(tmp_path, s, {}).get("Camino") for s in ("conguion", "contitulo", "sinmodo", slug)}
    assert ways == {"conguion": "con mi guion", "contitulo": "desde un título", "sinmodo": None, slug: "material primero"}
    assert yaml.safe_load((tmp_path / "materiales" / slug / "config.yaml").read_text())["modo"] == "material"


def test_a_material_first_video_is_not_shown_as_missing_its_script_or_voice(tmp_path):
    from pipeline import web

    (tmp_path / "config.yaml").write_text("{}\n")
    slug = expediente.create(tmp_path, "Top 5 momentos más épicos de la gimnasia", kind="top", count=5)
    status = web.video_summary(tmp_path, tmp_path / "materiales" / slug, {})["status"]
    assert status == "material primero"                       # not «incompleto: falta guion o voz»


def test_without_api_searches_left_the_case_file_searches_with_yt_dlp(tmp_path):
    from pipeline.ytapi import NoKeysLeft

    (tmp_path / "config.yaml").write_text("material_first: {keep_for_queue: 0}\n")
    ctx = RunContext.create("top1", root=tmp_path)

    class NoSearches(API):
        def search(self, q, **kw):
            raise NoKeysLeft("Cuota diaria de la API agotada")

    class YtDlp(YouTube):
        def search(self, q):
            return [{"id": "orig1"}, {"id": "news1"}]

    result = expediente.build(ctx, "Top persecuciones", count=1, api=NoSearches(), youtube=YtDlp(tmp_path), ask=ask)
    assert [s["id"] for s in result["items"][0]["sources"]] == ["orig1", "news1"]
    assert any("yt-dlp" in n for n in result["notes"])
