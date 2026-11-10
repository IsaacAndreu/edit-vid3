import json

from pipeline import datacheck
from pipeline.context import RunContext

SENTS = [{"text": "Uchimura ganó 10 oros mundiales.", "start": 10.0, "end": 14.0},
         {"text": "Yulo nació en 2000 en Manila.", "start": 20.0, "end": 24.0}]


def planned():
    return [{"start": 10.0, "end": 14.0, "graphic": {"type": "specs", "name": "Kohei Uchimura",
                                                    "rows": [{"label": "Oros mundiales", "value": "10"}]}},
            {"start": 20.0, "end": 24.0, "graphic": {"type": "card", "name": "Carlos Yulo", "value": "2000"}},
            {"start": 30.0, "end": 32.0, "graphic": {"type": "quote", "text": "sin datos"}}]


def make(tmp_path, monkeypatch, verdicts, claims=()):
    ctx = RunContext.create("t", root=tmp_path, config={})
    ctx.work_dir.mkdir(parents=True, exist_ok=True)
    (ctx.work_dir / "factcheck.json").write_text(json.dumps({"articles": [], "claims": list(claims)}), "utf-8")
    calls = []
    monkeypatch.setattr("pipeline.factcheck.web_snippets",
                        lambda ctx, q, count=5: [{"title": "Yulo", "snippet": "Carlos Yulo was born in 2000 in Manila", "url": "u"}])

    def judge(ctx, **kw):
        calls.append(kw["user"])
        return {"results": verdicts}

    monkeypatch.setattr(datacheck, "complete_json", judge)
    return ctx, calls


def test_wrong_needs_a_verbatim_quote(tmp_path, monkeypatch):
    ctx, _ = make(tmp_path, monkeypatch, [
        {"n": 1, "verdict": "wrong", "quote": "won six all-around titles", "correction": "6"},   # not in the evidence
        {"n": 2, "verdict": "wrong", "quote": "Carlos Yulo was born in 2000", "correction": "x"}])
    kept = datacheck.filter_planned(ctx, planned(), SENTS)
    assert [p["graphic"]["type"] for p in kept] == ["specs", "quote"]
    results = json.loads((ctx.work_dir / "datacheck.json").read_text("utf-8"))["results"]
    assert [r["verdict"] for r in results] == ["unverified", "wrong"]
    assert "❌ quitado" in (ctx.out_dir / "datos-graficos.md").read_text("utf-8")


def test_factcheck_wrong_drops_without_judge_and_cache(tmp_path, monkeypatch):
    claim = {"verdict": "wrong", "quote": "Uchimura ganó 10 oros mundiales", "claim": "c", "correction": "fueron 6"}
    ctx, calls = make(tmp_path, monkeypatch, [{"n": 2, "verdict": "ok"}], claims=[claim])
    kept = datacheck.filter_planned(ctx, planned(), SENTS)
    assert [p["graphic"]["type"] for p in kept] == ["card", "quote"] and len(calls) == 1
    assert "1. [specs]" not in calls[0]                        # judged by the script's fact check already
    datacheck.filter_planned(ctx, planned(), SENTS)
    assert len(calls) == 1                                     # same graphics → cached verdicts


def test_overlap_and_switch(tmp_path, monkeypatch):
    assert datacheck._overlaps("ganó 10 oros mundiales", "Uchimura ganó 10 oros mundiales en su carrera.")
    assert not datacheck._overlaps("nació en 1989", "Uchimura ganó 10 oros mundiales.")
    ctx = RunContext.create("t", root=tmp_path, config={"graphics": {"verify": False}})
    assert datacheck.filter_planned(ctx, planned(), SENTS) == planned()
