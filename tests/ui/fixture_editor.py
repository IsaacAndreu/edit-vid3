"""A small real project for trying the editor in a browser: python tests/ui/fixture_editor.py <folder> [port]

Makes <folder> a studio root (the repository's config, profiles, Remotion components and node_modules linked in) with
one video, «demo-editor» (channel coches): 8 shots of generated footage (ffmpeg testsrc2, each in another colour), a
photo, a chapter card, a graphic, a label, a whip transition and a 24 s narration. Then, with a port, serves the studio
there without a password (127.0.0.1), so http://127.0.0.1:<port>/#/editor/demo-editor opens the editor.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SLUG, CHANNEL, FPS, SECONDS = "demo-editor", "coches", 30, 24


def ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


def make(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for name in ("config.yaml", "canales", "formatos", "node_modules", "remotion", "templates", "assets", "main.py", "pipeline"):
        link = root / name
        if not link.exists() and (REPO / name).exists():
            link.symlink_to(REPO / name)
    folder = root / "materiales" / CHANNEL / SLUG
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "guion.txt").write_text("## El coche del futuro\nUn coche que parecía de otro planeta.\n", "utf-8")
    (folder / "titulo.txt").write_text("El coche que llegó del futuro\n", "utf-8")
    work = root / "work" / SLUG
    (work / "media").mkdir(parents=True, exist_ok=True)
    (work / "audio").mkdir(parents=True, exist_ok=True)
    shots, cursor = [], 0
    plan = [("chapter", 60), *[("broll", 75)] * 4, ("image", 75), *[("broll", 75)] * 3, ("broll", 90)]
    for i, (kind, frames) in enumerate(plan):
        sid = f"s{i + 1:03d}"
        shot = {"id": sid, "type": "chapter" if kind == "chapter" else "broll", "from": cursor, "durationInFrames": frames,
                "text": f"Frase {i + 1} del guion"}
        if kind == "chapter":
            shot["chapterTitle"], shot["chapterNumber"], shot["chapterFrames"] = "El coche del futuro", 1, frames
        elif kind == "image":
            ffmpeg("-f", "lavfi", "-i", "testsrc2=size=1280x720", "-frames:v", "1", str(work / "media" / f"{sid}.jpg"))
            shot["media"] = {"src": f"media/{sid}.jpg", "kind": "image", "source": "web", "credit": "Fuente: Archivo"}
        else:
            ffmpeg("-f", "lavfi", "-i", f"testsrc2=size=960x540:rate={FPS}:duration={frames / FPS + 1:.2f}",
                   "-vf", f"hue=h={i * 40}", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(work / "media" / f"{sid}.mp4"))
            shot["media"] = {"src": f"media/{sid}.mp4", "kind": "video", "source": "youtube", "credit": f"Fuente: Canal {i + 1}"}
        shots.append(shot)
        cursor += frames
    ffmpeg("-f", "lavfi", "-i", f"sine=frequency=220:duration={SECONDS}", "-ar", "48000", "-ac", "2", str(work / "audio" / "voz.wav"))
    timeline = {
        "slug": SLUG, "title": "El coche que llegó del futuro", "fps": FPS, "width": 1920, "height": 1080, "durationInFrames": cursor,
        "shots": shots,
        "groups": [{"id": "graphic-1", "kind": "graphic", "from": 300, "durationInFrames": 90,
                    "graphic": {"type": "kinetic", "lines": ["12.000 PEDIDOS", "EL PRIMER DÍA"]}}],
        "labels": [{"kind": "place", "text": "PARÍS, 1955", "from": 70, "durationInFrames": 75}],
        "transitions": [{"kind": "whip", "from": 129, "durationInFrames": 12}], "shakes": [],
        "audio": {"voice": "audio/voz.wav", "voiceFrom": 0, "voiceGaps": [], "speech": [[0, cursor]], "clips": [],
                  "musicParts": [], "musicVolume": 0.25, "duckedVolume": 0.03, "sfx": []},
    }
    for name in ("timeline.json", "timeline.base.json"):
        (work / name).write_text(json.dumps(timeline, ensure_ascii=False), "utf-8")
    (work / "shots.json").write_text(json.dumps({"events": [{"label": "a", "startWord": 0, "tag": "EL SALÓN"},
                                                            {"label": "b", "startWord": 50, "tag": "EL ATENTADO"}],
                                                 "shots": [{"id": s["id"], "startWord": 10 * i} for i, s in enumerate(shots)]}), "utf-8")
    return root


if __name__ == "__main__":
    target = make(Path(sys.argv[1]).resolve())
    print(f"Proyecto de prueba en {target}")
    if len(sys.argv) > 2:
        sys.path.insert(0, str(REPO))
        from pipeline import web

        web.serve(port=int(sys.argv[2]), host="127.0.0.1", root=target, open_browser=False)
