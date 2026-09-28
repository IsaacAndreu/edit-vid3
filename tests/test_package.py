from pipeline.ideas import channel_url, score
from pipeline.package import write_titles


def test_write_titles_replaces_title_block(tmp_path):
    path = tmp_path / "youtube.txt"
    path.write_text("TÍTULO\nViejo título\n\nDESCRIPCIÓN\nTexto\n", encoding="utf-8")
    write_titles(path, ["Uno", "Dos", "Tres"])
    text = path.read_text("utf-8")
    assert text.startswith("TÍTULO (elige uno)\n1. Uno\n2. Dos\n3. Tres\n\nDESCRIPCIÓN\nTexto")
    assert "Viejo" not in text


def test_score_ratio_against_channel_median_ignores_shorts():
    channel = {"channel": "C", "videos": [
        {"id": "a", "title": "a", "views": 100, "duration": 600},
        {"id": "b", "title": "b", "views": 200, "duration": 600},
        {"id": "c", "title": "c", "views": 1000, "duration": 600},
        {"id": "s", "title": "short", "views": 10**7, "duration": 40},
        {"id": "n", "title": "no views", "views": None, "duration": 600},
    ]}
    ratios = {v["id"]: v["ratio"] for v in score(channel)}
    assert ratios == {"a": 0.5, "b": 1.0, "c": 5.0}


def test_channel_url():
    assert channel_url("@GymnastIcons") == "https://www.youtube.com/@GymnastIcons/videos"
    assert channel_url("GymnastIcons") == "https://www.youtube.com/@GymnastIcons/videos"
    assert channel_url("https://www.youtube.com/@X/") == "https://www.youtube.com/@X/videos"
    assert channel_url("https://www.youtube.com/@X/videos") == "https://www.youtube.com/@X/videos"
