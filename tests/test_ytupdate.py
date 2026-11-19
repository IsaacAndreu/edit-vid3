"""Fase 1.9: a new yt-dlp that does not download here is rolled back and remembered as bad."""

from __future__ import annotations

import json

from pipeline import ytupdate


class Pip:
    def __init__(self, latest: str, current: str):
        self.latest, self.current, self.calls = latest, current, []

    def install(self, *specs):
        self.calls.append(specs)
        pinned = next((s.split("==")[1] for s in specs if s.startswith("yt-dlp==")), None)
        self.current = pinned or self.latest
        return True

    def versions(self):
        return {"yt-dlp": self.current, "yt-dlp-ejs": "0.8.0"}


def test_a_release_that_breaks_downloads_is_rolled_back(tmp_path):
    pip = Pip("2026.12.01", "2026.10.26")
    told = []
    probes = iter([False, True])                       # the new one fails, the old one works
    out = ytupdate.update(tmp_path, install=pip.install, versions=pip.versions, probe=lambda root: next(probes),
                          notify=told.append)
    assert out["rolledBack"] and pip.current == "2026.10.26" and "2026.12.01" in told[0]
    assert json.loads((tmp_path / ytupdate.STATE).read_text())["bad"] == "2026.12.01"
    # the next round: the same bad release is not probed again, it goes straight back
    out = ytupdate.update(tmp_path, install=pip.install, versions=pip.versions,
                          probe=lambda root: (_ for _ in ()).throw(AssertionError("no probe")), notify=told.append)
    assert out["rolledBack"] and pip.current == "2026.10.26"


def test_both_failing_is_youtube_not_the_release(tmp_path):
    pip = Pip("2026.12.01", "2026.10.26")
    out = ytupdate.update(tmp_path, install=pip.install, versions=pip.versions, probe=lambda root: False,
                          notify=lambda t: None)
    assert not out["rolledBack"] and pip.current == "2026.12.01"


def test_no_new_release_no_probe(tmp_path):
    pip = Pip("2026.10.26", "2026.10.26")
    out = ytupdate.update(tmp_path, install=pip.install, versions=pip.versions,
                          probe=lambda root: (_ for _ in ()).throw(AssertionError("no probe")), notify=lambda t: None)
    assert out["probe"] is None
