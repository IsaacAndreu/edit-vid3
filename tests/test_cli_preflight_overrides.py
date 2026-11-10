from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline import cli, preflight
from pipeline.config import ConfigError
from pipeline.overrides import OverridesError, apply_overrides, load_overrides

from tests.helpers import make_settings


class ProjectResolutionTests(unittest.TestCase):
    def test_folder_with_guion_and_voz_needs_no_flags(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir) / "Video7"
            project.mkdir()
            (project / "guion.txt").write_text("Hola", encoding="utf-8")
            (project / "voz.mp3").write_bytes(b"x")
            (project / "notas.txt").write_text("otra cosa", encoding="utf-8")
            (project / "overrides.json").write_text('{"scenes": {}}', encoding="utf-8")

            request = cli.build_run_request(cli._run_parser().parse_args([str(project), "--skip-render"]))

            self.assertEqual(request.script_path, (project / "guion.txt").resolve())
            self.assertEqual(request.audio_path, (project / "voz.mp3").resolve())
            self.assertEqual(request.output_path.name, "Video7.mp4")
            self.assertEqual(request.output_path.parent.name, "Video7")
            self.assertEqual(request.overrides_path, (project / "overrides.json").resolve())
            self.assertTrue(request.skip_render)

    def test_ambiguous_folder_explains_what_to_rename(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            (project / "a.txt").write_text("a", encoding="utf-8")
            (project / "b.txt").write_text("b", encoding="utf-8")
            (project / "voz.mp3").write_bytes(b"x")
            with self.assertRaisesRegex(cli.UsageError, "varios candidatos a guion"):
                cli.resolve_project(project)

    def test_legacy_flags_still_work_and_missing_ones_are_named(self) -> None:
        args = cli._run_parser().parse_args(["--guion", "g.txt", "--voz", "v.mp3", "--output", "o.mp4"])
        request = cli.build_run_request(args)
        self.assertEqual((request.script_path, request.audio_path, request.output_path), (Path("g.txt"), Path("v.mp3"), Path("o.mp4")))
        self.assertFalse(request.fresh)

        with self.assertRaisesRegex(cli.UsageError, "--voz, --output"):
            cli.build_run_request(cli._run_parser().parse_args(["--guion", "g.txt"]))

    def test_scene_number_lists_and_ranges(self) -> None:
        self.assertEqual(cli._parse_scene_numbers("12, 17,20-22"), frozenset({12, 17, 20, 21, 22}))
        self.assertEqual(cli._parse_scene_numbers(None), frozenset())
        for bad in ("abc", "5-2", "0"):
            with self.subTest(bad=bad), self.assertRaises(cli.UsageError):
                cli._parse_scene_numbers(bad)


class MainExitCodeTests(unittest.TestCase):
    def _run(self, argv: list[str]) -> tuple[int, str]:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(io.StringIO()):
            code = cli.main(argv)
        return code, stderr.getvalue()

    def test_usage_problem_is_one_clear_line(self) -> None:
        code, err = self._run([])
        self.assertEqual(code, 1)
        self.assertTrue(err.startswith("Error: Faltan --guion, --voz, --output"))
        self.assertNotIn("Traceback", err)

    def test_unexpected_library_errors_do_not_dump_a_traceback(self) -> None:
        class WeirdSdkError(Exception):
            pass

        with patch.dict(cli._COMMANDS, {"run": lambda _argv: (_ for _ in ()).throw(WeirdSdkError("quota exceeded"))}):
            code, err = self._run(["x"])
        self.assertEqual(code, 1)
        self.assertIn("WeirdSdkError", err)
        self.assertIn("quota exceeded", err)

    def test_ctrl_c_explains_that_work_is_saved(self) -> None:
        with patch.dict(cli._COMMANDS, {"run": lambda _argv: (_ for _ in ()).throw(KeyboardInterrupt())}):
            code, err = self._run(["x"])
        self.assertEqual(code, 130)
        self.assertIn("relanza el mismo comando", err)


class CleanCommandTests(unittest.TestCase):
    def test_dry_run_by_default_and_keep_newest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            assets = root / "public" / "pipeline-assets"
            for index, name in enumerate(["viejo", "medio", "nuevo"]):
                (assets / name).mkdir(parents=True)
                file = assets / name / "clip.mp4"
                file.write_bytes(b"x" * 1024)
                stamp = time.time() - (3 - index) * 86400
                os.utime(file, (stamp, stamp))
                os.utime(assets / name, (stamp, stamp))
            out = io.StringIO()
            with patch.object(cli, "PROJECT_ROOT", root), contextlib.redirect_stdout(out):
                self.assertEqual(cli.main(["clean", "--keep", "1"]), 0)
                self.assertEqual(sorted(path.name for path in assets.iterdir()), ["medio", "nuevo", "viejo"])
                self.assertIn("Simulación", out.getvalue())
                self.assertEqual(cli.main(["clean", "--keep", "1", "--yes"]), 0)
            self.assertEqual([path.name for path in assets.iterdir()], ["nuevo"])


class PreflightTests(unittest.TestCase):
    def _checks(self, *, tools: set[str], **kwargs: object) -> dict[str, preflight.Check]:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            if kwargs.pop("with_node_modules", False):
                (root / "node_modules" / "@remotion" / "cli").mkdir(parents=True)
            installed = lambda module, package, *, required: preflight.Check(f"python:{package}", preflight.OK, "instalado")
            with patch(
                "pipeline.preflight.shutil.which", side_effect=lambda name: f"/bin/{name}" if name in tools else None
            ), patch("pipeline.preflight._module_check", side_effect=installed):
                checks = preflight.run_checks(
                    settings_loader=kwargs.pop("settings_loader", lambda: make_settings(root)),  # type: ignore[arg-type]
                    project_root=root,
                    **kwargs,  # type: ignore[arg-type]
                )
        return {check.name: check for check in checks}

    def test_complete_environment_has_no_errors(self) -> None:
        checks = self._checks(tools={"ffmpeg", "ffprobe", "deno", "node", "npx"}, with_node_modules=True)
        self.assertEqual([c.name for c in checks.values() if c.status == preflight.ERROR], [])
        preflight.enforce(list(checks.values()))

    def test_missing_tools_are_found_before_any_work(self) -> None:
        checks = self._checks(tools={"node", "npx"})
        failing = {name for name, check in checks.items() if check.status == preflight.ERROR}
        self.assertEqual(failing, {"ffmpeg", "ffprobe", "deno", "dependencias de Remotion"})
        with self.assertRaisesRegex(preflight.PreflightError, "ffmpeg") as raised:
            preflight.enforce(list(checks.values()))
        self.assertIn("npm install", str(raised.exception))

    def test_flags_relax_what_is_required(self) -> None:
        checks = self._checks(tools={"ffprobe"}, need_third_party=False, need_render=False)
        self.assertEqual([c.name for c in checks.values() if c.status == preflight.ERROR], [])
        self.assertNotIn("deno", checks)
        self.assertNotIn("node", checks)

    def test_new_node_dependency_not_installed_yet_is_caught(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "package.json").write_text(
                json.dumps({"dependencies": {"remotion": "4", "@fontsource/inter": "5"}}), encoding="utf-8"
            )
            for name in ("@remotion/cli", "remotion"):
                (root / "node_modules" / name).mkdir(parents=True)

            stale = preflight._node_dependencies_check(root)
            self.assertEqual(stale.status, preflight.ERROR)
            self.assertIn("@fontsource/inter", stale.detail)
            self.assertEqual(stale.fix, "npm install")

            (root / "node_modules" / "@fontsource" / "inter").mkdir(parents=True)
            self.assertEqual(preflight._node_dependencies_check(root).status, preflight.OK)

    def test_missing_python_package_names_the_install_command(self) -> None:
        check = preflight._module_check("module_that_does_not_exist_xyz", "yt-dlp", required=True)
        self.assertEqual(check.status, preflight.ERROR)
        self.assertIn("pip install -r requirements.txt", check.fix)

    def test_missing_keys_and_files_are_reported(self) -> None:
        def no_keys() -> None:
            raise ConfigError("Faltan variables obligatorias: OPENAI_API_KEY")

        checks = self._checks(
            tools={"ffmpeg", "ffprobe", "deno", "node", "npx"},
            with_node_modules=True,
            settings_loader=no_keys,
            audio_path=Path("/no/such/voz.mp3"),
            script_path=Path("/no/such/guion.txt"),
        )
        self.assertEqual(checks[".env"].status, preflight.ERROR)
        self.assertIn("OPENAI_API_KEY", checks[".env"].detail)
        self.assertEqual(checks["voz"].status, preflight.ERROR)
        self.assertEqual(checks["guion"].status, preflight.ERROR)


class OverridesTests(unittest.TestCase):
    def _scenes(self) -> list[dict]:
        return [{"text": "Uno", "keywords": ["a"]}, {"text": "Dos", "keywords": ["b"]}]

    def test_text_fields_and_local_media_are_applied(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "planos").mkdir()
            (root / "planos" / "ruleta.mp4").write_bytes(b"x")
            path = root / "overrides.json"
            path.write_text(
                json.dumps({"scenes": {"2": {"media": "planos/ruleta.mp4", "keywords": ["roulette wheel"], "text": "La ruleta"}}}),
                encoding="utf-8",
            )
            scenes = self._scenes()
            changed = apply_overrides(scenes, load_overrides(path))  # type: ignore[arg-type]

            self.assertEqual(changed, [2])
            self.assertEqual(scenes[0], {"text": "Uno", "keywords": ["a"]})
            self.assertEqual(scenes[1]["text"], "La ruleta")
            self.assertEqual(scenes[1]["keywords"], ["roulette wheel"])
            self.assertEqual(scenes[1]["mediaOverride"], str((root / "planos" / "ruleta.mp4").resolve()))

    def test_mistakes_are_explained(self) -> None:
        cases = {
            '{"scenes": {"1": {"colour": "red"}}}': "claves no admitidas",
            '{"scenes": {"x": {}}}': "no es un número de escena",
            '{"scenes": {"1": {"media": "falta.mp4"}}}': "no existe el fichero",
            '{"scenes": {"1": {"keywords": "casino"}}}': "lista de textos",
            "{nope": "no es JSON válido",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "overrides.json"
            for content, expected in cases.items():
                path.write_text(content, encoding="utf-8")
                with self.subTest(content=content), self.assertRaisesRegex(OverridesError, expected):
                    load_overrides(path)
            path.write_text('{"scenes": {"9": {"text": "x"}}}', encoding="utf-8")
            with self.assertRaisesRegex(OverridesError, r"escenas \[9\]"):
                apply_overrides(self._scenes(), load_overrides(path))  # type: ignore[arg-type]



class LegacyMainModuleTests(unittest.TestCase):
    def test_external_launchers_can_still_import_parser_and_run_pipeline(self) -> None:
        import main as legacy

        args = legacy._parser().parse_args(
            ["--guion", "g.txt", "--voz", "v.mp3", "--output", "o.mp4", "--skip-render", "--skip-third-party"]
        )
        with patch.object(legacy, "_run_request", return_value=Path("o.props.json")) as run:
            self.assertEqual(legacy.run_pipeline(args), Path("o.props.json"))
        request = run.call_args.args[0]
        self.assertEqual((request.script_path, request.audio_path, request.output_path), (Path("g.txt"), Path("v.mp3"), Path("o.mp4")))
        self.assertTrue(request.skip_render)
        self.assertTrue(request.skip_third_party)

        minimal = argparse.Namespace(guion="g.txt", voz="v.mp3", output="o.mp4")
        with patch.object(legacy, "_run_request", return_value=Path("o.mp4")) as run:
            legacy.run_pipeline(minimal)
        self.assertFalse(run.call_args.args[0].skip_render)

if __name__ == "__main__":
    unittest.main()
