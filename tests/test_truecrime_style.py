"""True-crime style: people introduced by their whole photo and their typed name; the film finish only on request."""

from pathlib import Path

from PIL import Image

from pipeline.schemas import ShotsFile, TimelineMedia, TimelineShot
from pipeline.timeline import person_cards, place_labels


class Ctx:
    def __init__(self, root: Path, card: str):
        self.work_dir, self.card = root, card

    def section(self, name):
        return {"card": self.card} if name == "people" else {}

    def read_json(self, name):
        import json

        return json.loads((self.work_dir / name).read_text("utf-8"))


def _setup(tmp_path):
    import json

    (tmp_path / "people").mkdir()
    Image.new("RGBA", (400, 500)).save(tmp_path / "people" / "isabel.png")
    Image.new("RGB", (1200, 800)).save(tmp_path / "people" / "isabel-foto.jpg")
    (tmp_path / "people.json").write_text(json.dumps({"people": [{"name": "Isabel Fuentes", "image": "people/isabel.png",
                                                                  "photo": "people/isabel-foto.jpg", "credit": "Fuente: X"}]}))
    media = TimelineMedia(src="media/a.mp4", kind="video", source="youtube", credit="Fuente: Y")
    shots = [TimelineShot.model_validate({"id": f"s{i}", "type": "broll", "from": 1200 + i * 90, "durationInFrames": 90,
                                          "text": t, "media": media.model_dump()})
             for i, t in enumerate(["La casa de Pazos.", "Isabel Fuentes tenía 66 años."])]
    return shots


def test_a_person_is_introduced_by_their_whole_photo_and_their_name(tmp_path):
    shots = _setup(tmp_path)
    names = person_cards(Ctx(tmp_path, "photo"), None, shots, [], 30)
    assert shots[1].media.src == "people/isabel-foto.jpg" and shots[1].media.layout == "full"
    assert names == {"s1": "Isabel Fuentes"}
    story = ShotsFile.model_construct(shots=[], events=[])
    labels = place_labels(story, shots, [], 30, {}, names)
    assert [(l.kind, l.text, l.from_) for l in labels] == [("name", "Isabel Fuentes", 1293)]


def test_the_cutout_card_stays_the_default(tmp_path):
    shots = _setup(tmp_path)
    assert person_cards(Ctx(tmp_path, "cutout"), None, shots, [], 30) == {}
    assert shots[1].media.layout == "person"


def test_the_film_finish_runs_only_when_the_channel_asks(tmp_path):
    from pipeline.render import film_look

    assert film_look(None, tmp_path / "x.mp4", None, {"brand": {}}) is False


def test_a_photo_stays_on_over_the_filler_after_it():
    from pipeline.schemas import TimelineGroup
    from pipeline.timeline import hold_photos

    photo = TimelineMedia(src="people/isabel-foto.jpg", kind="image", source="web", credit="Fuente: X", layout="full")
    clip = TimelineMedia(src="media/a.mp4", kind="video", source="youtube", credit="Fuente: Y")
    shots = [TimelineShot.model_validate({"id": f"s{i}", "type": "broll", "from": i * 100, "durationInFrames": 100,
                                          "text": f"frase {i}", "media": m.model_dump() if m else None})
             for i, m in enumerate([photo, clip, None, clip, clip])]
    weak = {"s1", "s4"}                                    # s1 filler, s2 nothing, s3 footage the judge chose
    held = hold_photos(shots, [], 30, 10, weak)
    assert [(s.id, s.durationInFrames) for s in held] == [("s0", 300), ("s3", 100), ("s4", 100)]
    assert held[0].text == "frase 0 frase 1 frase 2"
    assert [s.id for s in hold_photos(shots, [], 30, 7, weak)] == ["s0", "s2", "s3", "s4"]     # 7 s: only s1 fits
    graphic = TimelineGroup.model_validate({"id": "g", "kind": "graphic", "from": 100, "durationInFrames": 50,
                                            "graphic": {"type": "kinetic", "lines": ["x"]}})
    assert len(hold_photos(shots, [graphic], 30, 10, weak)) == 5                             # never under a graphic


def test_people_named_together_are_shown_side_by_side(tmp_path):
    import json

    from pipeline.timeline import lineups

    _setup(tmp_path)
    Image.new("RGBA", (400, 500)).save(tmp_path / "people" / "aniceto.png")
    (tmp_path / "people.json").write_text(json.dumps({"people": [
        {"name": "Isabel Fuentes", "image": "people/isabel.png", "photo": "people/isabel-foto.jpg"},
        {"name": "Aniceto Rodríguez Caneiro", "image": "people/aniceto.png"}]}))

    class Lineups(Ctx):
        def section(self, name):
            return {"lineups": 2} if name == "people" else {}

    media = TimelineMedia(src="media/a.mp4", kind="video", source="youtube", credit="Fuente: Y").model_dump()
    shots = [TimelineShot.model_validate({"id": "s0", "type": "broll", "from": 0, "durationInFrames": 90,
                                          "text": "Isabel y Aniceto llevaban 25 años casados.", "media": media}),
             TimelineShot.model_validate({"id": "s1", "type": "broll", "from": 90, "durationInFrames": 90,
                                          "text": "Isabel trabajaba en el campo.", "media": media})]
    found = lineups(Lineups(tmp_path, ""), shots, [], 30)
    assert len(found) == 1 and found[0].from_ == 0
    assert [p["name"] for p in found[0].graphic["people"]] == ["Isabel Fuentes", "Aniceto Rodríguez Caneiro"]
    assert found[0].graphic["people"][0]["media"]["src"] == "people/isabel-foto.jpg"        # the whole photo first
    assert lineups(Ctx(tmp_path, ""), shots, [], 30) == []                                    # off unless asked
