"""Data from a partner (an idea's id, a «published» link, model text) never runs as code on the owner's pages."""

import html
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _core_functions() -> str:
    """esc, jsq, safeUrl and md from core.js, to run in Node."""

    text = (ROOT / "pipeline" / "web_static" / "js" / "core.js").read_text("utf-8")
    keep = [line for line in text.splitlines() if line.startswith(("const esc =", "const jsq =", "const safeUrl ="))]
    start = text.index("function md(")
    end = text.index("\nfunction pill(")
    return "\n".join(keep) + "\n" + text[start:end]


def _node(expression: str) -> str:
    if not shutil.which("node"):
        pytest.skip("sin node")
    done = subprocess.run(["node", "-e", _core_functions() + f"\nprocess.stdout.write(JSON.stringify({expression}));"],
                          capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


@pytest.mark.parametrize("value", ["x');alert(1);//", 'x");alert(1);//', "x'+alert(1)+'", "O'Brien", "</b>&#39;"])
def test_a_handler_argument_stays_a_string(value):
    attribute = _node(f"jsq({json.dumps(value)})")
    assert '"' not in attribute and "'" not in attribute and "<" not in attribute      # cannot leave the attribute
    assert json.loads(html.unescape(attribute)) == value                              # the handler gets it as given


def test_links_from_data_are_web_links_only():
    assert _node('safeUrl("javascript:alert(1)")') == "#"
    assert _node('safeUrl(" JaVaScRiPt:alert(1)")') == "#"
    assert _node('safeUrl("data:text/html,x")') == "#"
    assert _node('safeUrl("https://youtu.be/abc")') == "https://youtu.be/abc"
    page = _node('md("[mira](javascript:alert(1)) y [bien](https://example.com)", "")')
    assert "javascript:" not in page.split("mira")[0] and 'href="https://example.com"' in page


def test_the_server_refuses_ids_and_links_that_are_not_plain(tmp_path):
    from pipeline import housekeeping, niche_ideas

    with pytest.raises(ValueError):
        niche_ideas.save(tmp_path, {"id": "a');alert(1);//", "title": "x"}, "canal")
    assert niche_ideas.save(tmp_path, {"id": "idea-12:3", "title": "x"}, "canal")
    (tmp_path / "out" / "v1").mkdir(parents=True)
    with pytest.raises(ValueError):
        housekeeping.mark_published(tmp_path, "v1", "javascript:alert(1)")
    assert housekeeping.mark_published(tmp_path, "v1", "https://youtu.be/x")
