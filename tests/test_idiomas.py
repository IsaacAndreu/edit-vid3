"""Gaps in any language (prompt «qué canales empezar, cuáles doblar», part 1): API and model simulated."""

from pipeline import idiomas


class FakeAPI:
    """Results per (query, days): videos with views, a language and a channel size."""

    def __init__(self, data, left=100_000):
        self.data, self.left, self.searches = data, left, []

    def quota(self):
        return {"left": self.left}

    def search(self, query, days=0, order="", language="", max_results=50):
        self.searches.append((query, days, language))
        self.left -= 100
        return [f"{query}|{days}|{i}" for i in range(len(self.data.get((query, days), [])))]

    def videos(self, ids):
        out = []
        for vid in ids:
            query, days, i = vid.split("|")
            v = self.data[(query, int(days))][int(i)]
            out.append({"id": vid, "title": v.get("title", query), "channelId": v.get("ch", "c1"), "channel": "x",
                        "views": v["views"], "published": "2026-06-01T00:00:00Z", "duration": 600, "live": "none",
                        "description": query, "audioLanguage": v.get("lang", "")})
        return out

    def channels(self, ids):
        return [{"id": i, "subscribers": 1_000_000 if i == "big" else 20_000} for i in ids]


def _many(n, views, lang, ch="c1", title=None):
    return [{"views": views, "lang": lang, "ch": ch, **({"title": title} if title else {})} for _ in range(n)]


def test_a_result_counts_only_in_its_own_language():
    assert idiomas.in_language({"audioLanguage": "pt-BR"}, "pt") is True
    assert idiomas.in_language({"audioLanguage": "en"}, "pt") is False
    assert idiomas.in_language({"title": "Por qué nadie vive en la isla de las serpientes"}, "es") is True
    assert idiomas.in_language({"title": "Why nobody lives on snake island"}, "es") is False
    assert idiomas.in_language({"title": "Simone Biles 2016"}, "es") is None        # nothing says: not counted


def test_the_quota_keeps_room_for_the_queue_and_its_own_daily_cap(tmp_path):
    api = FakeAPI({}, left=3_500)
    budget = idiomas.Budget(tmp_path, api, {"gaps_units_per_day": 3000, "keep_for_queue": 3000}, today="2026-11-22")
    assert budget.left() == 500 and budget.allows(205) and not budget.allows(600)
    budget.spend(205)
    again = idiomas.Budget(tmp_path, FakeAPI({}, left=100_000), {"gaps_units_per_day": 3000}, today="2026-11-22")
    assert again.spent == 205 and again.left() == 2795                              # kept across processes
    assert again.topics_today(6) == 2795 // (idiomas.UNITS_FIRST + 5 * idiomas.UNITS_PER_LANGUAGE)
    assert idiomas.Budget(tmp_path, api, {}, today="2026-11-23").spent == 0         # a new day


def test_origin_and_spanish_first_the_rest_only_past_the_minimum_and_the_two_readings(tmp_path):
    data = {
        ("snake island", 365): _many(20, 900_000, "en", ch="big") + _many(5, 50_000, "pt"),   # pt results don't count in en
        ("snake island", 30): _many(30, 5_000, "en"), ("snake island", 0): _many(5, 1, "en"),
        ("isla serpientes", 365): _many(10, 40_000, "es"), ("isla serpientes", 30): _many(25, 900, "es"),
        ("ilha cobras", 365): _many(8, 30_000, "pt"), ("ilha cobras", 30): _many(1, 900, "pt"),
        ("schlangeninsel", 365): _many(3, 90_000, "de"), ("schlangeninsel", 30): _many(4, 900, "de"),
    }
    api = FakeAPI(data)
    budget = idiomas.Budget(tmp_path, api, {"gaps_units_per_day": 10_000, "keep_for_queue": 0})
    told = lambda q, langs: {"origin": "en", "queries": {"en": "snake island", "es": "isla serpientes",
                                                          "pt": "ilha cobras", "de": "schlangeninsel"}}
    result = idiomas.table(api, budget, "snake island", ["es", "en", "pt", "de", "fr"], {"idiomas_min_demand": 20_000}, told)
    assert [s[0] for s in api.searches[:5]] == ["snake island"] * 3 + ["isla serpientes"] * 2   # origin, then Spanish
    en = result["languages"]["en"]
    assert en["demand"] == 900_000 and en["inLanguage"] == 0.8 and en["bigShare"] == 1.0
    assert result["skipped"]["fr"] == "sin búsqueda traducida"
    rows = {r["lang"]: r for r in result["readings"]["rows"]}
    assert rows["pt"]["gap"] == 30.0 and rows["es"]["gap"] == 22.5
    assert [r["lang"] for r in result["readings"]["dub"]][:1] == ["pt"]             # biggest gap, few uploads
    assert "es" not in [r["lang"] for r in result["readings"]["dub"]]               # 25 uploads a month: crowded


def test_a_topic_under_the_minimum_spends_nothing_on_the_other_languages(tmp_path):
    data = {("tiny", 365): _many(5, 2_000, "en"), ("tiny", 30): [], ("tiny", 0): [],
            ("pequeño", 365): _many(5, 2_000, "es"), ("pequeño", 30): []}
    api = FakeAPI(data)
    told = lambda q, langs: {"origin": "en", "queries": {"en": "tiny", "es": "pequeño", "pt": "pequeno"}}
    result = idiomas.table(api, idiomas.Budget(tmp_path, api, {"keep_for_queue": 0}), "tiny", ["es", "en", "pt"],
                           {"idiomas_min_demand": 20_000}, told)
    assert "pt" not in result["languages"] and "mínimo" in result["skipped"]["pt"]
    assert not any(q == "pequeno" for q, _, _ in api.searches)
    assert result["readings"]["dub"] == [] and result["readings"]["dubNote"]


def test_what_does_not_fit_today_waits_and_says_so(tmp_path):
    data = {("a", 365): _many(5, 90_000, "en"), ("a", 30): [], ("a", 0): []}
    api = FakeAPI(data, left=idiomas.UNITS_FIRST + 10)
    told = lambda q, langs: {"origin": "en", "queries": {"en": "a", "es": "b"}}
    result = idiomas.table(api, idiomas.Budget(tmp_path, api, {"keep_for_queue": 0}), "a", ["es", "en"], {}, told)
    assert "en" in result["languages"] and result["skipped"]["es"] == "no cabe en la cuota de hoy: mañana"


def test_a_stored_topic_is_measured_in_every_language_and_kept_next_to_it(tmp_path):
    from pipeline import huecos

    (tmp_path / "config.yaml").write_text("radar: {idiomas: [es, en], keep_for_queue: 0}\n")
    huecos._write(tmp_path, {"items": {"isla serpientes": {"name": "Isla de las serpientes", "query_es": "isla serpientes",
                                                           "query_en": "snake island", "score": 7}}})
    data = {("snake island", 365): _many(5, 90_000, "en"), ("snake island", 30): [], ("snake island", 0): [],
            ("isla serpientes", 365): _many(5, 3_000, "es"), ("isla serpientes", 30): []}
    told = lambda q, langs: {"origin": "en", "queries": {"en": "snake island", "es": "isla serpientes"}}
    item = huecos.evaluate_languages(tmp_path, "Isla de las serpientes", api=FakeAPI(data), translate_fn=told)
    assert item["score"] == 7 and set(item["idiomas"]["languages"]) == {"en", "es"}
    assert huecos._read(tmp_path)["items"]["isla serpientes"]["idiomas"]["origin"] == "en"
