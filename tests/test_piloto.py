"""The scene-search pilot: only one video, its own config, the API quota check and the real-run report."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from pipeline import piloto


def _project(root: Path) -> None:
    (root / "config.yaml").write_text("canal: gimnasia\nsourcing:\n  youtube: {min_interval: 0}\n")
    (root / "canales").mkdir()
    (root / "canales" / "gimnasia.yaml").write_text("format: historia\n")
    for slug in ("piloto1", "otro"):
        (root / "materiales" / slug).mkdir(parents=True)
        (root / "materiales" / slug / "guion.txt").write_text("texto")


def _finished(root: Path, slug: str, sources: list[str | None], *, scene: bool = False, requests: dict | None = None,
              labels: dict | None = None) -> None:
    work = root / "work" / slug
    (work / "candidates").mkdir(parents=True)
    selections = [{"shotId": f"s{i + 1:03d}", "status": "selected" if s else "fallback", **({"candidateId": s} if s else {})}
                  for i, s in enumerate(sources)]
    (work / "selection.json").write_text(json.dumps({"selections": selections}))
    (work / "diag.json").write_text(json.dumps({
        "juez": {"shots": len(sources), "fallback": sources.count(None)}, "planos_flojos": 1,
        "etapas": {"sourcing": {"segundos": 600}, "render": {"segundos": 300}}}))
    (work / "candidates" / "_summary.json").write_text(json.dumps({"sceneSearch": scene}))
    rows = [{"action": action, "ok": True} for action, n in (requests or {}).items() for _ in range(n)]
    (work / "youtube_downloads.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    if labels:
        path = root / "out" / "_errores" / "etiquetas.json"
        from pipeline import feedback

        path = root / feedback.LABELS
        path.parent.mkdir(parents=True, exist_ok=True)
        old = json.loads(path.read_text()) if path.is_file() else {}
        old.update({f"{slug}/{k}": {"verdict": v} for k, v in labels.items()})
        path.write_text(json.dumps(old))


def test_only_that_video_gets_the_scene_search_and_it_comes_off_cleanly(tmp_path):
    _project(tmp_path)
    _finished(tmp_path, "otro", ["yt:a"])
    config = tmp_path / "materiales" / "piloto1" / "config.yaml"
    config.write_text("timeline: {moments: 0}\n")
    with pytest.raises(ValueError, match="a mano"):              # the reference is chosen by hand
        piloto.enable(tmp_path, "piloto1")
    done = piloto.enable(tmp_path, "piloto1", reference="otro")
    assert done["reference"] == "otro"
    written = yaml.safe_load(config.read_text())
    assert written["sourcing"]["youtube"] == {"scene_search": True, "api_overflow": "esperar"}
    assert written["judge"] == {"variety_margin": 0.02} and written["timeline"] == {"moments": 0}
    from pipeline.context import RunContext

    assert RunContext.create("piloto1", root=tmp_path).section("sourcing")["youtube"]["scene_search"] is True
    assert not RunContext.create("otro", root=tmp_path).section("sourcing")["youtube"].get("scene_search")
    with pytest.raises(ValueError, match="Ya hay un piloto"):   # one new documentary only
        piloto.enable(tmp_path, "otro")
    piloto.disable(tmp_path, "piloto1")
    assert yaml.safe_load(config.read_text()) == {"timeline": {"moments": 0}}
    with pytest.raises(ValueError, match="terminado"):
        piloto.enable(tmp_path, "piloto1", reference="nada")


def test_report_compares_the_real_runs_and_asks_for_the_human_review(tmp_path):
    _project(tmp_path)
    _finished(tmp_path, "otro", ["yt:a", "yt:b", "yt:c", "yt:d"], requests={"metadata": 40, "download": 20, "search": 30},
              labels={"s001": "correcta", "s002": "incorrecta"})
    _finished(tmp_path, "piloto1", ["yt:a", "yt:a", "yt:b", None], scene=True, requests={"metadata": 20, "download (HLS)": 18},
              labels={"s001": "correcta"})
    piloto.enable(tmp_path, "piloto1", reference="otro")
    result = piloto.report(tmp_path, "piloto1")
    rows = {r["label"]: r for r in result["rows"]}
    assert rows["Peticiones: extracciones (por 100 planos)"] == {"label": "Peticiones: extracciones (por 100 planos)",
                                                                 "reference": 1000.0, "pilot": 500.0, "better": True}
    assert rows["Peticiones: descargas (por 100 planos)"]["pilot"] == 450.0
    assert rows["Fuentes repetidas"]["better"] is False and rows["Misma fuente en planos seguidos (por 100 planos)"]["pilot"] == 25.0
    assert rows["Planos sin metraje aprovechable (relleno) (por 100 planos)"]["pilot"] == 25.0
    assert rows["Revisión humana: correcta (proporción)"]["pilot"] == 1.0
    assert any("30 clips" in p for p in result["pending"])
    assert (tmp_path / "out" / "piloto1" / "piloto.md").read_text().startswith("# Piloto por escenas: piloto1 frente a otro")


def test_scene_search_waits_for_api_quota_instead_of_scraping(tmp_path):
    from pipeline.budget import ApiSearchesShort, BudgetReached
    from pipeline.sourcing import check_api_searches
    from tests.test_scenes import YULO, _broll, _plan

    plan = _plan([[_broll(YULO, YULO, q) for q in ("vault landing replay", "rings strength hold", "parallel bars dismount")]])

    class Api:
        def __init__(self, left):
            self.left = left

        def quota(self):
            return {"searchesLeft": self.left}

    class YouTube:
        api = Api(1)

        def search_cached(self, query):
            return query == YULO                            # already on disk: costs nothing

    cfg = {"scene_extra_queries": 3, "api_scene_extra_queries": 2, "queries_en": 2}
    check_api_searches(YouTube(), [plan.shots], {**cfg, "api_overflow": "ytdlp"})   # only if asked: rest by yt-dlp
    with pytest.raises(ApiSearchesShort) as raised:
        check_api_searches(YouTube(), [plan.shots], {**cfg, "api_overflow": "esperar"})
    assert isinstance(raised.value, BudgetReached) and "necesita 2" in str(raised.value)
    YouTube.api = Api(2)
    check_api_searches(YouTube(), [plan.shots], {**cfg, "api_overflow": "esperar"})       # enough: goes on


def test_the_review_must_cover_the_whole_documentary(tmp_path):
    _project(tmp_path)
    _finished(tmp_path, "otro", ["yt:a"] * 4)
    early = {f"s{i:03d}": "correcta" for i in range(1, 31)}            # 30 clips, all from the opening
    _finished(tmp_path, "piloto1", [f"yt:{i}" for i in range(120)], scene=True, labels=early)
    result = piloto.report(tmp_path, "piloto1", reference="otro")
    assert result["pilot"]["reviewedByQuarter"] == [30, 0, 0, 0]
    assert any("cada cuarto" in p for p in result["pending"]) and not any("30 clips" in p for p in result["pending"])
    spread = {f"s{i:03d}": "correcta" for i in range(1, 121, 4)}       # 30 spread over the four quarters
    (tmp_path / "out" / "_errores" / "etiquetas.json").unlink()
    _finished_labels = {f"piloto1/{k}": {"verdict": v} for k, v in spread.items()}
    (tmp_path / "out" / "_errores" / "etiquetas.json").write_text(json.dumps(_finished_labels))
    assert piloto.report(tmp_path, "piloto1", reference="otro")["pending"] == []


def test_mid_run_the_last_api_search_stops_the_pilot_instead_of_scraping(tmp_path):
    from pipeline.budget import ApiSearchesShort
    from pipeline.sourcing.youtube import YouTubeSource
    from pipeline.ytapi import NoKeysLeft

    class EmptyApi:
        def search(self, *a, **k):
            raise NoKeysLeft("Límite diario de búsquedas de la API (100) alcanzado")

    scraped = []
    for overflow, expected in (("esperar", ApiSearchesShort), ("ytdlp", None)):
        yt = YouTubeSource(root=tmp_path, cache_dir=tmp_path / overflow, config={"min_interval": 0, "api_overflow": overflow})
        yt.api = EmptyApi()
        yt._call = lambda action, fn, **k: scraped.append(action) or {"entries": []}
        if expected:
            with pytest.raises(expected):
                yt.search_pool(["a query"], [])
            assert scraped == []                             # checked before the call: nothing went to yt-dlp
        else:
            assert yt.search_pool(["a query"], []) == ([[]], {}) and scraped == ["search"]
