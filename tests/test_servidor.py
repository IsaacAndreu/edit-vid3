"""«Estado del servidor» and the weekly backup."""

import json
import tarfile
import time

from pipeline import copia, servidor


def _project(tmp_path, extra=""):
    (tmp_path / "config.yaml").write_text("sourcing:\n  youtube:\n    metadata_proxy: http://u:p@gw.example:823\n"
                                          "    metadata_proxy_mb_per_request: 1.024\n" + extra)
    return tmp_path


def test_the_proxy_balance_is_what_was_bought_minus_the_requests_since(tmp_path):
    root = _project(tmp_path)
    (root / "out").mkdir()
    (root / "out" / "_ajustes.json").write_text(json.dumps({"proxy_gb": 5, "proxy_since": "2026-10-17"}))
    log = root / "work" / "pati1" / "youtube_downloads.jsonl"
    log.parent.mkdir(parents=True)
    since = 1792195200                                       # 2026-10-17T00:00Z
    rows = [{"ts": since + 10, "proxy": "metadatos"}] * 1000 + [{"ts": since - 10, "proxy": "metadatos"}] * 50
    log.write_text("\n".join(json.dumps(r) for r in rows))
    b = servidor.proxy_balance(root)
    assert b["requests"] == 1000 and b["usedGb"] == 1.0 and b["leftGb"] == 4.0 and b["videosLeft"] == 4


def test_a_low_proxy_balance_is_told_once_a_day(tmp_path, monkeypatch):
    root = _project(tmp_path)
    (root / "out").mkdir()
    (root / "out" / "_ajustes.json").write_text(json.dumps({"proxy_gb": 0.5, "proxy_since": "2026-10-17"}))
    sent = []
    import pipeline.notify as notify

    monkeypatch.setattr(notify, "telegram", lambda ctx, text: sent.append(text))
    servidor.check_proxy(root, now=1_000_000)
    servidor.check_proxy(root, now=1_000_000 + 4000)            # an hour later: not again the same day
    assert len(sent) == 1 and "GB" in sent[0]


def test_the_backup_keeps_scripts_voices_settings_and_studio_data_not_videos(tmp_path):
    root = _project(tmp_path, f"backup:\n  dir: {tmp_path / 'copias'}\n  keep: 2\n")
    video = root / "materiales" / "patinaje" / "pati1"
    video.mkdir(parents=True)
    for name, data in (("guion.txt", "hola"), ("voz.mp3", "x"), ("clip.mp4", "big")):
        (video / name).write_text(data)
    (root / ".env").write_text("KEY=1")
    (root / "out").mkdir()
    (root / "out" / "_ajustes.json").write_text("{}")
    (root / "out" / "video-final.mp4").write_text("no")
    made = copia.make(root)
    names = tarfile.open(made).getnames()
    assert {"materiales/patinaje/pati1/guion.txt", "materiales/patinaje/pati1/voz.mp3", ".env", "out/_ajustes.json"} <= set(names)
    assert "materiales/patinaje/pati1/clip.mp4" not in names and copia.make_if_due(root) is None
    for i in range(3):
        (tmp_path / "copias" / f"edit-vid3-2020-01-0{i + 1}-0000.tar.gz").write_bytes(b"")
    time.sleep(0.01)
    copia.make(root)
    assert len(list((tmp_path / "copias").glob("*.tar.gz"))) == 2


def test_the_status_page_never_breaks_on_one_part(tmp_path):
    status = servidor.status(_project(tmp_path))
    assert status["machine"]["cores"] >= 1 and "diskFree" in status["machine"] and isinstance(status["queue"], list)
