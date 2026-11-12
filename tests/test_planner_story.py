"""planner: the outline's story events and their search in the local language."""

from pipeline.planner import event_place_at, parse_story


def test_each_event_keeps_its_search_in_the_language_of_where_it_happened():
    sentences = [(0, 3), (4, 8), (9, 12)]
    subject, events = parse_story({"subject": "", "events": [
        {"sentence": 0, "label": "Michael Madison trial Cleveland 2016", "place": None},
        {"sentence": 2, "label": "Brazil plane crash 2024 Vinhedo", "place": "queda avião Vinhedo 2024"}]}, sentences)
    assert [e.place for e in events] == [None, "queda avião Vinhedo 2024"]
    assert event_place_at(events, 10) == "queda avião Vinhedo 2024" and event_place_at(events, 5) is None
