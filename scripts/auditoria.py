"""Material to review finished videos from outside the server: what is said, what is on screen and where it came from.

    python scripts/auditoria.py avion9 negocio7 atlet2 ...      (or --canal negocios --ultimos 2)

For each video, in out/_auditoria/<slug>/:
- auditoria.txt — one line per shot: minute in the final video, the narration, the type, the source (channel and
  title of the clip, or Pexels/photo credit) and who chose it (score, judge, fallback and why). Short enough to
  paste in a chat; the wrong clips are usually obvious from the title next to the sentence.
- hoja-1.jpg, hoja-2.jpg… — a frame every 6 s, 8×8 per sheet (6.4 min), with the minute on each frame.
Then everything is zipped in out/_auditoria.zip to take it to the PC in one go:
    scp root@<servidor>:/opt/video-app/edit-vid3/out/_auditoria.zip .
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def _mmss(seconds: float) -> str:
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def _cut(text: str, n: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


def report(slug: str) -> str:
    work = ROOT / "work" / slug
    timeline = _read(work / "timeline.json")
    shots = _read(work / "shots.json")
    selections = {s["shotId"]: s for s in _read(work / "selection.json").get("selections", [])}
    fallback = {i["shotId"]: i for i in _read(work / "fallback.json").get("items", [])}
    fps = float(timeline.get("fps") or 30)
    lines = [f"# {slug} · {shots.get('title', '')}",
             f"Protagonista: {shots.get('subject') or '—'} · {len(shots.get('events') or [])} tramos · contexto: "
             f"{_cut(shots.get('context', ''), 140) or '—'}", ""]
    for shot in timeline.get("shots", []):
        sid, media = shot.get("id", ""), shot.get("media") or {}
        start = float(shot.get("from") or 0) / fps
        if shot.get("type") == "endscreen":
            lines.append(f"{_mmss(start)} pantalla final")
            continue
        sel, fb = selections.get(sid) or {}, fallback.get(sid)
        if fb:
            origin = f"relleno:{fb.get('method')} ({_cut(fb.get('reason', ''), 50)})"
            where = _cut(fb.get("credit") or fb.get("url") or "", 70)
        elif sel:
            origin = sel.get("decidedBy", "")
            where = _cut(f"{sel.get('channel') or ''} — {sel.get('title') or ''}", 90)
        else:
            origin, where = "", _cut(media.get("credit") or "", 70)
        kind = shot.get("type", "")
        if shot.get("coldOpen"):
            kind = "apertura"
        lines.append(f"{_mmss(start)} [{kind}] «{_cut(shot.get('text', ''), 80)}» → {where or '(gráfico)'}"
                     + (f" · {origin}" if origin else ""))
    return "\n".join(lines) + "\n"


def sheets(slug: str, target: Path) -> int:
    video = ROOT / "out" / slug / "video-final.mp4"
    if not video.is_file() or not shutil.which("ffmpeg"):
        return 0
    for old in target.glob("hoja-*.jpg"):
        old.unlink()
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vf",
                    "fps=1/6,scale=320:-2,drawtext=text='%{pts\\:hms}':x=4:y=4:fontsize=16:fontcolor=white:"
                    "box=1:boxcolor=black@0.6,tile=8x8", "-q:v", "5", str(target / "hoja-%d.jpg")], check=False)
    return len(list(target.glob("hoja-*.jpg")))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("slugs", nargs="*")
    parser.add_argument("--canal", help="los últimos vídeos terminados de este canal (materiales/<canal>/…)")
    parser.add_argument("--ultimos", type=int, default=2)
    parser.add_argument("--sin-hojas", action="store_true", help="solo el texto (más rápido)")
    args = parser.parse_args()
    slugs = list(args.slugs)
    if args.canal:
        done = [p.parent.name for p in (ROOT / "out").glob("*/video-final.mp4")
                if (ROOT / "materiales" / args.canal / p.parent.name).is_dir()]
        done.sort(key=lambda s: (ROOT / "out" / s / "video-final.mp4").stat().st_mtime)
        slugs += done[-args.ultimos:]
    if not slugs:
        sys.exit("Dime qué vídeos: python scripts/auditoria.py avion9 negocio7  (o --canal negocios --ultimos 2)")
    base = ROOT / "out" / "_auditoria"
    shutil.rmtree(base, ignore_errors=True)
    for slug in dict.fromkeys(slugs):
        if not (ROOT / "work" / slug / "timeline.json").is_file():
            print(f"{slug}: sin timeline.json (¿no terminado?), lo salto")
            continue
        target = base / slug
        target.mkdir(parents=True, exist_ok=True)
        (target / "auditoria.txt").write_text(report(slug), encoding="utf-8")
        count = 0 if args.sin_hojas else sheets(slug, target)
        print(f"{slug}: auditoria.txt + {count} hojas")
    archive = shutil.make_archive(str(ROOT / "out" / "_auditoria"), "zip", base)
    print(f"\nTodo en {archive}\nEn el PC:  scp root@169.58.120.193:{archive} .")


if __name__ == "__main__":
    main()
