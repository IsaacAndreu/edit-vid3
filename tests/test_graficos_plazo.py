from pipeline.graphics import clean

TEXT = ("La reclamación debe presentarse en el primer minuto. Según el tribunal, se presentó un minuto y cuatro segundos "
        "después de la nota, pero el vídeo muestra que la entrenadora reclamó a los 47 segundos.")


def test_a_deadline_with_its_moments_said_in_the_script():
    g = clean("plazo", {"title": "Plazo para reclamar", "limit": 60,
                        "marks": [{"seconds": 47, "label": "la entrenadora reclamó"}, {"seconds": 64, "label": "según el tribunal"}]},
              TEXT, None, set())
    assert g and g["limit"] == 60 and [m["seconds"] for m in g["marks"]] == [47, 64]


def test_a_deadline_with_an_invented_moment_is_dropped():
    assert clean("plazo", {"limit": 60, "marks": [{"seconds": 52}]}, TEXT, None, set()) is None


def test_a_score_that_changed_only_with_both_scores_said():
    text = "Su nota fue de 13,666, quinta. Tras la reclamación, 13,766: tercera."
    g = clean("cambio", {"name": "Chiles", "before": "13,666", "after": "13,766", "from_place": "quinta", "to_place": "tercera"},
              "Jordan Chiles. " + text, None, set())
    assert g and g["before"] == "13,666" and g["toPlace"] == "tercera"
    assert clean("cambio", {"name": "Chiles", "before": "13,666", "after": "13,866"}, "Jordan Chiles. " + text, None, set()) is None
