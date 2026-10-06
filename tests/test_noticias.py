"""«Noticias del día» (pipeline/noticias.py)."""

from __future__ import annotations

from datetime import datetime, timezone

from pipeline import noticias

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)


def _v(i, title, channel, views, hours_ago):
    published = datetime.fromtimestamp(NOW.timestamp() - hours_ago * 3600, timezone.utc).isoformat().replace("+00:00", "Z")
    return {"id": f"v{i}", "title": title, "channel": channel, "views": views, "published": published, "duration": 600,
            "live": "none", "thumbnail": "t", "url": "u", "description": f"desc {i}"}


class FakeAPI:
    def __init__(self, videos):
        self.items = videos

    def search(self, query, **kw):
        return [v["id"] for v in self.items]

    def videos(self, ids):
        return [v for v in self.items if v["id"] in ids]


def test_stories_group_by_shared_names_and_rank_by_speed():
    items = [_v(1, "CHRISTA PIKE: La MUJER que fue EJECUTADA Dos Veces", "Magnus", 400_000, 20),
             _v(2, "Christa Pike sobrevive a inyección letal", "Milenio", 200_000, 30),
             _v(3, "GYPSY ROSE: Su novio MURIÓ HOY", "Magnus", 100_000, 10),
             _v(4, "Gypsy Rose y Ken Urker", "Telemundo", 20_000, 12),
             _v(5, "Una receta de cocina", "Chef", 900_000, 40),          # alone: not a story
             _v(6, "Christa Pike en 1995", "Viejo", 900_000, 24 * 30)]     # too old
    found = []
    for q in ("x",):
        found += noticias.search(FakeAPI(items), q, 48, 1000, NOW)
    assert {v["id"] for v in found} == {"v1", "v2", "v3", "v4", "v5"}
    stories = noticias.group(found)
    assert [s["name"] for s in stories] == ["Christa Pike", "Gypsy Rose"]
    assert stories[0]["channels"] == 2 and stories[0]["videos"][0]["id"] == "v1"
    idea = noticias.idea_for(stories[0])
    assert idea["format"] == "caso-real" and "desc 1" in idea["note"] and "[COMPROBAR]" in idea["note"]


def test_niches_are_discovered_from_small_channels_outliers(tmp_path, monkeypatch):
    from datetime import date

    from pipeline import lab, radar
    from pipeline.context import RunContext

    (tmp_path / "config.yaml").write_text("canal: ''\n", encoding="utf-8")
    ctx = RunContext.create("_radar", root=tmp_path)
    asked = []

    def outliers(ctx, query, **kw):
        asked.append(query)
        assert kw["max_subs"] == 100_000 and kw["min_ratio"] == 3
        return [{"id": f"{query}-{i}", "title": f"Ejecuciones fallidas {i}", "channel": "Peque", "views": 50_000 * i,
                 "ratio": 5.0 + i, "subscribers": 20_000, "thumbnail": "t", "url": "u", "published": "", "duration": 600}
                for i in range(2)]

    monkeypatch.setattr(lab, "outliers", outliers)
    seen = {}

    def fake(ctx, **kwargs):
        seen.update(kwargs)
        ids = [line.split(" · ")[0] for line in kwargs["user"].split("VÍDEOS QUE FUNCIONAN:\n")[1].splitlines()]
        return {"niches": [{"name": "Pena de muerte", "query": "ejecuciones fallidas", "why": "x", "videos": ids[:2]}]}

    monkeypatch.setattr("pipeline.llm.complete_json", fake)
    found = radar.discover(ctx, None, {"discovery_per_day": 2}, ["true crime"], date(2026, 10, 6))
    assert len(asked) == 2 and len(set(asked)) == 2
    assert found[0]["query"] == "ejecuciones fallidas" and len(found[0]["found"]) == 2
    assert "true crime" in seen["user"]
    other = []
    monkeypatch.setattr(lab, "outliers", lambda ctx, q, **kw: other.append(q) or [])
    radar.discover(ctx, None, {"discovery_per_day": 2}, [], date(2026, 10, 7))
    assert set(other).isdisjoint(asked)                                   # another day, other searches
