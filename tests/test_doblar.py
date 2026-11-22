"""What to dub of what is already made (part 2): API and model simulated."""

import json

from pipeline import doblar


class API:
    def __init__(self, demand):
        self.demand, self.searches = demand, []

    def quota(self):
        return {"left": 100_000}

    def search(self, query, days=0, order="", language="", max_results=50):
        self.searches.append(query)
        n = 0 if days == 30 else 6
        return [f"{query}|{language}|{i}" for i in range(n)]

    def videos(self, ids):
        return [{"id": i, "title": i, "channelId": "c", "views": self.demand[i.split("|")[0]], "duration": 600,
                 "published": "2026-06-01T00:00:00Z", "live": "none", "description": "",
                 "audioLanguage": i.split("|")[1]} for i in ids]

    def channels(self, ids):
        return [{"id": i, "subscribers": 1_000_000} for i in ids]


def _video(root, channel, slug, script="Una frase. " * 100):
    folder = root / "materiales" / channel / slug
    folder.mkdir(parents=True)
    (folder / "guion.txt").write_text(script)
    (root / "out" / slug).mkdir(parents=True)
    (root / "out" / slug / "video-final.mp4").write_bytes(b"x")


def _root(tmp_path):
    (tmp_path / "config.yaml").write_text("radar: {idiomas: [es, pt, de], keep_for_queue: 0}\ntts: {usd_per_1k_chars: 0.02}\n")
    (tmp_path / "canales").mkdir()
    (tmp_path / "canales" / "mapas.yaml").write_text(
        "visual: {style: atlas}\nalign: {language: es}\nlab: {queries: [por qué este mapa]}\n")
    (tmp_path / "canales" / "deporte.yaml").write_text(
        "quotes: {count: 2}\nalign: {language: es}\nlab: {queries: [gimnasta]}\ndubbing: {channels: {pt: deporte-br}}\n")
    (tmp_path / "canales" / "deporte-br.yaml").write_text("align: {language: pt}\ndubbing: {enabled: false}\n")
    for channel in ("mapas", "deporte", "deporte-br"):
        (tmp_path / "materiales" / channel).mkdir(parents=True)
        (tmp_path / "materiales" / channel / "config.yaml").write_text(f"canal: {channel}\n")
    for n in range(3):
        _video(tmp_path, "mapas", f"mapa{n}")
    _video(tmp_path, "deporte", "gym1")
    _video(tmp_path, "deporte-br", "gym1-pt")
    (tmp_path / "out" / "_canal").mkdir(parents=True)
    (tmp_path / "out" / "_canal" / "deporte.json").write_text(json.dumps({"numbers": {"medianLong": 10_000}}))
    (tmp_path / "out" / "_canal" / "deporte-br.json").write_text(json.dumps({"numbers": {"medianLong": 1_000}}))
    return tmp_path


def test_dependency_on_the_language():
    assert doblar.dependency({"visual": {"style": "atlas"}})[0] == "ninguna"
    assert doblar.dependency({"quotes": {"count": 2}})[0] == "alta"
    assert doblar.dependency({})[0] == "baja"


def test_dub_this_channel_into_this_language_with_videos_ready_cost_and_the_check(tmp_path):
    root = _root(tmp_path)
    (root / "materiales" / "mapas" / "mapa2" / "voz-pt.mp3").write_bytes(b"x")       # its voice is on its way
    demand = {"por qué este mapa": 100_000, "porque este mapa": 5_000, "warum diese karte": 50_000,
              "gimnasta": 80_000, "ginasta": 4_000, "turnerin": 60_000}
    told = lambda q, langs: {"queries": {"es": q, "pt": {"por qué este mapa": "porque este mapa", "gimnasta": "ginasta"}[q],
                                         "de": {"por qué este mapa": "warum diese karte", "gimnasta": "turnerin"}[q]}}
    result = doblar.compute(root, api=API(demand), translate_fn=told, today="2026-11-22")
    rows = {(r["channel"], r["lang"]): r for r in result["rows"]}
    assert set(rows) == {("mapas", "pt"), ("mapas", "de"), ("deporte", "de")}        # deporte→pt is done; -br is a target
    pt = rows[("mapas", "pt")]
    assert pt["gap"] == 20.0 and pt["dependency"] == "ninguna" and pt["readyCount"] == 2   # mapa2 has its voice coming
    assert pt["cost"] == round(2 * (0.02 * 1000 / 1000 + doblar.API_USD_PER_DUB), 2)
    assert result["rows"][0]["channel"] == "mapas" and result["rows"][0]["lang"] == "de"   # an audience (50k), dubs whole
    assert pt["verdict"] == "sin demanda"                                            # a 20x gap over 5k views is no audience
    assert [r["score"] for r in result["rows"]] == sorted((r["score"] for r in result["rows"]), reverse=True)
    assert rows[("deporte", "de")]["dependency"] == "alta"
    check = result["checks"][0]
    assert check["channel"] == "deporte" and check["lang"] == "pt" and check["dubbedRatio"] == 0.1
    assert check["check"].startswith("nota mal hecha") or check["score"] < 6        # the dubbed channel does badly
    again = doblar.compute(root, api=API({}), translate_fn=told, today="2026-11-30")   # within 14 days: no new searches
    assert again["rows"] and again["measures"]["mapas"]["date"] == "2026-11-22"
