from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()
