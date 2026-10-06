"""Numbers in words for the narration (pipeline/numeros.py)."""

from __future__ import annotations

import pytest

from pipeline.numeros import spoken_numbers, to_words


@pytest.mark.parametrize("text, said", [
    ("413.240.000 euros", "cuatrocientos trece millones doscientos cuarenta mil euros"),
    ("206,6 millones", "doscientos seis coma seis millones"),
    ("en 2023 los clientes", "en dos mil veintitrés los clientes"),
    ("más de 1.200 millones", "más de mil doscientos millones"),
    ("21 años", "veintiún años"),
    ("1 millón", "un millón"),
    ("el 1 de enero de 2019", "el uno de enero de dos mil diecinueve"),
    ("un 15% más", "un quince por ciento más"),
    ("cuesta 100 euros", "cuesta cien euros"),
    ("95 €", "noventa y cinco euros"),
    ("200 personas", "doscientas personas"),
    ("1 noche", "una noche"),
    ("41 páginas", "cuarenta y una páginas"),
    ("2 millones de personas", "dos millones de personas"),
    ("3,05", "tres coma cero cinco"),
    ("2024-2025", "dos mil veinticuatro-dos mil veinticinco"),
    ("COVID-19 y 4K a las 13:57 del 12/03/2024", "COVID-19 y 4K a las 13:57 del 12/03/2024"),
])
def test_spoken(text, said):
    assert spoken_numbers(text) == said


def test_big_numbers():
    assert to_words(1_000_000) == "un millón"
    assert to_words(21_000) == "veintiún mil"
    assert to_words(1_500_000_000) == "mil quinientos millones"
