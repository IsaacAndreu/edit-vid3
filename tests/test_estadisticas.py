"""«Estadísticas» (pipeline/estadisticas.py)."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline import estadisticas
from test_agenda import _site, _video


def test_per_video_and_per_channel(tmp_path: Path, monkeypatch):
    root = _site(tmp_path)
    for slug, views in (("n1", 3000), ("n2", 1000), ("n3", None)):
        _video(root, "negocios", slug, published="2026-10-01" if views else None, done=True)
        if views:
            pub = root / "out" / slug / "publicado.json"
            pub.write_text(json.dumps({"at": "2026-10-01T18:00:00", "url": f"https://youtu.be/{slug}xxxxxxxxx"}))
        work = root / "work" / slug
        work.mkdir(parents=True)
        (work / "costs.json").write_text(json.dumps({"totalUsd": 0.8}))
        (work / "timeline.json").write_text(json.dumps({"fps": 30, "durationInFrames": 600 * 30, "shots": []}))
        (root / "out" / slug / "manifest.json").write_text(json.dumps({"shots": [
            {"source": "youtube", "media": "a"}, {"source": "youtube", "media": "b"}, {"source": "pexels", "media": "c"}, {}]}))
    fake = {"n1xxxxxxxxx": {"views": 3000, "likes": 90, "comments": 12, "published": "2026-10-01T18:00:00Z", "thumbnail": "t"},
            "n2xxxxxxxxx": {"views": 1000, "likes": 10, "comments": 1, "published": "2026-10-01T18:00:00Z", "thumbnail": "t"}}
    monkeypatch.setattr(estadisticas, "_youtube", lambda root, ids, refresh: fake)
    r = estadisticas.report(root)
    by = {v["slug"]: v for v in r["videos"]}
    assert by["n1"]["youtube"]["likesPer1k"] == 30.0 and by["n1"]["youtube"]["vsChannel"] == 1.5
    assert "youtube" not in by["n3"] and by["n3"]["production"]["mix"] == {"youtube": 2, "stock": 1, "gráficos": 1}
    assert by["n1"]["production"]["cutsPerMin"] == 0.4 and by["n1"]["production"]["duration"] == 600
    neg = next(c for c in r["channels"] if c["channel"] == "negocios")
    assert neg["views"] == 4000 and neg["median"] == 2000 and neg["published"] == 2 and neg["made"] == 3
    assert neg["best"]["views"] == 3000 and neg["usdPerVideo"] == 0.8
