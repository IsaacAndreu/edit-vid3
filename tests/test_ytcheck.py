from pipeline.ytcheck import verdict

OK = {"yt-dlp": "2026.8.19", "ejs": "0.8.0", "js": "deno"}


def run(label, seconds, error="", warnings=None):
    return {"label": label, "seconds": seconds, "mb": 2.7, "error": error, "warnings": warnings or {}}


def test_missing_solver_comes_first():
    lines = verdict({**OK, "js": ""}, [run("sin cookies", 60)])
    assert "deno" in lines[0] and len(lines) == 1


def test_slow_account_is_spotted():
    lines = verdict(OK, [run("con cookies", 70), run("sin cookies", 5)])
    assert any("ESA cuenta" in line for line in lines)


def test_fast_machine_points_to_the_nightly_log():
    assert "descarga bien" in verdict(OK, [run("con cookies", 4), run("sin cookies", 5)])[0]


def test_bot_check_only_without_cookies_is_not_an_alarm():
    lines = verdict(OK, [run("con cookies", 6), run("sin cookies", 3, "SourceUnavailable: Sign in to confirm")])
    assert any("no las quites" in line for line in lines) and not any("renueva" in line for line in lines)


def test_slow_everywhere_is_the_connection():
    assert "conexión" in verdict(OK, [run("con cookies", 80), run("sin cookies", 75)])[0]


def test_slow_info_points_to_deno():
    slow = {**run("con cookies", 300), "phases": {"info": 280, "download": 12}}
    assert "deno" in verdict({**OK, "line": 8.0}, [slow, {**slow, "label": "sin cookies"}])[0]


def test_fast_line_but_slow_download_is_youtube_throttling():
    slow = {**run("con cookies", 330), "phases": {"info": 5, "download": 320}}
    assert "frena a tu IP" in verdict({**OK, "line": 9.5}, [slow, {**slow, "label": "sin cookies"}])[0]


def test_slow_line_is_the_connection():
    slow = {**run("con cookies", 330), "phases": {"info": 5, "download": 320}}
    assert "conexión va lenta" in verdict({**OK, "line": 0.4}, [slow])[0]
