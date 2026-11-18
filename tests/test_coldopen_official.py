"""coldopen.analysed_options: the title filter with content.official_channels (17-11: a NameError there stopped
every footage video in the «apertura» stage for a whole night)."""

from __future__ import annotations

from pipeline import coldopen
from pipeline.context import RunContext
from tests.test_fallback_pool import _shot, _write


def _ctx(tmp_path, official: bool) -> RunContext:
    (tmp_path / "config.yaml").write_text("judge:\n  min_accept: 0.22\n" + (
        "content:\n  official_channels: [c]\n" if official else ""))
    return RunContext.create("v", root=tmp_path)


def test_analysed_options_runs_and_lets_official_channels_through(tmp_path):
    ctx = _ctx(tmp_path, official=False)
    shot = _shot(1, [])
    _write(ctx, ".", shot.id, [("v1", "GTA 6 Official Trailer"), ("v2", "Miami Beach drone 4K")])
    found = coldopen.analysed_options(ctx, [shot], [], set(), None, set())
    assert [sel.candidateId for sel, _ in found] == ["v2"]           # «gta»: blocked by default

    ctx = _ctx(tmp_path, official=True)                              # channel «c» official: the trailer comes in
    found = coldopen.analysed_options(ctx, [shot], [], set(), None, set())
    assert {sel.candidateId for sel, _ in found} == {"v1", "v2"}
