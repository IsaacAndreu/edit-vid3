"""The key-date calendar of true-crime videos: only a date the script says, day and month (and year if shown)."""

from pipeline.graphics import calendar_graphic, clean, spoken_es


class Ctx:
    def section(self, name):
        return {}


TEXT = "Madrugada del dos de abril de dos mil quince. Alguien le golpea la cabeza con un martillo."


def test_a_date_the_voice_spells_out_becomes_a_calendar_page():
    assert spoken_es(2015) == "dos mil quince" and spoken_es(1995) == "mil novecientos noventa y cinco"
    page = calendar_graphic({"day": 2, "month": 4, "year": 2015, "label": "golpea la cabeza con un martillo"}, TEXT, Ctx())
    assert page["monthName"] == "abril" and page["year"] == 2015 and page["weekday"] == 3      # a Thursday
    assert page["label"] == "golpea la cabeza con un martillo"
    assert clean("calendar", {"day": 2, "month": 4, "year": 2015}, TEXT, Ctx(), set())["type"] == "calendar"


def test_nothing_the_script_does_not_say():
    assert calendar_graphic({"day": 3, "month": 4, "year": 2015}, TEXT, Ctx()) is None          # another day
    assert calendar_graphic({"day": 2, "month": 5, "year": 2015}, TEXT, Ctx()) is None          # another month
    no_year = calendar_graphic({"day": 2, "month": 4, "year": 2016}, TEXT, Ctx())
    assert no_year["year"] is None and no_year["weekdays"] == []        # a year not said goes, and its weekdays
    assert calendar_graphic({"day": 31, "month": 4}, "el 31 de abril", Ctx()) is None            # no such day
    assert calendar_graphic({"day": 2, "month": 4, "label": "una frase inventada aquí"}, TEXT, Ctx())["label"] is None
