"""Fase 3.6: the probe that says which resources answer straight from the server (it only reports)."""

from pipeline import sonda_directo


def test_the_report_names_what_answers_directly():
    text = sonda_directo.markdown("abc", [
        {"resource": "miniaturas del storyboard (i.ytimg.com)", "status": 200, "bytes": 5000},
        {"resource": "64 KB de un formato HTTPS (googlevideo)", "status": 403, "bytes": 0},
        {"resource": "subtítulos json3 (youtube.com/api/timedtext)", "status": None, "error": "ConnectTimeout"}])
    assert "| 64 KB de un formato HTTPS (googlevideo) | 403 | 0 |" in text
    assert "Responden directo (candidatos a no pasar por el proxy): miniaturas del storyboard (i.ytimg.com)" in text
