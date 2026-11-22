"""Recommendations that learn (part 5)."""

import json
from datetime import datetime, timedelta, timezone

from pipeline import aprender


def _root(tmp_path):
    (tmp_path / "config.yaml").write_text("{}\n")
    (tmp_path / "canales").mkdir()
    return tmp_path


def test_after_30_days_and_ten_videos_the_prediction_meets_what_happened(tmp_path):
    root = _root(tmp_path)
    (root / "canales" / "mapas.yaml").write_text("dubbing: {channels: {de: mapas-de}}\n")
    aprender.record(root, [{"kind": "doblar", "channel": "mapas", "lang": "de", "score": 7, "demand": 50_000}],
                    today="2026-09-01")
    now = datetime(2026, 11, 22, tzinfo=timezone.utc)
    (root / "out" / "_canal").mkdir(parents=True)
    young = [{"published": (now - timedelta(days=d)).isoformat(), "short": False} for d in range(5)]
    (root / "out" / "_canal" / "mapas-de.json").write_text(json.dumps({"videos": young, "numbers": {"medianLong": 9_000}}))
    assert aprender.report(root, now)[0]["verdict"].startswith("aún sin datos")
    old = [{"published": (now - timedelta(days=40 - d)).isoformat(), "short": False} for d in range(12)]
    (root / "out" / "_canal" / "mapas-de.json").write_text(json.dumps({"videos": old, "numbers": {"medianLong": 9_000}}))
    row = aprender.report(root, now)[0]
    assert row["target"] == "mapas-de" and row["ratio"] == 0.18 and row["verdict"] == "peor de lo previsto"
