"""Static HTML review page for a run (``<output>.report.html``).

Built only from the sidecar files next to the MP4 (timeline, QA, timing,
postflight), so it can be regenerated at any time with ``python main.py report``.
"""

from __future__ import annotations

import html
import os
from pathlib import Path
from typing import Any

from .cache import atomic_write_text, read_json
from .templates import PROJECT_ROOT


PROVIDER_LABELS = {
    "youtube": "YouTube",
    "pexels": "Pexels",
    "openai-image": "GPT Image",
    "local": "Fichero local",
    "avatar": "Avatar",
    "": "Sin media",
}
STEP_LABELS = {
    "preflight": "Comprobación del entorno",
    "transcribe": "Transcripción (Whisper)",
    "segment": "Segmentación (DeepSeek)",
    "media": "Material visual",
    "qa": "QA pre-render",
    "props": "Props y timeline",
    "render": "Render (Remotion)",
    "audio_master": "Master de audio",
    "postflight": "Postflight",
}

_CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#16181d;--muted:#5d6470;--line:#dfe3e8;--ok:#177245;--warn:#9a5b00;
--err:#b3261e;--accent:#1f5fbf;--chip:#eef1f5}
@media (prefers-color-scheme:dark){:root{--bg:#111318;--card:#1a1d24;--ink:#e8eaee;--muted:#9aa3af;
--line:#2c313a;--ok:#5fd093;--warn:#f0b354;--err:#ff8a80;--accent:#8ab4ff;--chip:#252a33}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:1180px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:24px;margin:0 0 4px}h2{font-size:18px;margin:32px 0 12px}
.muted{color:var(--muted)}.grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(170px,1fr))}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px}
.big{font-size:24px;font-weight:650}.ok{color:var(--ok)}.warn{color:var(--warn)}.err{color:var(--err)}
table{border-collapse:collapse;width:100%}td,th{padding:6px 8px;border-bottom:1px solid var(--line);
text-align:left;vertical-align:top}th{font-weight:600;color:var(--muted);font-size:13px}
.bar{height:8px;border-radius:4px;background:var(--accent);min-width:2px}
.filters{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}
.filters button{font:inherit;padding:6px 12px;border-radius:999px;border:1px solid var(--line);
background:var(--card);color:var(--ink);cursor:pointer}.filters button.on{background:var(--accent);
color:#fff;border-color:var(--accent)}
.scene{display:grid;grid-template-columns:300px 1fr;gap:16px;margin-bottom:12px}
@media (max-width:760px){.scene{grid-template-columns:1fr}}
.scene img,.scene video{width:100%;border-radius:8px;background:#000;display:block}
.thumbs{display:grid;gap:6px}.nomedia{border:1px dashed var(--line);border-radius:8px;padding:28px 8px;
text-align:center;color:var(--muted)}
.chip{display:inline-block;background:var(--chip);border-radius:999px;padding:1px 10px;font-size:13px;
margin:0 4px 4px 0}.title{font-size:17px;font-weight:650;margin:2px 0 6px}
dl{display:grid;grid-template-columns:max-content 1fr;gap:2px 12px;margin:8px 0}dt{color:var(--muted)}
dd{margin:0;overflow-wrap:anywhere}details{margin-top:8px}summary{cursor:pointer;color:var(--accent)}
.issue{margin:4px 0;padding:4px 8px;border-left:3px solid var(--warn)}.issue.err{border-color:var(--err)}
a{color:var(--accent)}code{background:var(--chip);padding:1px 5px;border-radius:4px}
.cands{overflow-x:auto}.cands img{width:150px}
"""

_JS = """
const buttons=[...document.querySelectorAll('.filters button')];
function apply(){const active=buttons.filter(b=>b.classList.contains('on')).map(b=>b.dataset.f);
document.querySelectorAll('.scene').forEach(s=>{const tags=s.dataset.tags.split(' ');
s.style.display=active.every(f=>tags.includes(f))?'':'none';});}
buttons.forEach(b=>b.addEventListener('click',()=>{b.classList.toggle('on');apply();}));
"""


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)


def _clock(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    minutes, rest = divmod(seconds, 60)
    return f"{int(minutes)}:{rest:04.1f}"


def _duration(seconds: float) -> str:
    seconds = float(seconds)
    if seconds < 90:
        return f"{seconds:.1f} s"
    minutes, rest = divmod(int(round(seconds)), 60)
    if minutes < 90:
        return f"{minutes} min {rest:02d} s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes:02d} min"


def _media_href(url: object, report_dir: Path, project_root: Path) -> str:
    """Turn a props URL into something the report page can load."""

    if not isinstance(url, str) or not url:
        return ""
    if url.startswith(("http://", "https://")):
        return url
    local = project_root / "public" / url.lstrip("/")
    try:
        return Path(os.path.relpath(local, report_dir)).as_posix()
    except ValueError:  # different drive on Windows
        return local.as_uri()


def _is_video(url: object) -> bool:
    return isinstance(url, str) and url.lower().split("?")[0].endswith((".mp4", ".mov", ".webm", ".m4v"))


def _visual(url: object, poster: object, report_dir: Path, project_root: Path) -> str:
    href = _media_href(url, report_dir, project_root)
    poster_href = _media_href(poster, report_dir, project_root)
    if href and _is_video(url):
        poster_attr = f' poster="{_e(poster_href)}"' if poster_href else ""
        return f'<video src="{_e(href)}" controls muted loop preload="none"{poster_attr}></video>'
    if href:
        return f'<img src="{_e(href)}" loading="lazy" alt="">'
    if poster_href:
        return f'<img src="{_e(poster_href)}" loading="lazy" alt="">'
    return ""


def _scene_visuals(scene: dict[str, Any], report_dir: Path, project_root: Path) -> str:
    blocks: list[str] = []
    sheet = scene.get("mediaContactSheet")
    if sheet and not scene.get("shots"):
        blocks.append(_visual(sheet, None, report_dir, project_root))
    for key in ("videoUrl", "imageUrl"):
        if scene.get(key):
            poster = scene.get("mediaThumbnailUrl") if key == "videoUrl" else None
            blocks.append(_visual(scene[key], poster, report_dir, project_root))
    for shot in scene.get("shots") or []:
        if not isinstance(shot, dict):
            continue
        if shot.get("contactSheet"):
            blocks.append(_visual(shot["contactSheet"], None, report_dir, project_root))
        else:
            blocks.append(_visual(shot.get("url"), shot.get("thumbnailUrl"), report_dir, project_root))
    blocks = [block for block in blocks if block]
    if not blocks:
        return '<div class="nomedia">Sin media<br><span class="muted">plantilla gráfica</span></div>'
    return '<div class="thumbs">' + "".join(blocks) + "</div>"


def _source_rows(scene: dict[str, Any]) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    if scene.get("mediaSourceUrl"):
        url = str(scene["mediaSourceUrl"])
        label = scene.get("mediaSourceTitle") or url
        link = f'<a href="{_e(url)}" target="_blank" rel="noopener">{_e(label)}</a>' if url.startswith("http") else _e(url)
        rows.append(("Fuente", link))
    author = scene.get("mediaUploader") or scene.get("mediaPhotographer")
    if author:
        rows.append(("Autor", _e(author)))
    if scene.get("mediaStartSeconds") is not None and scene.get("mediaEndSeconds") is not None:
        rows.append(
            (
                "Tramo del original",
                f"{_clock(scene['mediaStartSeconds'])} – {_clock(scene['mediaEndSeconds'])} "
                f"({float(scene.get('mediaClipDurationSeconds') or 0):.2f} s)",
            )
        )
    if scene.get("mediaQuery"):
        rows.append(("Consulta", _e(scene["mediaQuery"])))
    scores: list[str] = []
    if scene.get("mediaVisualScore") is not None:
        scores.append(f"visual {float(scene['mediaVisualScore']):.2f}")
    if scene.get("mediaSelectionScore") is not None:
        scores.append(f"subtítulos {float(scene['mediaSelectionScore']):.2f}")
    if scene.get("mediaRelevanceScore") is not None:
        scores.append(f"ranking {float(scene['mediaRelevanceScore']):.0f}")
    if scores:
        rows.append(("Puntuación", _e(" · ".join(scores))))
    if scene.get("mediaSelectionReason"):
        rows.append(("Motivo", _e(scene["mediaSelectionReason"])))
    if scene.get("mediaTranscriptExcerpt"):
        rows.append(("Subtítulos del clip", _e(scene["mediaTranscriptExcerpt"])))
    if scene.get("visualIntent"):
        rows.append(("Intención visual", _e(scene["visualIntent"])))
    if scene.get("keywords"):
        rows.append(("Keywords", _e(", ".join(str(item) for item in scene["keywords"]))))
    return rows


def _shots_table(scene: dict[str, Any]) -> str:
    shots = [shot for shot in scene.get("shots") or [] if isinstance(shot, dict)]
    if not shots:
        return ""
    rows = []
    for number, shot in enumerate(shots, start=1):
        provider = PROVIDER_LABELS.get(str(shot.get("provider") or ""), str(shot.get("provider") or ""))
        source = str(shot.get("sourceUrl") or "")
        title = shot.get("sourceTitle") or shot.get("query") or source
        link = f'<a href="{_e(source)}" target="_blank" rel="noopener">{_e(title)}</a>' if source.startswith("http") else _e(title)
        tramo = ""
        if shot.get("startSeconds") is not None and shot.get("endSeconds") is not None:
            tramo = f"{_clock(shot['startSeconds'])} – {_clock(shot['endSeconds'])}"
        score = f"{float(shot['visualScore']):.2f}" if shot.get("visualScore") is not None else ""
        rows.append(
            f"<tr><td>{number}</td><td>{_e(provider)}</td><td>{link}</td><td>{_e(tramo)}</td><td>{_e(score)}</td></tr>"
        )
    return (
        "<details open><summary>Planos del montaje</summary><table><tr><th>#</th><th>Origen</th>"
        "<th>Fuente</th><th>Tramo</th><th>Visual</th></tr>" + "".join(rows) + "</table></details>"
    )


def _trace_block(scene: dict[str, Any], report_dir: Path, project_root: Path) -> str:
    traces = [trace for trace in scene.get("mediaSelectionTrace") or [] if isinstance(trace, dict)]
    if not traces:
        return ""
    parts: list[str] = []
    for trace in traces:
        head = f"Resultado: <code>{_e(trace.get('outcome', ''))}</code>"
        if trace.get("keyword"):
            head = f"«{_e(trace['keyword'])}» · " + head
        if trace.get("totalSeconds") is not None:
            head += f" · {_duration(trace['totalSeconds'])}"
        queries = ", ".join(str(query) for query in trace.get("queries") or [])
        rows = []
        for finalist in trace.get("finalists") or []:
            if not isinstance(finalist, dict):
                continue
            sheet = _media_href(finalist.get("contactSheet"), report_dir, project_root)
            image = f'<img src="{_e(sheet)}" loading="lazy" alt="">' if sheet else ""
            visual = f"{float(finalist['visualScore']):.2f}" if finalist.get("visualScore") is not None else "–"
            mark = "✓ " if finalist.get("selected") else ""
            note = finalist.get("reason") or finalist.get("error") or ""
            rows.append(
                f"<tr><td>{image}</td><td>{mark}<a href=\"{_e(finalist.get('url', ''))}\" target=\"_blank\" "
                f"rel=\"noopener\">{_e(finalist.get('title') or finalist.get('videoId', ''))}</a><br>"
                f"<span class=\"muted\">{_e(finalist.get('uploader', ''))} · "
                f"{_clock(finalist.get('startSeconds', 0))} – {_clock(finalist.get('endSeconds', 0))}</span></td>"
                f"<td>{_e(visual)}</td><td>{float(finalist.get('relevanceScore') or 0):.2f}</td>"
                f"<td>{_e(note)}</td></tr>"
            )
        table = (
            '<div class="cands"><table><tr><th>Contact sheet</th><th>Candidato</th><th>Visual</th>'
            "<th>Subt.</th><th>Motivo</th></tr>" + "".join(rows) + "</table></div>"
            if rows
            else ""
        )
        errors = "".join(f'<div class="issue err">{_e(error)}</div>' for error in trace.get("searchErrors") or [])
        judge = f'<div class="issue err">{_e(trace["judgeError"])}</div>' if trace.get("judgeError") else ""
        parts.append(
            f"<p>{head}<br><span class=\"muted\">Búsquedas: {_e(queries)}</span></p>{errors}{judge}{table}"
        )
    return "<details><summary>Candidatos de YouTube comparados</summary>" + "".join(parts) + "</details>"


def _scene_block(
    scene: dict[str, Any],
    issues: list[dict[str, Any]],
    timing: dict[str, Any] | None,
    report_dir: Path,
    project_root: Path,
) -> str:
    provider = str(scene.get("mediaProvider") or "")
    has_media = bool(scene.get("videoUrl") or scene.get("imageUrl") or scene.get("shots"))
    if not provider and has_media:
        provider = "pexels" if any(str(scene.get(key, "")).startswith("http") for key in ("videoUrl", "imageUrl")) else "local"
    tags = [f"p-{provider or 'none'}"]
    if any(issue.get("level") == "warning" for issue in issues):
        tags.append("warn")
    if any(issue.get("level") == "error" for issue in issues):
        tags.append("err")
    chips = [
        f'<span class="chip">{_clock(scene.get("startSeconds", 0))} – {_clock(scene.get("endSeconds", 0))}</span>',
        f'<span class="chip">{float(scene.get("durationSeconds") or 0):.1f} s</span>',
        f'<span class="chip">{_e(scene.get("templateName", ""))}</span>',
        f'<span class="chip">{_e(scene.get("sceneType", ""))}</span>',
        f'<span class="chip">{_e(PROVIDER_LABELS.get(provider if has_media else "", provider))}</span>',
    ]
    if timing and timing.get("reused"):
        chips.append('<span class="chip">reutilizada</span>')
    elif timing and timing.get("thirdPartySeconds"):
        chips.append(f'<span class="chip">YouTube: {_duration(timing["thirdPartySeconds"])}</span>')
    issue_html = "".join(
        f'<div class="issue {"err" if issue.get("level") == "error" else ""}">'
        f'<code>{_e(issue.get("code", ""))}</code> {_e(issue.get("message", ""))}</div>'
        for issue in issues
    )
    rows = "".join(f"<dt>{_e(label)}</dt><dd>{value}</dd>" for label, value in _source_rows(scene))
    return (
        f'<section class="card scene" data-tags="{_e(" ".join(tags))}" id="escena-{_e(scene.get("sceneIndex", ""))}">'
        f"<div>{_scene_visuals(scene, report_dir, project_root)}</div><div>"
        f'<div class="muted">Escena {_e(scene.get("sceneIndex", ""))}</div>'
        f'<div class="title">{_e(scene.get("text", "") or "(sin texto)")}</div>'
        f"<div>{''.join(chips)}</div>{issue_html}<dl>{rows}</dl>"
        f"{_shots_table(scene)}{_trace_block(scene, report_dir, project_root)}</div></section>"
    )


def _steps_block(timing: dict[str, Any]) -> str:
    steps = [step for step in timing.get("steps") or [] if isinstance(step, dict)]
    if not steps:
        return ""
    longest = max((float(step.get("seconds") or 0) for step in steps), default=0) or 1.0
    rows = []
    for step in steps:
        seconds = float(step.get("seconds") or 0)
        name = STEP_LABELS.get(str(step.get("name")), str(step.get("name")))
        notes = []
        if step.get("cached"):
            notes.append("caché")
        if step.get("status") == "error":
            notes.append("falló")
        note = f' <span class="muted">({", ".join(notes)})</span>' if notes else ""
        rows.append(
            f"<tr><td>{_e(name)}{note}</td><td>{_e(_duration(seconds))}</td>"
            f'<td style="width:55%"><div class="bar" style="width:{max(0.5, 100 * seconds / longest):.1f}%"></div></td></tr>'
        )
    counters = timing.get("counters") or {}
    counter_rows = "".join(f"<tr><td><code>{_e(key)}</code></td><td>{_e(value)}</td></tr>" for key, value in counters.items())
    counter_block = (
        f"<details><summary>Contadores de llamadas</summary><table>{counter_rows}</table></details>" if counter_rows else ""
    )
    return (
        "<h2>Tiempos por paso</h2><div class=\"card\"><table><tr><th>Paso</th><th>Tiempo</th><th></th></tr>"
        + "".join(rows)
        + f"</table>{counter_block}</div>"
    )


def render_report_html(
    *,
    title: str,
    timeline: dict[str, Any],
    qa: dict[str, Any] | None,
    timing: dict[str, Any] | None,
    postflight: dict[str, Any] | None,
    report_dir: Path,
    project_root: Path = PROJECT_ROOT,
    video_name: str | None = None,
) -> str:
    scenes = [scene for scene in timeline.get("scenes") or [] if isinstance(scene, dict)]
    issues_by_scene: dict[int, list[dict[str, Any]]] = {}
    global_issues: list[dict[str, Any]] = []
    for issue in (qa or {}).get("issues") or []:
        if not isinstance(issue, dict):
            continue
        if issue.get("scene_index") is None:
            global_issues.append(issue)
        else:
            issues_by_scene.setdefault(int(issue["scene_index"]), []).append(issue)
    timing_by_scene = {
        int(item["index"]): item
        for item in (timing or {}).get("scenes") or []
        if isinstance(item, dict) and item.get("index") is not None
    }

    provider_counts: dict[str, int] = {}
    for scene in scenes:
        has_media = bool(scene.get("videoUrl") or scene.get("imageUrl") or scene.get("shots"))
        key = str(scene.get("mediaProvider") or ("pexels" if has_media else "")) if has_media else ""
        provider_counts[key] = provider_counts.get(key, 0) + 1

    all_issues = [issue for issue in (qa or {}).get("issues") or [] if isinstance(issue, dict)]
    errors = sum(1 for issue in all_issues if issue.get("level") == "error")
    warnings = sum(1 for issue in all_issues if issue.get("level") == "warning")
    if qa is None:
        qa_card = '<div class="big muted">–</div><div class="muted">QA no ejecutada</div>'
    elif errors:
        qa_card = f'<div class="big err">{errors} errores</div><div class="muted">{warnings} avisos de QA</div>'
    else:
        qa_card = f'<div class="big ok">QA correcta</div><div class="muted">{warnings} avisos</div>'
    if postflight is None:
        post_card = '<div class="big muted">–</div><div class="muted">sin render todavía</div>'
    elif postflight.get("issues"):
        post_card = f'<div class="big err">{len(postflight["issues"])} problemas</div><div class="muted">postflight</div>'
    else:
        post_card = '<div class="big ok">Render verificado</div><div class="muted">postflight correcto</div>'

    cards = [
        f'<div class="card"><div class="big">{len(scenes)}</div><div class="muted">escenas · '
        f'{_duration(timeline.get("totalDurationSeconds") or 0)}</div></div>',
        f'<div class="card">{qa_card}</div>',
        f'<div class="card">{post_card}</div>',
    ]
    if timing:
        cards.append(
            f'<div class="card"><div class="big">{_e(_duration(timing.get("totalSeconds") or 0))}</div>'
            f'<div class="muted">tiempo total del run</div></div>'
        )
    for key, count in sorted(provider_counts.items(), key=lambda item: -item[1]):
        cards.append(
            f'<div class="card"><div class="big">{count}</div><div class="muted">{_e(PROVIDER_LABELS.get(key, key))}</div></div>'
        )

    filters = ['<button data-f="warn">Solo con avisos</button>', '<button data-f="err">Solo con errores</button>']
    for key in sorted(provider_counts):
        filters.append(f'<button data-f="p-{_e(key or "none")}">{_e(PROVIDER_LABELS.get(key, key))}</button>')

    global_html = "".join(
        f'<div class="issue {"err" if issue.get("level") == "error" else ""}"><code>{_e(issue.get("code", ""))}</code> '
        f'{_e(issue.get("message", ""))}</div>'
        for issue in global_issues
    )
    post_html = "".join(
        f'<div class="issue err"><code>{_e(issue.get("code", ""))}</code> {_e(issue.get("message", ""))}</div>'
        for issue in (postflight or {}).get("issues") or []
        if isinstance(issue, dict)
    )
    video_html = (
        f'<p><a href="{_e(video_name)}">Abrir el vídeo final</a></p>' if video_name else ""
    )
    scene_html = "".join(
        _scene_block(
            scene,
            issues_by_scene.get(int(scene.get("sceneIndex") or 0), []),
            timing_by_scene.get(int(scene.get("sceneIndex") or 0)),
            report_dir,
            project_root,
        )
        for scene in scenes
    )
    return (
        '<!doctype html><html lang="es"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{_e(title)} · revisión</title><style>{_CSS}</style></head><body><main>"
        f"<h1>{_e(title)}</h1><div class=\"muted\">Revisión del run</div>{video_html}"
        f'<div class="grid" style="margin-top:16px">{"".join(cards)}</div>{global_html}{post_html}'
        f"{_steps_block(timing or {})}"
        f'<h2>Escenas</h2><div class="filters">{"".join(filters)}</div>{scene_html}'
        f"</main><script>{_JS}</script></body></html>"
    )


def write_report(output_path: Path, *, project_root: Path = PROJECT_ROOT) -> Path | None:
    """Build ``<output>.report.html`` from the sidecars; ``None`` if there is no timeline yet."""

    timeline = read_json(output_path.with_suffix(".timeline.json"))
    if not isinstance(timeline, dict):
        return None
    qa = read_json(output_path.with_suffix(".qa.json"))
    timing = read_json(output_path.with_suffix(".timing.json"))
    postflight = read_json(output_path.with_suffix(".postflight.json"))
    report_path = output_path.with_suffix(".report.html")
    content = render_report_html(
        title=output_path.stem,
        timeline=timeline,
        qa=qa if isinstance(qa, dict) else None,
        timing=timing if isinstance(timing, dict) else None,
        postflight=postflight if isinstance(postflight, dict) else None,
        report_dir=report_path.parent,
        project_root=project_root,
        video_name=output_path.name if output_path.is_file() else None,
    )
    atomic_write_text(report_path, content)
    return report_path
