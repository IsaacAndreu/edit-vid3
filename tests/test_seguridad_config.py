"""A video's config.yaml from the studio is data: only known values, and a partner's video never sets where
requests and keys go, what program runs or the spending caps."""

from __future__ import annotations

import json

import yaml

from pipeline import web
from pipeline.context import RunContext, find_video
from tests.test_socios import studio  # noqa: F401  (fixture)
from tests.test_web import SCRIPT


def test_form_values_never_become_settings(studio):                     # noqa: F811
    root, call, login = studio
    assert login("contraseña-amigo") == 200
    sneaky = "historia\nplanner:\n  base_url: http://otro\nbudget:\n  per_video_usd: 999"
    for field in ("format", "serie"):
        code, body, _ = call("/api/videos", {"name": f"v-{field}", "channel": "atletismo", "script": SCRIPT, field: sneaky})
        assert code == 400, (field, body)
        assert not find_video(root, f"v-{field}").exists()
    code, body, _ = call("/api/videos", {"name": "bueno", "channel": "atletismo", "script": SCRIPT})
    assert code == 200, body
    saved = yaml.safe_load((find_video(root, "bueno") / "config.yaml").read_text())
    assert saved == {"creado_por": "amigo"}


def test_a_partners_video_ignores_protected_settings(studio):           # noqa: F811
    root, call, login = studio
    login("contraseña-amigo")
    assert call("/api/videos", {"name": "suyo2", "channel": "atletismo", "script": SCRIPT})[0] == 200
    folder = find_video(root, "suyo2")
    data = yaml.safe_load((folder / "config.yaml").read_text())
    data.update({"planner": {"base_url": "http://otro", "batch_size": 7},
                 "render": {"browser_executable": "/tmp/x"}, "budget": {"per_video_usd": 999},
                 "sourcing": {"youtube": {"proxy": "http://otro:1"}}})
    (folder / "config.yaml").write_text(yaml.safe_dump(data))
    cfg = RunContext.create("suyo2", root=root).config
    assert "base_url" not in cfg.get("planner", {}) and cfg["planner"].get("batch_size") == 7   # the rest stays
    assert cfg.get("render", {}).get("browser_executable") != "/tmp/x"
    assert cfg.get("budget", {}).get("per_video_usd") != 999
    assert (cfg.get("sourcing", {}).get("youtube") or {}).get("proxy") != "http://otro:1"


def test_your_own_video_keeps_its_settings(tmp_path):
    from tests.test_web import _project

    _project(tmp_path)
    web.create_video(tmp_path, {"name": "mio", "channel": "aviacion", "script": SCRIPT})
    folder = find_video(tmp_path, "mio")
    (folder / "config.yaml").write_text(yaml.safe_dump({"budget": {"per_video_usd": 7}}))
    assert RunContext.create("mio", root=tmp_path).config["budget"]["per_video_usd"] == 7
    assert json.dumps(web.formats(tmp_path))
