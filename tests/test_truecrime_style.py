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
