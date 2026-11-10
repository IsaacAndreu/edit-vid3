from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pipeline import library
from pipeline.context import RunContext
from pipeline.people import people_to_introduce
from pipeline.schemas import ShotsFile, TimelineShot
from pipeline.timeline import person_cards


class PeopleTests(unittest.TestCase):
    def test_protagonist_first_then_named_people(self) -> None:
        story = ShotsFile.model_construct(subject="Carlos Yulo · artistic gymnastics", shots=[
            type("S", (), {"label": type("L", (), {"kind": "name", "text": "Kohei Uchimura"})()})(),
            type("S", (), {"label": type("L", (), {"kind": "score", "text": "15.3"})()})(),
            type("S", (), {"label": None})(),
        ])
        self.assertEqual(people_to_introduce(story, 4), ["Carlos Yulo", "Kohei Uchimura"])
        self.assertEqual(library.person_key("Kōhei Uchimura"), "kohei-uchimura")

    def test_card_goes_on_the_first_plain_shot_naming_the_person_after_the_hook(self) -> None:
        media = {"src": "media/x.mp4", "kind": "video", "source": "youtube", "credit": "Fuente: X"}
        shots = [TimelineShot.model_validate({"id": f"s{i:03d}", "type": "broll", "from": i * 60, "durationInFrames": 60,
                                              "text": text, "media": media})
                 for i, text in enumerate(["Yulo en el hook", "algo", "dijo Yulo", "Yulo otra vez"])]
        with tempfile.TemporaryDirectory() as tmp:
            ctx = RunContext.create("t", root=Path(tmp), config={"judge": {"hook_seconds": 3}})
            ctx.write_json("people.json", {"people": [{"name": "Carlos Yulo", "image": "people/carlos-yulo.png",
                                                       "credit": "Fuente: Embajada"}]})
            person_cards(ctx, None, shots, [], 30)
        self.assertEqual([s.media.layout for s in shots], ["full", "full", "person", "full"])
        self.assertEqual((shots[2].media.caption, shots[2].media.credit), ("Carlos Yulo", "Fuente: Embajada"))


if __name__ == "__main__":
    unittest.main()


def test_portrait_score_rejects_flipping_figures_and_prefers_big_upright_faces():
    import numpy as np
    from pipeline import people

    class Det:
        def __init__(self, face):
            self.face = face

        def face_details(self, image):
            return [self.face]

    upright_face = {"box": [40, 10, 20, 24], "area": 0.02,
                    "landmarks": [(45, 18), (55, 18), (50, 24), (46, 29), (54, 29)]}
    image = np.zeros((1000, 800, 3), np.uint8)
    standing = people.portrait_score(image, Det(upright_face), (0, 400, 20, 80))
    assert standing is not None and standing > 1.0
    low_head = {**upright_face, "box": [40, 300, 20, 24]}
    assert people.portrait_score(image, Det(low_head), (0, 400, 20, 80)) is None       # head at the bottom
    assert people.portrait_score(image, Det(upright_face), (0, 100, 0, 400)) is None    # lying / mid-flip
    upside = {**upright_face, "landmarks": [(45, 29), (55, 29), (50, 24), (46, 18), (54, 18)]}
    assert people.portrait_score(image, Det(upside), None) is None                      # eyes below the mouth


def test_organisations_are_not_people():
    from pipeline.people import looks_like_person

    assert not looks_like_person("OCU") and not looks_like_person("NTSB") and not looks_like_person("Ministerio de Consumo")
    assert looks_like_person("Surya Bonaly") and looks_like_person("SATO") and looks_like_person("MALININ")
