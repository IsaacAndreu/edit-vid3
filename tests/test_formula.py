"""From 5-8 reference videos to a channel ready to produce (part 3): API, subtitles and model simulated."""

import json

import pytest
import yaml

from pipeline import formula

IDS = ["aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc", "ddddddddddd", "eeeeeeeeeee", "fffffffffff"]


class API:
    def videos(self, ids):
        titles = ["10 SECRETOS de Simone Biles: lo que nadie sabe", "7 VERDADES de Rebeca Andrade: su historia",
                  "5 MENTIRAS de Nadia Comaneci: la verdad", "9 DATOS de Suni Lee: increíble",
                  "8 COSAS de Jordan Chiles: así es", "Por qué Biles se retiró en Tokio?"]
        return [{"id": i, "title": titles[n], "channelId": f"UC{'x' * 21}{n}", "channel": f"c{n}", "views": 200_000,
                 "duration": 720, "thumbnail": "t", "audioLanguage": "pt" if n == 0 else "es",
                 "description": "Fuentes: Olympics\nhttps://youtube.com/@WorldGym"} for n, i in enumerate(ids)]

    def channels(self, ids):
        return [{"id": i, "subscribers": 30_000, "uploads": "UU"} for i in ids]

    def baseline(self, channel):
        return 50_000


def words(_vid):
    return [(f"palabra{i}", i * 0.4, i * 0.4 + 0.3) for i in range(1500)]       # 150 wpm over 10 min


def llm(system, text):
    if "FÓRMULA de guion" in system:
        return {"structure": ["gancho", "lista", "cierre"], "opening": "pregunta", "promises_every_seconds": 60,
                "sentence_kinds": {"hechos con fecha": 60, "citas": 20}}
    return {"ideas": [{"title": "10 SECRETOS de Simone Biles: lo que nadie sabe", "angle": "copia"},
                      {"title": "6 verdades de Daiane dos Santos", "angle": "pionera"}],
            "queries": ["secretos gimnastas"], "structure": "1. Gancho\n2. Lista de 7-10\n3. Cierre con pregunta"}


def test_fewer_than_five_references_are_refused(tmp_path):
    with pytest.raises(ValueError, match="de 5 a 8"):
        formula.analyse(tmp_path, [f"https://youtu.be/{i}" for i in IDS[:3]], api=API())


def test_the_formula_is_what_all_but_one_share_and_measured_is_kept_apart_from_interpreted(tmp_path):
    report = formula.analyse(tmp_path, [f"https://youtu.be/{i}" for i in IDS], api=API(), words_fn=words, llm_fn=llm,
                             niche="secretos de gimnastas")
    m = report["measured"]
    assert m["videos"] == 6 and m["ratio"] == 4.0 and m["wpm"] == 150 and m["durationMinutes"] == 12.0
    assert set(m["titleTraits"]) == {"number", "capitals", "separator"}             # 5 of 6 share them
    assert any("question" in x for x in report["lonely"])                          # only one asks: not the formula
    assert report["interpreted"]["sentenceKinds"] == {"hechos con fecha": 60, "citas": 20}
    assert "@WorldGym" in report["sources"] and report["montageMB"] == round(6 * 12 * formula.MB_PER_MINUTE_360)
    assert (tmp_path / formula.FOLDER / "secretos-de-gimnastas.json").is_file()


def test_the_montage_downloads_nothing_without_a_confirmation(tmp_path):
    report = formula.analyse(tmp_path, [f"https://youtu.be/{i}" for i in IDS], api=API(), niche="n")
    asked = formula.montage(tmp_path, report)
    assert asked["needsConfirmation"] and "MB" in asked["message"]
    done = formula.montage(tmp_path, report, confirm=True,
                           measure_fn=lambda vid, s: {"cutSeconds": 3.2, "firstImage": 0.0, "textShare": 2.0, "cardShare": 25.0})
    assert done["measured"]["montage"]["cardShare"] == 25.0 and formula.recipe_for(done["measured"]["montage"]) == "teoria"


def test_create_channel_with_the_formula_and_the_autopilot_waits_for_the_pilot(tmp_path):
    from pipeline import autopilot, niche_ideas

    (tmp_path / "config.yaml").write_text("{}\n")
    report = formula.analyse(tmp_path, [f"https://youtu.be/{i}" for i in IDS], api=API(), words_fn=words, llm_fn=llm,
                             niche="secretos de gimnastas")
    made = formula.create_channel(tmp_path, report, "Secretos Gym", llm_fn=llm)
    profile = yaml.safe_load((tmp_path / "canales" / "secretos-gym.yaml").read_text())
    assert made["channel"] == "secretos-gym" and profile["align"]["language"] == "es" and profile["montaje"]["receta"] == "persona"
    assert profile["guion"]["estructura"].startswith("1. Gancho") and len(profile["ideas"]["competitors"]) == 6
    assert [i["title"] for i in made["ideas"]] == ["6 verdades de Daiane dos Santos"]   # the reference's own title: out
    assert [i["title"] for i in niche_ideas.saved(tmp_path) if i["channel"] == "secretos-gym"] == ["6 verdades de Daiane dos Santos"]
    assert json.loads((tmp_path / "materiales" / "secretos-gym" / "material.json").read_text())["channels"] == ["@WorldGym"]
    with pytest.raises(ValueError, match="piloto"):
        autopilot.configure(tmp_path, "secretos-gym", on=True)
    report["videos"][0]["montage"] = {"cutSeconds": 3.0}
    formula.save(tmp_path, report)
    (tmp_path / "work" / "piloto1").mkdir(parents=True)
    (tmp_path / "work" / "piloto1" / "timeline.json").write_text(json.dumps({"fps": 30, "durationInFrames": 90, "shots": [
        {"id": "s1", "type": "broll", "from": 0, "durationInFrames": 90, "media": {"src": "x.mp4", "kind": "video"}}]}))
    rows = formula.pilot_table(tmp_path, formula.load(tmp_path, report["key"]), "piloto1")
    assert rows[0]["name"].startswith("PILOTO") and rows[0]["firstImage"] == 0.0 and rows[-1]["name"].startswith("fórmula")
    formula.pilot_seen(tmp_path, report["key"])
    assert autopilot.configure(tmp_path, "secretos-gym", on=True)["on"] is True
