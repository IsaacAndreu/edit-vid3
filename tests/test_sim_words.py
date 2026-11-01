import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "remotion"
KEY = re.compile(r"^\s+([A-Za-z0-9_]+): \{es:", re.M)


def test_no_two_worlds_define_the_same_on_screen_word():
    # the words of every world share one dictionary: a key defined twice is overwritten by whichever file loads last
    # (the office once said «Gacelas cazadas» because the savanna also defined «caught»)
    where = defaultdict(list)
    for path in sorted((ROOT / "sim").rglob("*.ts*")) + sorted((ROOT / "components").rglob("*.ts*")):
        for key in KEY.findall(path.read_text(encoding="utf-8")):
            where[key].append(path.relative_to(ROOT).as_posix())
    twice = {k: v for k, v in where.items() if len(v) > 1}
    assert not twice, twice


def test_the_epidemic_scenes_are_offered_to_the_scriptwriter():
    import json
    spec = json.loads((ROOT / "sim" / "worlds.json").read_text(encoding="utf-8"))["contagio"]
    options = spec["params"]["scene"]["options"]
    for scene in ["arbol", "doble", "oculto", "palancas", "caminos", "inmunidad"]:
        assert scene in options and f"{scene} (" in spec["describe"]
    tsx = (ROOT / "sim" / "worlds" / "epidemia.tsx").read_text(encoding="utf-8")
    assert all(f"{s}:" in tsx.split("EPIDEMIC_SCENES")[-1] for s in ["arbol", "doble", "oculto", "palancas", "caminos", "inmunidad"])


def test_a_datacard_without_footage_still_becomes_a_valid_simulation_shot():
    # sim2, sim5, sim7-short2 failed with «1 validation error for Shot»: a broll shot needs a broll
    from pipeline.planner import drawn_shot
    from pipeline.schemas import Shot

    shot = {"id": "s001", "type": "datacard", "startWord": 0, "endWord": 3, "start": 0, "end": 2, "text": "22 coches en círculo",
            "chapter": 0, "panel": {"title": "x"}}
    assert Shot.model_validate(drawn_shot(shot)).type == "broll"
