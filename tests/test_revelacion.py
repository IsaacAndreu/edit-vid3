"""«Canales revelación» (pipeline/revelacion.py)."""

from __future__ import annotations

from datetime import date

from pipeline import revelacion


class FakeAPI:
    def __init__(self):
        self.searched = []

    def search(self, query, **kw):
        self.searched.append(query)
        return ["v1", "v2", "v3", "v4"]

    def videos(self, ids):
        rows = {"v1": ("c1", 900_000, 700), "v2": ("c2", 50_000, 700), "v3": ("c3", 2_000_000, 700), "v4": ("c4", 400_000, 40)}
        return [{"id": i, "title": f"vídeo {i}", "channelId": rows[i][0], "views": rows[i][1], "duration": rows[i][2],
                 "thumbnail": "t", "url": "u", "published": "2026-09-01T00:00:00Z"} for i in ids if i in rows]

    def channels(self, ids):
        subs = {"c1": 12_000, "c2": 30_000, "c3": 900_000, "c4": 1_000}
        return [{"id": c, "title": f"Canal {c}", "handle": f"@{c}", "subscribers": subs[c], "viewCount": 5_000_000,
                 "videoCount": 20, "created": "2026-05-01T00:00:00Z", "thumbnail": "t", "uploads": f"UU{c}"} for c in ids]

    def uploads(self, playlist, count):
        return [{"title": "La caída de X", "views": 300_000, "duration": 720, "thumbnail": "t", "url": "u"}] * 3


def test_small_channels_with_huge_views_only():
    found = revelacion.candidates(FakeAPI(), ["el caso de"], 60, 50_000, 5)
    assert [c["id"] for c in found] == ["c1"]             # c2: 1.6x · c3: too big · c4: a short
    assert found[0]["multiple"] == 75.0 and found[0]["url"] == "https://www.youtube.com/@c1"


def test_scan_reads_the_format_remembers_and_rotates(tmp_path, monkeypatch):
    (tmp_path / "config.yaml").write_text("canal: ''\n", encoding="utf-8")
    monkeypatch.setattr("pipeline.llm.complete_json", lambda ctx, **kw: {"channels": [
        {"id": "c1", "format": "Casos de empresas que cayeron", "niche": "caídas de empresas", "query": "caída empresa",
         "fit": 9, "why": "x", "how": "un canal de caídas"}]})
    api = FakeAPI()
    first = revelacion.scan(tmp_path, api, date(2026, 10, 7))
    assert first[0]["fit"] == 9 and first[0]["new"] and first[0]["medianViews"] == 300_000
    lines = revelacion.telegram_lines(first)
    assert "🆕 Canal c1" in lines[0] and "encaje 9/10" in lines[0] and "→ un canal de caídas" in lines[0]
    again = revelacion.scan(tmp_path, FakeAPI(), date(2026, 10, 8))
    assert not again[0]["new"] and again[0]["format"] == "Casos de empresas que cayeron"
    other = FakeAPI()
    revelacion.scan(tmp_path, other, date(2026, 10, 9))
    assert set(other.searched) != set(api.searched)
