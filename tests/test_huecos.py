"""«Huecos» (pipeline/huecos.py): demand against competition."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from pipeline import huecos


def _iso(days: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


class FakeAPI:
    def __init__(self, recent: int, big: bool = False):
        self.recent, self.big, self.calls = recent, big, []

    def search(self, query, *, days=0, order="viewCount", language="", max_results=50, **_):
        self.calls.append((query, days, order, language))
        if language == "en":
            return [f"en{i}" for i in range(10)]
        if order == "date":
            return [f"r{i}" for i in range(self.recent)]
        return [f"t{i}" for i in range(10)] if days else [f"a{i}" for i in range(5)]

    def videos(self, ids):
        out = []
        for i in ids:
            views = {"e": 900_000, "t": 120_000, "a": 300_000, "r": 2_000}[i[0]]
            out.append({"id": i, "title": "desastres de ingeniería: el puente" if i[0] == "r" else "x", "description": "",
                        "channelId": "big" if self.big else ("small" if i.endswith(("1", "2")) else "mid"),
                        "channel": "c", "views": views, "duration": 600, "published": _iso(3 * 365 if i[0] == "a" else 100),
                        "thumbnail": "", "url": "u"})
        return out

    def channels(self, ids):
        subs = {"small": 8_000, "mid": 200_000, "big": 3_000_000}
        return [{"id": i, "subscribers": subs[i]} for i in ids]


def test_little_competition_and_english_gap_make_a_hueco(monkeypatch):
    monkeypatch.setattr(huecos, "suggestions", lambda q, language="es": 7)
    m = huecos.measure(FakeAPI(recent=3), "desastres de ingeniería", "engineering disasters")
    assert m["demand"] == 120_000 and m["recent"] == 3 and m["smallWins"] == 2 and m["englishGap"] == 7.5
    assert m["verdict"] == "hueco" and m["score"] >= 6.5 and m["searched"] == 7


def test_a_crowded_topic_of_big_channels_is_saturated(monkeypatch):
    monkeypatch.setattr(huecos, "suggestions", lambda q, language="es": None)
    m = huecos.measure(FakeAPI(recent=45, big=True), "desastres de ingeniería", "")
    assert m["verdict"] == "saturado" and m["bigShare"] == 1.0 and m["smallWins"] == 0


def test_a_topic_you_type_is_measured_and_kept_with_history(tmp_path: Path, monkeypatch):
    import shutil

    repo = Path(__file__).parents[1]
    shutil.copy(repo / "config.yaml", tmp_path / "config.yaml")
    shutil.copytree(repo / "canales", tmp_path / "canales")
    monkeypatch.setattr(huecos, "suggestions", lambda q, language="es": 3)
    monkeypatch.setattr("pipeline.llm.complete_json", lambda ctx, **kw: {
        "name": "Desastres de ingeniería", "query_es": "desastres de ingeniería", "query_en": "engineering disasters",
        "fit": 9, "why": "poco en español", "ideas": ["El puente que bailaba"]})
    first = huecos.evaluate(tmp_path, "desastres de ingeniería", api=FakeAPI(recent=3))
    assert first["origin"] == "manual" and first["fit"] == 9 and len(first["history"]) == 1
    ranked = huecos.ranked(tmp_path)
    assert ranked[0]["name"] == "Desastres de ingeniería"
    lines = huecos.telegram_lines([{**first, "new": True}])
    assert "Desastres de ingeniería" in lines[0] and "El puente que bailaba" in lines[0]
