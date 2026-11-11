"""Atlas escrito a partir de un guion y de la descripción exacta de sus escenas (fase 8 del plan Atlas).

    python main.py --atlas-guion <carpeta>        (materiales/<carpeta>/)

La carpeta lleva:
  guion.txt      el texto de la voz, tal cual se dice
  voz.mp3        la voz grabada (opcional: sin ella se hace un borrador mudo con tiempos estimados)
  escenas.md     qué debe salir en pantalla, escena a escena, en texto libre    ┐ una de las dos
  escenas.json   el storyboard ya escrito (remotion/atlas/schema.ts) + "data"   ┘

Pasos: tiempos de la voz (Whisper, o estimados) → storyboard (la IA lo escribe a partir de escenas.md con el catálogo
docs/atlas-authoring.md, o escenas.json tal cual) → validación con el esquema zod y las anclas (los errores vuelven a la
IA, dos intentos) → datos geográficos (npm run atlas:data) → hoja de contactos (npm run atlas:stills) → render.

Nunca inventa datos: la IA sólo puede usar cifras, fechas y nombres del guion o de escenas.md, y las geografías salen de
datos públicos descargados por los scripts.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PUBLIC = PROJECT_ROOT / "public"
WORDS_PER_SECOND = 2.6          # borrador mudo: ritmo de una voz en off tranquila
SENTENCE_PAUSE = 0.35
PREINSTALLED_CHROME = Path("/opt/pw-browsers/chromium-1243/chrome-linux64/chrome")

SYSTEM = """
Eres el guionista visual del sistema Atlas (Remotion). Conviertes un guion y la descripción de sus escenas en un
storyboard JSON que cumple EXACTAMENTE el esquema del catálogo de abajo.

Reglas:
- Una escena por idea; nunca una pantalla quieta más de ~8 s sin un revelado nuevo.
- Cada momento ("start", "at") es un ancla a la voz: {"say": "frase literal del guion"} de 2-6 palabras que aparezcan
  tal cual en el guion; si se repite, añade "nth" (1, 2…). Usa {"t": segundos} sólo si no hay frase posible.
- Las escenas van en orden y cada "start" es posterior al anterior. La primera empieza en {"t": 0}.
- Textos en pantalla cortos (2-6 palabras), en el idioma del guion; titulares con la palabra clave entre *asteriscos*.
- SOLO cifras, fechas y nombres que estén en el guion o en la descripción de escenas. Si falta un dato, no lo inventes:
  deja fuera ese elemento.
- Coordenadas reales [lon, lat] de los lugares que se nombran.
- Toda geografía que uses (paquetes de región, contornos, perfiles, rejillas, bloques 3D, países) la declaras en "data"
  para que se genere; las rutas de archivo del storyboard deben coincidir con lo que genera "data".
- meta.brand: {"name": "ATLAS", "icon": "✦"} salvo que se pida otra marca. meta.slug: el que te doy.
- Vídeos de accidentes aéreos (hay un vuelo en "data"): el 3D de cerca (atlas-flight-cam) va SOLO en los momentos
  fuertes, 5-15 s cada uno y unos 60-90 s en total por cada 10 min de vídeo (es lento de renderizar):
    1) gancho, en los primeros 10 s: el avión en el momento crítico, cámara chase u orbit, sin explicar aún;
    2) el fallo (aves, motor, aviso): chase o side, con "pfd" en una esquina;
    3) la decisión en cabina: mode cockpit con cockpitPanel, mientras la voz cita el CVR;
    4) la aproximación final: ground (teleobjetivo, desde la orilla o un testigo) o side;
    5) el desenlace: el 3D puede llegar al impacto para informar, con "impact": {"clock": hora del contacto del
       informe, "label": "HH:MM:SS · IMPACTO"}: el avión se desvanece en el punto real y queda una marca. Nunca fuego,
       restos, víctimas ni repeticiones del choque; después, un mapa, un perfil o atlas-known.
  Lo demás (contexto, datos, causas, recomendaciones) con mapas, perfiles, cabina en texto y gráficos.
  El bloque 3D de cerca: {"kind": "terrain", ..., "cols": 800, "zoom": 14, "smooth": 1, "region": "<región del caso>"}.
  Pon "model" (el tipo del informe), "registration" (la del informe) y "livery" si el caso la trae; en los tramos a
  tiempo real (rate 1) añade "engineSound": {"file": "accidentes/<caso>/motores.mp3", "volume": 0.5}.

Devuelve SOLO JSON: {"storyboard": {...}, "data": [...]}

Formato de "data" (cada elemento):
  {"kind": "region", "id": "andes", "bbox": [[lonMin, latMin], [lonMax, latMax]],
   "projection": {"type": "conicConformal", "rotate": [-lon0, 0], "parallels": [lat1, lat2]}, "width": 5600, "zoom": 7}
     → atlas-data/regions/<id>/  (usa "region": "<id>" en atlas-relief-map)
  {"kind": "contour", "region": "<id>", "meters": 3000}  → atlas-data/regions/<id>/contour-3000.geojson
  {"kind": "country", "name": "Greenland", "id": "greenland"}  → atlas-data/shapes/<id>.geojson
  {"kind": "profile", "id": "lima-la-paz", "from": [lon, lat], "to": [lon, lat]}  → atlas-data/profiles/<id>.json
  {"kind": "cells", "id": "altiplano", "bbox": [lonMin, latMin, lonMax, latMax]}  → atlas-data/cells/<id>.json
  {"kind": "terrain", "id": "altiplano-3d", "bbox": [lonMin, latMin, lonMax, latMax], "cols": 400, "zoom": 8,
   "contourStep": 1000, "smooth": 2}  → atlas-data/terrain/<id>/  (usa "terrain": "<id>" en atlas-terrain-3d)
  {"kind": "flight", "case": "us1549", "table": "<URL de la tabla del FDR del expediente público, .zip o .csv>"}
     → accidentes/<case>/vuelo.json (necesita scripts/accidentes/casos/<case>.json escrito a mano, con sus fuentes)
El globo (atlas-data/globe) existe siempre.

CATÁLOGO
""".strip()


def _npm(*args: str, check: bool = True, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["npm", "run", "-s", *args], cwd=PROJECT_ROOT, text=True, capture_output=True, check=check,
                          env={**os.environ, **(env or {})})


def estimated_transcript(script: str) -> dict[str, Any]:
    """Tiempos por palabra estimados del guion (borrador sin voz): mismo formato que pipeline/transcribe.py."""

    words: list[dict[str, Any]] = []
    t = 0.4
    for token in script.split():
        dur = max(0.18, len(token) / (WORDS_PER_SECOND * 5.2))
        words.append({"word": token, "start": round(t, 3), "end": round(t + dur, 3)})
        t += 1 / WORDS_PER_SECOND
        if re.search(r"[.!?…:;]$", token):
            t += SENTENCE_PAUSE
    return {"text": script, "words": words, "duration_seconds": round(t + 1.5, 2), "estimated": True}


def spoken_script(text: str) -> str:
    """El guion tal como se dice: sin las líneas de capítulo («## LA MANCHA SOBRE EL MAPA», pipeline/capitulos.py)."""

    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#")).strip()


def voice_timings(voice: Path) -> dict[str, Any] | None:
    """Los tiempos por palabra que ya dejó la voz sintética (voz.palabras.json de GenAIPro, pipeline/tts.py), si son
    de este voz.mp3: así no hace falta Whisper."""

    try:
        from pipeline import tts
    except Exception:          # sin las dependencias del pipeline de voz: se transcribe
        return None
    found = tts.timings(voice)
    if not found:
        return None
    return {"words": found["words"], "duration_seconds": found["duration"], "source": "genaipro"}


def data_commands(spec: dict[str, Any], slug: str) -> list[list[str]]:
    """Las órdenes de npm run atlas:data para un elemento de "data". Lanza ValueError si está incompleto."""

    kind = spec.get("kind")
    if kind == "region":
        region = {k: spec[k] for k in ("id", "bbox", "projection")}
        region["width"] = int(spec.get("width", 5600))
        region["zoom"] = int(spec.get("zoom", 7))
        region.update({k: spec[k] for k in ("margin", "water") if k in spec})      # mapas de ciudad (accidentes)
        path = PROJECT_ROOT / "scripts" / "atlas-data" / "regions" / f"{spec['id']}.json"
        path.write_text(json.dumps(region, indent=2) + "\n", encoding="utf-8")
        return [["atlas:data", "--", "region", spec["id"]]]
    if kind == "contour":
        return [["atlas:data", "--", "contour", spec["region"], str(int(spec["meters"]))]]
    if kind == "country":
        return [["atlas:data", "--", "country", spec["name"], spec.get("id", spec["name"].lower())]]
    if kind == "profile":
        a, b = spec["from"], spec["to"]
        return [["atlas:data", "--", "profile", spec["id"], f"{a[0]},{a[1]}", f"{b[0]},{b[1]}"]]
    if kind == "cells":
        cmd = ["atlas:data", "--", "cells", spec["id"], ",".join(str(v) for v in spec["bbox"]), str(int(spec.get("zoom", 9)))]
        if spec.get("peaks"):
            cmd += ["--peaks", str(spec["peaks"])]
        return [cmd]
    if kind == "terrain":
        return [["atlas:data", "--", "terrain", spec["id"], ",".join(str(v) for v in spec["bbox"]), str(int(spec.get("cols", 400))),
                 str(int(spec.get("zoom", 8))), str(int(spec.get("contourStep", 1000))), str(int(spec.get("smooth", 1))),
                 *([spec["region"]] if spec.get("region") else [])]]
    if kind == "flight-ground":
        return [["atlas:data", "--", "flight-ground", f"public/accidentes/{spec['case']}/vuelo.json"]]
    raise ValueError(f"data: tipo desconocido {kind!r} en {spec}")


def data_output(spec: dict[str, Any]) -> Path:
    """Archivo que demuestra que un elemento de "data" ya está generado (para no repetirlo)."""

    base = PUBLIC / "atlas-data"
    kind = spec["kind"]
    return {
        "region": lambda: base / "regions" / spec["id"] / "meta.json",
        "contour": lambda: base / "regions" / spec["region"] / f"contour-{int(spec['meters'])}.geojson",
        "country": lambda: base / "shapes" / f"{spec.get('id', spec['name'].lower())}.geojson",
        "profile": lambda: base / "profiles" / f"{spec['id']}.json",
        "cells": lambda: base / "cells" / f"{spec['id']}.json",
        "terrain": lambda: base / "terrain" / spec["id"] / "meta.json",
        "flight": lambda: PUBLIC / "accidentes" / spec["case"] / "vuelo.json",
    }[kind]()


def build_flight(spec: dict[str, Any], log: Callable[[str], None] = print) -> None:
    """Un vuelo real: la tabla del FDR (URL del expediente público o ruta local, .csv o .zip) → vuelo.py con el caso
    scripts/accidentes/casos/<case>.json → el terreno bajo la trayectoria (atlas:data flight-ground)."""

    import urllib.request
    import zipfile

    case = spec["case"]
    table = str(spec["table"])
    cache = PROJECT_ROOT / ".cache" / "accidentes" / case
    cache.mkdir(parents=True, exist_ok=True)
    if table.startswith("http"):
        local = cache / ("tabla.zip" if "zip" in table.lower() else "tabla.csv")
        if not local.exists():
            log(f"   descargando la tabla del FDR: {table}")
            urllib.request.urlretrieve(table, local)
    else:
        local = PROJECT_ROOT / table
    if local.suffix == ".zip" or zipfile.is_zipfile(local):
        with zipfile.ZipFile(local) as z:
            name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
            z.extract(name, cache)
            local = cache / name
    log(f"   python scripts/accidentes/vuelo.py {local.relative_to(PROJECT_ROOT)} scripts/accidentes/casos/{case}.json")
    done = subprocess.run(["python3", "scripts/accidentes/vuelo.py", str(local), f"scripts/accidentes/casos/{case}.json"],
                          cwd=PROJECT_ROOT, text=True, capture_output=True)
    if done.returncode != 0:
        raise RuntimeError(f"vuelo.py falló ({case}): {(done.stderr or done.stdout).strip()[-600:]}")
    for cmd in data_commands({"kind": "flight-ground", "case": case}, case):
        log(f"   npm run {' '.join(cmd)}")
        ground = _npm(*cmd, check=False)
        if ground.returncode != 0:
            raise RuntimeError(f"flight-ground falló ({case}): {(ground.stderr or ground.stdout).strip()[-600:]}")
    log(f"   python scripts/accidentes/sonido.py public/accidentes/{case}/vuelo.json")
    sound = subprocess.run(["python3", "scripts/accidentes/sonido.py", f"public/accidentes/{case}/vuelo.json"],
                           cwd=PROJECT_ROOT, text=True, capture_output=True)
    if sound.returncode != 0:                 # sin sonido el vídeo se hace igual
        log(f"   (sin sonido de motores: {(sound.stderr or sound.stdout).strip()[-200:]})")


def build_data(specs: list[dict[str, Any]], slug: str, log: Callable[[str], None] = print) -> None:
    # las regiones antes que sus contornos
    # las regiones antes que sus contornos y que los bloques 3D que toman su textura
    order = {"region": 0, "flight": 0, "country": 1, "profile": 1, "cells": 1, "terrain": 2, "contour": 2}
    for spec in sorted(specs, key=lambda s: order.get(str(s.get("kind")), 9)):
        if data_output(spec).exists():
            log(f"   datos ya generados: {data_output(spec).relative_to(PROJECT_ROOT)}")
            continue
        if spec.get("kind") == "flight":
            build_flight(spec, log)
            continue
        for cmd in data_commands(spec, slug):
            log(f"   npm run {' '.join(cmd)}")
            done = _npm(*cmd, check=False)
            if done.returncode != 0:
                raise RuntimeError(f"atlas:data falló ({spec}): {(done.stderr or done.stdout).strip()[-600:]}")
    if not (PUBLIC / "atlas-data" / "globe" / "meta.json").exists():
        _npm("atlas:data", "--", "globe")


def validate(storyboard_path: Path) -> str | None:
    """None si el storyboard es válido (esquema + anclas + duraciones); si no, el mensaje de error legible."""

    done = _npm("atlas:validate", str(storyboard_path), check=False)
    return None if done.returncode == 0 else (done.stderr or done.stdout).strip()


def catalog() -> str:
    """El catálogo de escenas para la IA: docs/atlas-authoring.md sin las imágenes."""

    text = (PROJECT_ROOT / "docs" / "atlas-authoring.md").read_text(encoding="utf-8")
    return re.sub(r"!\[[^\]]*\]\([^)]*\)\n?", "", text)


def draft(ask: Callable[[str, str], dict[str, Any]], slug: str, script: str, scenes: str, duration: float | None,
          storyboard_path: Path, transcript_rel: str, voice_rel: str | None, tries: int = 2) -> dict[str, Any]:
    """Storyboard escrito por la IA; los errores de validación se le devuelven para que los corrija."""

    system = f"{SYSTEM}\n\n{catalog()}"
    user = f"slug: {slug}\n\nGUION:\n{script}\n\nESCENAS (qué debe salir):\n{scenes}"
    for attempt in range(tries + 1):
        answer = ask(system, user)
        board = answer.get("storyboard") if isinstance(answer, dict) else None
        if not isinstance(board, dict):
            raise RuntimeError("La IA no devolvió {\"storyboard\": …}")
        board = with_audio(board, slug, transcript_rel, voice_rel, duration)
        storyboard_path.write_text(json.dumps(board, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        error = validate(storyboard_path)
        if error is None:
            return {"storyboard": board, "data": answer.get("data") or []}
        if attempt == tries:
            raise RuntimeError(f"El storyboard sigue sin validar tras {tries} correcciones:\n{error}")
        user = (f"{user}\n\nTu storyboard anterior:\n{json.dumps(answer, ensure_ascii=False)}\n\n"
                f"No valida. Corrige SOLO esto y devuélvelo entero:\n{error}")
    raise AssertionError("inalcanzable")


def with_audio(board: dict[str, Any], slug: str, transcript_rel: str, voice_rel: str | None, duration: float | None) -> dict[str, Any]:
    """La voz, la transcripción y la duración las pone el pipeline, no la IA."""

    board = json.loads(json.dumps(board))
    board.setdefault("meta", {})["slug"] = re.sub(r"[^a-z0-9-]+", "-", slug.lower()).strip("-")
    audio = {"transcript": transcript_rel}
    if voice_rel:
        audio["voice"] = voice_rel
        board["meta"].pop("duration", None)
    elif duration:
        board["meta"]["duration"] = duration
    board["audio"] = audio
    return board


def run(slug: str, *, ask: Callable[[str, str], dict[str, Any]] | None = None, transcribe: Callable[[Path], dict[str, Any]] | None = None,
        until: str | None = None, log: Callable[[str], None] = print) -> Path:
    """Todo el camino de guion + escenas a vídeo. Devuelve el storyboard (o el vídeo si se renderiza)."""

    from .context import find_video

    folder = find_video(PROJECT_ROOT, slug)          # materiales/<slug>/ o materiales/<canal>/<slug>/
    if not (folder / "guion.txt").is_file():
        raise SystemExit(f"Falta {folder.relative_to(PROJECT_ROOT)}/guion.txt")
    script = spoken_script((folder / "guion.txt").read_text(encoding="utf-8"))
    clean = re.sub(r"[^a-z0-9-]+", "-", slug.lower()).strip("-")
    work = PUBLIC / "atlas-work" / clean
    work.mkdir(parents=True, exist_ok=True)
    storyboard_path = PROJECT_ROOT / "storyboards" / f"{clean}.json"

    # 1. tiempos de la voz
    voice = next((p for p in folder.iterdir() if p.stem == "voz" and p.suffix.lower() in (".mp3", ".wav", ".m4a")), None)
    if voice is not None:
        shutil.copy2(voice, work / f"voz{voice.suffix.lower()}")
        known = voice_timings(voice)
        if known:
            log(f"1. Tiempos de la voz de voz.palabras.json ({len(known['words'])} palabras, sin Whisper)")
            transcript = known
        else:
            if transcribe is None:
                raise SystemExit("Hay voz pero no hay transcriptor (OPENAI_API_KEY para Whisper)")
            log("1. Transcribiendo la voz…")
            transcript = transcribe(voice)
        voice_rel: str | None = f"atlas-work/{clean}/voz{voice.suffix.lower()}"
        duration = None
    else:
        log("1. Sin voz: borrador mudo con tiempos estimados del guion")
        transcript = estimated_transcript(script)
        voice_rel = None
        duration = float(transcript["duration_seconds"])
    (work / "transcript.json").write_text(json.dumps(transcript, ensure_ascii=False), encoding="utf-8")
    transcript_rel = f"atlas-work/{clean}/transcript.json"

    # 2-3. storyboard
    if (folder / "escenas.json").is_file():
        log("2. Storyboard: escenas.json tal cual")
        given = json.loads((folder / "escenas.json").read_text(encoding="utf-8"))
        board = with_audio(given.get("storyboard", given), slug, transcript_rel, voice_rel, duration)
        data = given.get("data", [])
        storyboard_path.write_text(json.dumps(board, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        log("4. Datos geográficos")
        build_data(data, clean, log)
        error = validate(storyboard_path)
        if error:
            raise SystemExit(error)
    elif (folder / "escenas.md").is_file():
        if ask is None:
            raise SystemExit("escenas.md necesita la IA (LLM_API_KEY); o escribe escenas.json")
        log("2. Storyboard: la IA lo escribe a partir de escenas.md")
        result = draft(ask, slug, script, (folder / "escenas.md").read_text(encoding="utf-8"), duration,
                       storyboard_path, transcript_rel, voice_rel)
        data = result["data"]
        (work / "data.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        log("4. Datos geográficos")
        build_data(data, clean, log)
    else:
        raise SystemExit(f"Falta {folder.relative_to(PROJECT_ROOT)}/escenas.md (o escenas.json)")
    log(f"3. Storyboard válido → {storyboard_path.relative_to(PROJECT_ROOT)}")
    if until == "storyboard":
        return storyboard_path

    # 5. hoja de contactos
    log("5. Hoja de contactos…")
    stills = _npm("atlas:stills", "--", str(storyboard_path), check=False)
    if stills.returncode != 0:
        raise RuntimeError(f"atlas:stills falló: {(stills.stderr or stills.stdout).strip()[-800:]}")
    log(f"   out/stills/{clean}/contact-sheet.jpg")
    if until == "stills":
        return PROJECT_ROOT / "out" / "stills" / clean / "contact-sheet.jpg"

    # 6. render (vertical, composición AtlasShort, si escenas.json lo pide con "vertical": true)
    vertical = bool((folder / "escenas.json").is_file() and json.loads((folder / "escenas.json").read_text(encoding="utf-8")).get("vertical"))
    out = PROJECT_ROOT / "out" / clean / "atlas.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["npx", "remotion", "render", "remotion/index.ts", "AtlasShort" if vertical else "AtlasVideo", str(out),
           f"--props={storyboard_path}", "--gl=swangle"]
    browser = os.environ.get("REMOTION_BROWSER") or (str(PREINSTALLED_CHROME) if PREINSTALLED_CHROME.exists() else "")
    if browser:
        cmd.append(f"--browser-executable={browser}")
    log("6. Render…")
    subprocess.run(cmd, cwd=PROJECT_ROOT, check=True)
    log(f"   {out.relative_to(PROJECT_ROOT)}")
    return out


def is_atlas_folder(folder: Path) -> bool:
    """Un vídeo de --atlas-guion: la cola lo hace con este camino, no con el de metraje."""

    return (folder / "guion.txt").is_file() and ((folder / "escenas.json").is_file() or (folder / "escenas.md").is_file())


def make_in_queue(root: Path, slug: str, ask: Callable[[str, str], dict[str, Any]] | None, log: Callable[[str], None] = print) -> Path:
    """Desde la cola: la voz del canal (GenAIPro) si falta, el vídeo y out/<slug>/video-final.mp4, que es lo que el
    estudio y «Para subir» esperan de cualquier vídeo terminado."""

    from . import tts
    from .context import RunContext

    ctx = RunContext.create(slug, root=root)
    tts.ensure(ctx)                      # sin voz configurada sigue sin ella (borrador mudo)
    try:
        out = run(slug, ask=ask, log=log)
    except SystemExit as error:          # un fallo del vídeo no para la cola entera
        raise RuntimeError(str(error)) from None
    final = root / "out" / slug / "video-final.mp4"
    final.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(out, final)
    log(f"   {final.relative_to(root)}")
    return final
