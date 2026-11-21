"""Bloque 5: before the voice is recorded, what of the script can be shown — with image, ambient, without image —
and the sentences without one, each with an idea to fix it. A warning, never a block."""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from pipeline import imagen_guion

SCRIPT = ("Simone Biles ganó el oro en la final de suelo de Río 2016. Con quince años dejó el instituto para entrenar. "
          "Imagina lo que supone renunciar a todo eso. Sus padres son en realidad sus abuelos. "
          "En Tokio se retiró de la final por equipos. Hay muchas formas de entender la presión.")


def test_each_sentence_is_labelled_and_the_ones_without_image_come_with_an_idea():
    def ask(user):
        numbers = [int(n) for n in re.findall(r"^\[(\d+)\]", user, re.M)]
        kinds = {1: "imagen", 2: "ambiente", 3: "sin_imagen", 4: "ambiente", 5: "imagen", 6: "sin_imagen"}
        return {"frases": [{"n": n, "tipo": kinds[n], "idea": "Apóyala en su retirada de Tokio 2021" if kinds[n] == "sin_imagen" else ""}
                           for n in numbers]}

    r = imagen_guion.review(SimpleNamespace(), SCRIPT, "Simone Biles", ask=ask)
    assert r["counts"] == {"imagen": 2, "ambiente": 2, "sin_imagen": 2, "sin_revisar": 0}
    assert [x["text"][:8] for x in r["sinImagen"]] == ["Imagina ", "Hay much"]
    assert r["sinImagen"][0]["idea"].startswith("Apóyala") and r["verdict"].startswith("⚠️ 33 %")


def test_a_batch_without_answer_stays_unknown_and_short_scripts_are_refused():
    r = imagen_guion.review(SimpleNamespace(), SCRIPT, ask=lambda user: (_ for _ in ()).throw(RuntimeError("caído")))
    assert r["counts"]["sin_revisar"] == 6 and r["sinImagen"] == []
    with pytest.raises(ValueError):
        imagen_guion.review(SimpleNamespace(), "Hola. Adiós.", ask=lambda user: {})
    assert imagen_guion.verdict({"imagen": 60, "ambiente": 35, "sin_imagen": 5}).startswith("✅")
