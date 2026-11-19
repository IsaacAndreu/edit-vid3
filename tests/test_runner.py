from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline import runner
from pipeline.context import RunContext
from pipeline.runner import Stage, run_stages


class RunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "materiales" / "demo").mkdir(parents=True)
        self.source = self.root / "materiales" / "demo" / "in.txt"
        self.source.write_text("v1", encoding="utf-8")
        self.ctx = RunContext.create("demo", root=self.root, config={"step": {"k": 1}})
        self.calls: list[str] = []

        def make(name: str, reads):
            def run(ctx: RunContext) -> None:
                self.calls.append(name)
                (ctx.work_dir / f"{name}.json").write_text("{}", encoding="utf-8")

            return Stage(name, lambda ctx: [ctx.work_dir / f"{name}.json"], reads, run, None, ("step",))

        self.stages = [
            make("first", lambda ctx: [self.source]),
            make("second", lambda ctx: [ctx.work_dir / "first.json"]),
        ]
        patcher = patch.multiple(runner, STAGES=self.stages, STAGE_NAMES=["first", "second"])
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)

    def test_second_run_skips_everything(self) -> None:
        run_stages(self.ctx)
        run_stages(self.ctx)
        self.assertEqual(self.calls, ["first", "second"])

    def test_changed_input_reruns_only_affected_stage(self) -> None:
        run_stages(self.ctx)
        self.source.write_text("v2", encoding="utf-8")
        run_stages(self.ctx)
        # "second" is re-run only if first.json actually changed (it did not: same "{}").
        self.assertEqual(self.calls, ["first", "second", "first"])

    def test_config_change_invalidates(self) -> None:
        run_stages(self.ctx)
        self.ctx.config["step"]["k"] = 2
        run_stages(self.ctx)
        self.assertEqual(self.calls, ["first", "second", "first", "second"])

    def test_force_and_until(self) -> None:
        run_stages(self.ctx, until="first")
        self.assertEqual(self.calls, ["first"])
        run_stages(self.ctx, force={"first"})
        self.assertEqual(self.calls, ["first", "first", "second"])

    def test_missing_output_reruns(self) -> None:
        run_stages(self.ctx)
        (self.ctx.work_dir / "second.json").unlink()
        run_stages(self.ctx)
        self.assertEqual(self.calls, ["first", "second", "second"])

    def test_retry_if_reruns_a_valid_stage(self) -> None:
        run_stages(self.ctx)
        flaky = self.stages[0]
        self.stages[0] = Stage(flaky.name, flaky.outputs, flaky.inputs, flaky.run, None, ("step",), lambda ctx: True)
        run_stages(self.ctx, until="first")
        self.assertEqual(self.calls, ["first", "second", "first"])

    def test_unknown_stage_names_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            run_stages(self.ctx, force={"nope"})
        with self.assertRaises(ValueError):
            run_stages(self.ctx, until="nope")


class PerVideoConfigTests(unittest.TestCase):
    def test_materials_config_overrides_the_project_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config.yaml").write_text("timeline:\n  music_volume: 0.25\n  cold_open_seconds: 0\nvideo:\n  fps: 30\n")
            (root / "materiales" / "v").mkdir(parents=True)
            (root / "materiales" / "v" / "config.yaml").write_text("timeline:\n  cold_open_seconds: 10\n")
            ctx = RunContext.create("v", root=root)
            other = RunContext.create("w", root=root)
        self.assertEqual(ctx.section("timeline"), {"music_volume": 0.25, "cold_open_seconds": 10})
        self.assertEqual(other.section("timeline")["cold_open_seconds"], 0)


if __name__ == "__main__":
    unittest.main()


def test_fingerprints_read_the_bytes_only_when_a_file_changed(tmp_path, monkeypatch):
    """4.4: the same value as hashing everything (markers stay valid), but files untouched since the last
    fingerprint are not read again; a change of size or time is."""

    import hashlib
    import os

    from pipeline import runner
    from pipeline.context import RunContext
    from pipeline.runner import Stage

    (tmp_path / "materiales" / "v").mkdir(parents=True)
    ctx = RunContext.create("v", root=tmp_path, config={"x": {"a": 1}})
    folder = tmp_path / "datos"
    folder.mkdir()
    (folder / "uno.txt").write_text("1")
    (folder / "dos.txt").write_text("22")
    stage = Stage("s", lambda c: [], lambda c: [folder, tmp_path / "falta.json"], None, None, ("x",))

    def plain():
        digest = hashlib.sha256()
        for path in stage.inputs(ctx):
            runner._hash_path(digest, path)
        digest.update(json.dumps(runner._without_speed(ctx.section("x")), sort_keys=True).encode())
        return digest.hexdigest()

    first = runner.fingerprint(ctx, stage)
    assert first == plain()                                              # the same value as always
    reads = []
    real = runner._hash_path
    monkeypatch.setattr(runner, "_hash_path", lambda d, p: reads.append(p) or real(d, p))
    runner._FINGERPRINTS.clear()                                         # a new process: from huellas.cache
    assert runner.fingerprint(ctx, stage) == first and reads == []
    assert not list((ctx.work_dir / ".stages").glob("*.json"))           # never taken for a stage marker
    (folder / "dos.txt").write_text("33")
    os.utime(folder / "dos.txt", ns=(1, 1))                              # same size, another time
    changed = runner.fingerprint(ctx, stage)
    assert reads and changed != first and changed == plain()
