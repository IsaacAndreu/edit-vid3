"""judge.parar_si_rechaza: a story the judge found no images for stops before the HD downloads and the fill-in."""

import inspect
from types import SimpleNamespace

from pipeline import judge, runner


def _ctx(tmp_path, limit, rejected, total=40):
    from pipeline.schemas import Selection, SelectionFile

    sels = [Selection(shotId=f"s{i:03d}", status="fallback" if i < rejected else "selected", decidedBy="judge",
                      candidateId=None if i < rejected else f"yt:{i:011d}", source=None if i < rejected else "youtube",
                      kind=None if i < rejected else "video", start=None if i < rejected else 1.0,
                      end=None if i < rejected else 3.0, url=None if i < rejected else "u",
                      credit=None if i < rejected else "Fuente: c") for i in range(total)]
    work = tmp_path / "w"
    work.mkdir(parents=True)
    (work / judge.OUTPUT).write_text(SelectionFile(slug="v", selections=sels).model_dump_json(), encoding="utf-8")
    import json

    return SimpleNamespace(section=lambda name: {"parar_si_rechaza": limit} if name == "judge" else {}, work_dir=work,
                           read_json=lambda name: json.loads((work / name).read_text("utf-8")))


def test_off_by_default(tmp_path):
    assert judge.too_rejected(_ctx(tmp_path, 0, 39)) is None


def test_stops_when_most_shots_were_rejected_and_says_how_to_go_on(tmp_path):
    message = judge.too_rejected(_ctx(tmp_path, 60, 30))
    assert message and "30 de 40" in message and "parar_si_rechaza: 0" in message


def test_goes_on_below_the_limit_or_with_few_shots(tmp_path):
    assert judge.too_rejected(_ctx(tmp_path / "a", 60, 20)) is None
    assert judge.too_rejected(_ctx(tmp_path / "b", 60, 9, total=10)) is None


def test_the_runner_checks_before_the_hd_downloads():
    source = inspect.getsource(runner)
    assert source.index('if stage.name == "ingest":') < source.index("budget.check_proxy(ctx.root")
