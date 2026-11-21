"""gta2-it: «positivo» / «negativo» in a data panel failed the whole Timeline. Any language, any spelling → a sign."""

from pipeline.schemas import DataRow, StatData


def test_signs_in_other_languages_and_unknown_words():
    assert DataRow(label="a", value="1", sign="positivo").sign == "positive"
    assert DataRow(label="a", value="1", sign="Negativa").sign == "negative"
    assert DataRow(label="a", value="1", sign="négatif").sign == "negative"
    assert DataRow(label="a", value="1", sign="positiv").sign == "positive"
    assert DataRow(label="a", value="1", sign="neutro").sign == "neutral"
    assert DataRow(label="a", value="1", sign="whatever").sign == "neutral"
    assert StatData(value="2", label="b", sign="negative").sign == "negative"
    assert StatData(value="2", label="b").sign == "neutral"
