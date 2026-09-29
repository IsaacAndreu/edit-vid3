"""Stage 2 — plan shots from words.json.

1. Chapters: taken from the script's "## " lines; if there are none, one LLM call
   proposes them (and a short global visual context used by every later query).
2. Cutting (deterministic): dynamic programming over word boundaries picks shots of
   1.5-4 s around `target_shot_seconds`, preferring sentence ends, commas and pauses,
   never cutting right after a function word, and always cutting at chapter starts.
3. Labelling (LLM, batched, parallel): each shot gets a type and its search spec or
   structured data. Output is validated with pydantic; invalid batches are retried
   with the validation errors fed back to the model.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from pydantic import ValidationError

from .context import RunContext
from .llm import LLMError, complete_json
from .schemas import MAX_SHOT_SECONDS, MIN_SHOT_SECONDS, PlanChapter, Shot, ShotsFile, StoryEvent, Word, WordsFile


STAGE = "planner"
OUTPUT = "shots.json"
REVIEW = "shots.md"

_FUNCTION_WORDS = frozenset(
    "a al ante con de del desde el en entre hacia hasta la las lo los mi mis muy no o para "
    "por que se si sin su sus te tu tus un una unos unas y e ni ya más le les nos cuando "
    "donde como cada".split()
)
_SOFT_PUNCT = (",", ";", ":", ")", "»", "”", "—")


# --- 1. Chapters -----------------------------------------------------------------------

OUTLINE_SYSTEM = """
Eres editor de vídeos documentales de ritmo rápido para YouTube (b-roll real, cifras grandes, paneles de datos).
El nicho y el tema los marca el guion.
Recibes las frases numeradas del guion de un vídeo. Devuelve SOLO un objeto JSON:
{
  "context": "1-2 frases EN INGLÉS: tema, país/ciudad, época y tipo de metraje que encaja (se usará para buscar b-roll)",
  "chapters": [{"title": "TÍTULO EN MAYÚSCULAS", "sentence": 12}],
  "subject": "si el vídeo trata de una persona concreta: 'Nombre Apellido · deporte/actividad en inglés' (p. ej. 'Carlos Yulo · artistic gymnastics'); si no, \"\"",
  "peak": "si hay protagonista: búsqueda EN INGLÉS de su momento cumbre, el más espectacular (p. ej. 'Carlos Yulo Paris 2024 floor gold medal winning moment'); si no, \"\"",
  "events": [{"sentence": 5, "label": "búsqueda EN INGLÉS del evento concreto que se cuenta desde esa frase: persona + competición/hecho + año + lugar, p. ej. 'Carlos Yulo floor final 2019 World Championships Stuttgart'", "tag": "rótulo en pantalla en el idioma del guion, lugar y/o fecha tal como se dicen en esa parte, MAYÚSCULAS, máx. 30 caracteres, p. ej. 'STUTTGART · 2019'; null si el guion no dice lugar ni fecha"}]
}
Reglas de "events" (el hilo de la historia):
- Un evento nuevo cada vez que el guion pasa a contar un hecho concreto distinto (una
  competición, un año, un lugar, una etapa de la vida). Suelen ser 5-20 en un vídeo de 10 min.
- Si el guion habla de otra persona durante un tramo (un rival, un ídolo), ese tramo es un
  evento de esa persona ("Kohei Uchimura London 2012 all-around gold").
- Tramos sin hecho concreto (reflexiones, llamada a suscribirse) siguen con el evento anterior
  o con uno general del protagonista ("Carlos Yulo best moments highlights").
- "sentence" en orden creciente.
Reglas de los capítulos:
- Entre 3 y 7 capítulos, en el idioma del guion, en MAYÚSCULAS, 1-4 palabras, con gancho
  (p. ej. "LA LICENCIA", "LA MÁQUINA DE DINERO"). Nada de "Introducción" ni "Conclusión".
- "sentence" es el número de la frase donde empieza el capítulo. Deben ir en orden creciente
  y separados al menos 45 segundos. El gancho inicial (las primeras frases) no lleva capítulo:
  el primer capítulo empieza cuando arranca el desarrollo del tema.
""".strip()

RANKING_OUTLINE = """
ESTE VÍDEO ES UN RANKING / CUENTA ATRÁS (top X de ciudades, robots, empresas…), sin protagonista:
- "subject": "" y "peak": "".
- "events": uno por puesto, desde la frase que lo presenta. "label" = búsqueda EN INGLÉS del elemento
  de ese puesto y del metraje que lo enseña (p. ej. 'Shenzhen China skyline drone footage',
  'Unitree H1 humanoid robot walking demo'); "tag" = 'Nº 7 · SHENZHEN' (máx. 30 caracteres).
- La intro antes del primer puesto es un evento general del tema del ranking.
- Capítulos: agrupan varios puestos (p. ej. "DEL 10 AL 7", "EL PODIO"), con las mismas reglas.
""".strip()


BANNED_OUTLINE = """
ESTE VÍDEO REPASA COSAS PROHIBIDAS/ELIMINADAS de un deporte (elementos, técnicas, trajes, reglas…):
- "subject": "" salvo que todo el vídeo sea sobre una sola persona; "peak": "".
- "events": uno por elemento prohibido, desde la frase que lo presenta, y otro cuando se cuenta quién lo hizo
  famoso. "label" = búsqueda EN INGLÉS que encuentre ese elemento en vídeo (elemento + deporte + persona +
  año, p. ej. 'Korbut flip uneven bars Olga Korbut 1972'); "tag" = 'NOMBRE DEL ELEMENTO · AÑO' si se dice.
- Capítulos: agrupan elementos (por aparato, por época…), con las mismas reglas.
""".strip()

TECHNIQUE_OUTLINE = """
ESTE VÍDEO EXPLICA UNA TÉCNICA O UN MOVIMIENTO (cómo se hace, por qué es tan difícil):
- "subject": la persona que lo creó o lo hace mejor si el vídeo gira en torno a ella; si no, "".
- "events": uno por cada ejecución o fase que se cuenta; "label" = búsqueda EN INGLÉS que encuentre ese
  movimiento bien visible y con la cámara lo más quieta posible (p. ej. 'Yurchenko double pike vault
  Simone Biles slow motion side view'); "tag" = nombre del movimiento y año si se dice.
- Capítulos: las partes de la explicación (origen, cómo se hace, por qué es difícil, quién lo domina).
""".strip()

FINAL_OUTLINE = """
ESTE VÍDEO NARRA UNA FINAL O COMPETICIÓN CONCRETA, participante a participante:
- "subject": el protagonista de la final si lo hay; si no, "".
- "peak": búsqueda EN INGLÉS del momento decisivo de esa final.
- "events": uno por cada participante o ejercicio que se cuenta, SIEMPRE con la competición y el año
  (p. ej. 'Carlos Yulo floor final Paris 2024 Olympics'); "tag" = 'NOMBRE · NOTA' o el lugar y año.
- Capítulos: los momentos de la final (la previa, los primeros ejercicios, el giro, el desenlace).
""".strip()

RIVALRY_OUTLINE = """
ESTE VÍDEO ES UNA RIVALIDAD ENTRE DOS (personas, equipos o países):
- "subject": "" (son dos protagonistas); "peak": búsqueda EN INGLÉS de su duelo más famoso.
- "events": uno por cada duelo o etapa, con los DOS nombres, la competición y el año
  (p. ej. 'Simone Biles Rebeca Andrade vault final Paris 2024'); si un tramo habla solo de uno, solo ese.
- Capítulos: las etapas de la rivalidad (el origen, el primer duelo, el cambio, el último duelo).
""".strip()

RECORDS_OUTLINE = """
ESTE VÍDEO VA DE RÉCORDS (marcas imposibles, quién las tiene, cuánto duran):
- "subject": "" salvo que todo el vídeo sea el récord de una persona.
- "events": uno por récord, desde la frase que lo presenta: "label" = búsqueda EN INGLÉS de la prueba en la
  que se batió (persona + prueba + récord + año, p. ej. 'Javier Sotomayor high jump world record 2.45 1993');
  "tag" = 'RÉCORD · AÑO' o la marca si se dice.
""".strip()

LIST_OUTLINE = """
ESTE VÍDEO ES UNA LISTA DE CASOS SIN NUMERAR (fallos, momentos, anécdotas…), cada uno con su protagonista:
- "subject": "" (hay varios protagonistas); "peak": "".
- "events": uno por caso, desde la frase que lo presenta, y otro cuando dentro del caso cambia el momento
  concreto. "label" = búsqueda EN INGLÉS de ESE momento (persona + aparato/hecho + competición + año, p. ej.
  'Gabby Douglas balance beam fall London 2012'); "tag" = 'LUGAR · AÑO' tal como se dice.
- Capítulos: agrupan casos (por tono o por época), con las mismas reglas.
""".strip()

FORMAT_OUTLINES = {"lista": LIST_OUTLINE, "rivalidad": RIVALRY_OUTLINE, "records": RECORDS_OUTLINE, "ranking": RANKING_OUTLINE, "prohibidos": BANNED_OUTLINE, "tecnica": TECHNIQUE_OUTLINE,
                   "final": FINAL_OUTLINE}


def outline_system(ctx: RunContext) -> str:
    extra = FORMAT_OUTLINES.get(str(ctx.config.get("format") or ""))
    return OUTLINE_SYSTEM + ("\n\n" + extra if extra else "")


def _sentences(words: list[Word]) -> list[tuple[int, int]]:
    spans, start = [], 0
    for word in words:
        if word.sentenceEnd:
            spans.append((start, word.index))
            start = word.index + 1
    if start < len(words):
        spans.append((start, len(words) - 1))
    return spans


def _fmt_time(seconds: float) -> str:
    return f"{int(seconds // 60)}:{seconds % 60:04.1f}"


def parse_story(result: dict[str, Any], sentences: list[tuple[int, int]]) -> tuple[str, list[StoryEvent]]:
    """Subject and story events from the outline; malformed events are dropped, never fatal."""

    subject = str(result.get("subject") or "").strip()[:120]
    if subject.casefold() in ("none", "null", "n/a", "-"):
        subject = ""
    events: list[StoryEvent] = []
    raw = result.get("events") if isinstance(result.get("events"), list) else []
    for item in sorted((e for e in raw if isinstance(e, dict)), key=lambda e: _as_int(e.get("sentence"))):
        sentence, label = _as_int(item.get("sentence")), " ".join(str(item.get("label") or "").split())[:160]
        if not 0 <= sentence < len(sentences) or len(label) < 3:
            continue
        start = sentences[sentence][0]
        tag = " ".join(str(item.get("tag") or "").split()).upper()[:40] or None
        if tag in ("NULL", "NONE"):
            tag = None
        if events and events[-1].startWord == start:
            events[-1] = StoryEvent(label=label, startWord=start, tag=tag)
        elif not events or events[-1].label != label:
            events.append(StoryEvent(label=label, startWord=start, tag=tag))
    if events and events[0].startWord != 0 and subject:
        events.insert(0, StoryEvent(label=subject.split("·")[0].strip() + " highlights", startWord=0))
    return subject, events


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def subject_person(subject: str) -> str:
    """'Carlos Yulo · artistic gymnastics' → 'Carlos Yulo'."""

    return subject.split("·")[0].strip()


def event_at(events: list[StoryEvent], word: int) -> str | None:
    current = [e for e in events if e.startWord <= word]
    return current[-1].label if current else None


def plan_chapters(ctx: RunContext, words_file: WordsFile) -> tuple[list[PlanChapter], str, dict[str, Any]]:
    words = words_file.words
    sentences = _sentences(words)
    if words_file.chapters:
        chapters = [
            PlanChapter(title=c.title.upper()[:48], startWord=c.wordIndex, fromScript=True) for c in words_file.chapters
        ]
        context = ""
        result = {}
    else:
        listing = "\n".join(
            f"[{n}] ({_fmt_time(words[a].start)}) " + " ".join(w.text for w in words[a : b + 1])
            for n, (a, b) in enumerate(sentences)
        )
        result: dict[str, Any] = {}
        error: Exception | None = None
        for _ in range(int(ctx.section("planner").get("max_attempts", 3))):
            feedback = f"\n\nTu respuesta anterior no era válida: {error}. Corrígela." if error else ""
            result = complete_json(
                ctx,
                stage=STAGE,
                section="planner",
                system=outline_system(ctx),
                user=f"TÍTULO: {words_file.title}\n\nFRASES:\n{listing}{feedback}",
                max_tokens=2000,
            )
            try:
                chapters = _validate_outline(result, sentences, words)
                break
            except ValueError as exc:
                error = exc
        else:
            raise RuntimeError(f"El planner no produjo capítulos válidos: {error}")
        context = str(result.get("context") or "").strip()[:400]
    if not chapters or chapters[0].startWord != 0:
        chapters.insert(0, PlanChapter(title=words_file.title.upper()[:48] or "INTRO", startWord=0, fromScript=False, showTitle=False))
    return chapters, context, result


def _validate_outline(result: dict[str, Any], sentences: list[tuple[int, int]], words: list[Word],
                      min_gap: float = 45.0, hook: float = 20.0) -> list[PlanChapter]:
    """Chapters in order, at least `min_gap` s apart and after the hook. The model often gets the
    spacing slightly wrong: such chapters are dropped instead of rejecting the whole outline."""

    raw = result.get("chapters")
    if not isinstance(raw, list) or not raw:
        raise ValueError("se esperaba una lista de capítulos")
    parsed: list[tuple[int, str]] = []
    for item in raw:
        try:
            sentence = int(item["sentence"])
            title = str(item["title"]).strip().upper()
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"capítulo mal formado: {item!r}") from None
        if 0 <= sentence < len(sentences) and title:
            parsed.append((sentence, title))
    chapters: list[PlanChapter] = []
    previous_start = hook - min_gap          # the first chapter may not start inside the hook
    for sentence, title in sorted(set(parsed)):
        start_word = sentences[sentence][0]
        if words[start_word].start - previous_start < min_gap:
            continue
        previous_start = words[start_word].start
        chapters.append(PlanChapter(title=title[:48], startWord=start_word, fromScript=False))
    if len(chapters) < 2:
        raise ValueError(f"quedan {len(chapters)} capítulos válidos: hacen falta al menos 2, en orden, "
                         f"separados {min_gap:.0f} s y después del segundo {hook:.0f}")
    return chapters[:7]


# --- 2. Cutting ------------------------------------------------------------------------


def _boundary_cost(words: list[Word], b: int) -> float:
    """Cost of cutting right before word b (lower is a more natural cut)."""

    prev, nxt = words[b - 1], words[b]
    gap = max(0.0, nxt.start - prev.end)
    if prev.sentenceEnd:
        cost = 0.0
    elif prev.text.rstrip("»”\"')").endswith(_SOFT_PUNCT):
        cost = 1.0
    else:
        cost = 3.0
        if prev.text.casefold().strip(".,;:¿?¡!\"'«»") in _FUNCTION_WORDS:
            cost += 4.0
    return cost - min(1.0, gap * 2)


def _boundary_times(words: list[Word], duration: float) -> list[list[float]]:
    """Where shot b may start: at word b, or — after a long pause — inside the silence, so a long
    pause can be shared by two shots instead of forcing one over the maximum length."""

    n = len(words)
    times: list[list[float]] = [[0.0]]
    for b in range(1, n):
        start, previous_end = words[b].start, words[b - 1].end
        options = [start]
        if start - previous_end > 0.6:
            options += [(start + previous_end) / 2, previous_end + 0.15]
        times.append(options)
    times.append([duration])
    return times


def cut_shots(
    words: list[Word],
    duration: float,
    *,
    target: float,
    forced_starts: set[int],
    min_seconds: float = MIN_SHOT_SECONDS,
    max_seconds: float = MAX_SHOT_SECONDS,
    with_times: bool = False,
):
    """Return shots as (firstWord, lastWord), contiguous and covering all words — and, with
    `with_times`, the start second of each shot (a cut may fall inside a long pause)."""

    n = len(words)
    times = _boundary_times(words, duration)
    forced = sorted(b for b in forced_starts if 0 < b < n)
    inf = math.inf
    best = [[inf] * len(times[b]) for b in range(n + 1)]
    back: list[list[tuple[int, int]]] = [[(-1, -1)] * len(times[b]) for b in range(n + 1)]
    best[0][0] = 0.0
    for b in range(1, n + 1):
        cut_cost = _boundary_cost(words, b) if b < n else 0.0
        for j, tb in enumerate(times[b]):
            for a in range(b - 1, -1, -1):
                if tb - max(times[a]) > max_seconds * 3:
                    break
                if any(a < f < b for f in forced):
                    continue
                for i, ta in enumerate(times[a]):
                    if best[a][i] == inf:
                        continue
                    d = tb - ta
                    if d <= 0:
                        continue
                    penalty = ((d - target) / 0.8) ** 2
                    if d < min_seconds:
                        penalty += 1000 * (min_seconds - d + 0.1)
                    elif d > max_seconds:
                        penalty += 1000 * (d - max_seconds + 0.1)
                    total = best[a][i] + penalty + cut_cost
                    if total < best[b][j]:
                        best[b][j], back[b][j] = total, (a, i)
    if best[n][0] == inf:
        raise RuntimeError("No se pudo dividir el audio en planos.")
    bounds: list[tuple[int, float]] = []
    b, j = n, 0
    while b > 0:
        bounds.append((b, times[b][j]))
        b, j = back[b][j]
    bounds.reverse()
    shots, starts, start_word, start_time = [], [], 0, 0.0
    for end_word, end_time in bounds:
        shots.append((start_word, end_word - 1))
        starts.append(start_time)
        start_word, start_time = end_word, end_time
    return (shots, starts) if with_times else shots


# --- 3. Labelling ----------------------------------------------------------------------

LABEL_SYSTEM = """
Eres el editor de un canal de YouTube de documentales de ritmo rápido (b-roll real de
terceros, cifras grandes, paneles de datos). El nicho y el tema los marcan el TÍTULO y el
CONTEXTO VISUAL (economía, deporte, historia, tecnología…); los ejemplos de abajo son solo ejemplos.
Recibes una lista de planos YA CORTADOS (1,5-4 s cada uno) con el texto que se narra
durante cada plano. Para CADA plano decides qué se ve. Devuelve SOLO JSON:

{"shots": [
  {"id": "s001", "type": "broll", "broll": {...}},
  {"id": "s002", "type": "stat", "stat": {"value": "2,7%", "label": "ventaja de la banca · ruleta europea", "sign": "positive"}, "broll": {...}},
  {"id": "s003", "type": "datacard", "panelId": "p1", "panel": {"title": "Ruleta europea", "rows": [{"label": "Apuesta", "value": "100 €", "sign": "neutral"}, {"label": "Se queda el casino", "value": "2,70 €", "sign": "positive"}], "note": null}},
  {"id": "s004", "type": "split", "panel": {...}, "broll": {...}},
  {"id": "s005", "type": "chapter", "broll": {...}}
]}

Opcional en cualquier plano: "rotulo": {"tipo": "nombre" | "nota", "texto": "..."} — etiqueta pequeña
abajo a la izquierda. "nombre": la PRIMERA vez que el texto nombra a una persona relevante distinta
del protagonista (p. ej. "Kohei Uchimura"). "nota": una puntuación o marca dicha en ese plano
("15.3", "14.549"). Solo con lo que se dice en ese plano; como mucho 1 de cada 4 planos.

Objeto "broll" (metraje a buscar en YouTube/bancos de imágenes):
{"visualIntent": "qué se ve, concreto y observable, en inglés",
 "queriesEn": ["3-5 búsquedas en inglés de 2-6 palabras, como las escribiría un editor buscando b-roll: 'las vegas strip aerial night', 'roulette wheel spinning close up'"],
 "queriesEs": ["1-2 búsquedas en el idioma del guion, p. ej. 'Gran Casino de Madrid Torrelodones'"],
 "entities": ["personas, lugares, empresas o marcas concretas que aparecen; [] si no hay"],
 "mustContain": ["1-3 elementos que DEBEN verse"],
 "avoid": ["presentador hablando a cámara", "texto en pantalla", ...],
 "preferredShot": "wide | medium | close-up | aerial | detail | action | archive"}

Tipos:
- "broll" (la mayoría, ~70-80 %): metraje que ilustra lo que se dice. Si el texto
  es abstracto, elige una imagen documental concreta y reconocible del tema (personas, lugares,
  objetos, momentos reconocibles). Varía el encuadre entre planos seguidos; no repitas queries.

El b-roll se queda SIEMPRE en el mundo del vídeo (el TÍTULO y el CONTEXTO VISUAL):
- Comparaciones y metáforas NO se ilustran al pie de la letra: "no es como abrir un
  restaurante" o "es una máquina de hacer dinero" muestran el tema del vídeo (en un vídeo de
  casinos, un casino lleno; en uno de deporte, el atleta compitiendo), no una cocina ni una máquina.
- Conceptos abstractos o burocráticos (requisitos, regulación, ingresos, trámites, impuestos)
  → una imagen concreta DEL TEMA (casinos: sala de juego, crupier, fachada; deporte: el atleta
  entrenando o compitiendo, el estadio, el podio; historia: lugares y documentos de época),
  NUNCA pantallas de ordenador, hojas de cálculo,
  programas (Excel, Word), formularios, casillas de verificación ni tutoriales.
- Si el plano lleva "evento", el b-roll es de ESE evento (esa competición, ese año, ese lugar):
  un podio es EL podio de ese evento, no cualquiera. Incluye persona + competición + año en las
  búsquedas. Solo si el texto del plano habla claramente de otra cosa, busca eso otro.
- PROTAGONISTA PRIMERO: si hay PROTAGONISTA, por defecto cada plano muestra AL PROTAGONISTA
  (compitiendo, en el podio, entrenando, en entrevistas, en fotos), aunque el texto cuente un
  recuerdo, una reflexión o una cita suya. Solo si el texto NOMBRA a otra persona o un lugar
  concreto, muestra a esa persona o ese lugar (con su nombre en "entities"). NUNCA "un niño
  cualquiera", "un abuelo", "un gimnasta genérico" ni imágenes de stock de desconocidos.
- Si el vídeo trata de una persona concreta (un deportista, un empresario…), pide metraje de
  ESA persona siempre que el texto hable de ella, con su nombre en "entities" y en las búsquedas
  (nombre + prueba/acción + año/lugar, p. ej. "Simone Biles vault final 2023 Antwerp"): competiciones, entrenamientos, podios.
- Los planos con "gancho": true son los primeros segundos: deciden si el espectador se queda.
  Si hay PROTAGONISTA, muestran su momento cumbre (el "evento" del plano), no lo que narra el texto.
  Pide el metraje más espectacular e inconfundible del tema (el protagonista en su mejor
  momento, planos aéreos, multitudes, momentos cumbre), nunca algo genérico.
- "stat": UNA cifra que el texto dice en ese plano, mostrada en grande sobre b-roll
  (incluye "broll" como fondo). "value" corto tal como lo diría el guion ("2,7%", "60.000 m²",
  "14 M"); "label" breve en el idioma del guion.
- "datacard": panel oscuro con 1-6 filas cuando el texto compara o calcula varias cifras.
  Si varios planos seguidos explican el mismo cálculo, usa el MISMO "panelId" en todos y
  haz que cada plano repita las filas anteriores y añada la nueva (el panel se va construyendo).
- "split": b-roll a la izquierda + panel de datos a la derecha; para cifras ligadas a
  un lugar/objeto/empresa concreto que conviene ver a la vez (p. ej. los datos de un edificio
  o de una empresa concreta). Lleva "broll" y "panel"; puede acumular filas con "panelId".
- "chapter": SOLO en los planos marcados con "chapterTitle" en la entrada. Lleva "broll"
  (fondo del título). No lleves "chapterTitle" en la salida: ya lo tenemos.

Ritmo: "stat" es para la cifra más impactante de un bloque, no para todas. Cuando se
encadenan 3 o más cifras sobre lo mismo (inversión pequeño/mediano/grande, datos de un
mismo casino, un cálculo paso a paso), usa "datacard" o "split" con el mismo "panelId"
que va sumando filas. NUNCA más de 2 planos "stat" seguidos.

Reglas duras:
- Las cifras y datos SALEN DEL TEXTO del plano (o de los planos inmediatamente anteriores
  del mismo cálculo). NUNCA inventes cifras, redondeos ni rangos que el guion no diga:
  si el guion dice "decenas de millones" o "cientos de millones" SIN número, no hay cifra
  que mostrar → usa "broll". Todo "value" debe contener dígitos que se digan en el texto.
- "sign": "positive" = ganancia/crecimiento/a favor; "negative" = pérdida/coste/caída; si no, "neutral".
- Devuelve exactamente un objeto por cada id recibido, en el mismo orden.
""".strip()


def _summary(shot: dict[str, Any]) -> str:
    if shot["type"] == "stat":
        return f"stat {shot['stat']['value']}"
    if shot.get("panel"):
        return f"{shot['type']} {shot.get('panelId') or ''} [{shot['panel']['title']}]".strip()
    return shot["type"]


def _label_batch(
    ctx: RunContext,
    batch: list[dict[str, Any]],
    header: str,
    attempts: int,
    nearby_text: dict[str, str],
) -> list[dict[str, Any]]:
    """Label structural shots; returns full shot dicts that validate against `Shot`."""

    good: dict[str, dict[str, Any]] = {}
    demoted: dict[str, dict[str, Any]] = {}   # last candidate of shots that failed only on their figures
    errors: list[str] = []
    for _ in range(attempts):
        pending = [s for s in batch if s["id"] not in good]
        public = [
            {"id": s["id"], "seconds": round(s["end"] - s["start"], 1), "text": s["text"],
             **({"chapterTitle": s["chapterTitle"]} if s.get("chapterTitle") else {}),
             **({"gancho": True} if s.get("hook") else {}),
             **({"evento": s["event"]} if s.get("event") else {}),
             **({"yaDecidido": _summary(good[s["id"]])} if s["id"] in good else {})}
            for s in batch
        ]
        feedback = ""
        if errors:
            feedback = (
                "\n\nRESPONDE SOLO con los planos " + ", ".join(p["id"] for p in pending)
                + " (los que tienen 'yaDecidido' ya están bien). Errores de tu respuesta anterior:\n- "
                + "\n- ".join(errors[:20])
            )
        try:
            result = complete_json(
                ctx,
                stage=STAGE,
                section="planner",
                system=LABEL_SYSTEM,
                user=f"{header}\n\nPLANOS:\n{json.dumps(public, ensure_ascii=False, indent=1)}{feedback}",
                max_tokens=16000,
            )
        except LLMError as error:
            errors = [str(error)]
            continue
        labelled = result.get("shots")
        errors = []
        if not isinstance(labelled, list):
            errors.append("falta la lista 'shots'")
            continue
        by_id = {str(item.get("id")): item for item in labelled if isinstance(item, dict)}
        for shot in pending:
            label = by_id.get(shot["id"])
            if label is None:
                errors.append(f"{shot['id']}: falta en la respuesta")
                continue
            candidate = _merge(shot, label)
            try:
                Shot.model_validate(candidate)
            except ValidationError as error:
                details = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors()[:4])
                errors.append(f"{shot['id']}: {details}")
                continue
            number_errors = check_numbers(candidate, nearby_text[shot["id"]])
            if number_errors:
                errors.extend(number_errors)
                demoted[shot["id"]] = candidate
                continue
            good[shot["id"]] = candidate
        run = 0
        for shot in batch:
            candidate = good.get(shot["id"])
            run = run + 1 if candidate and candidate["type"] == "stat" else 0
            if run == 3:
                errors.append(f"{shot['id']}: tercer plano stat seguido; agrupa las cifras en un datacard/split con panelId")
                demoted[shot["id"]] = good.pop(shot["id"])
                run = 0
        if len(good) == len(batch):
            return [good[s["id"]] for s in batch]
    # Last resort: a shot whose only problem is its figure becomes plain b-roll with its own footage.
    for shot in batch:
        candidate = demoted.get(shot["id"])
        if shot["id"] in good or not candidate or not isinstance(candidate.get("broll"), dict):
            continue
        plain = {k: v for k, v in candidate.items() if k not in ("stat", "panel", "panelId")} | {"type": "broll"}
        if shot.get("chapterTitle"):
            plain["type"] = "chapter"
        try:
            Shot.model_validate(plain)
        except ValidationError:
            continue
        print(f"   {shot['id']}: la cifra no se dice en el texto → se queda como b-roll")
        good[shot["id"]] = plain
    if len(good) == len(batch):
        return [good[s["id"]] for s in batch]
    raise RuntimeError("El planner no produjo planos válidos tras varios intentos: " + " | ".join(errors[:8]))


_NUMBER = re.compile(r"\d[\d.,]*\d|\d")


_UNITS = ["cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez", "once", "doce",
          "trece", "catorce", "quince", "dieciseis", "diecisiete", "dieciocho", "diecinueve", "veinte", "veintiuno",
          "veintidos", "veintitres", "veinticuatro", "veinticinco", "veintiseis", "veintisiete", "veintiocho",
          "veintinueve"]
_TENS = {"treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60, "setenta": 70, "ochenta": 80, "noventa": 90}
_ORDINALS = {"primer": 1, "primero": 1, "primera": 1, "segundo": 2, "tercer": 3, "tercero": 3, "cuarto": 4,
             "quinto": 5, "sexto": 6, "septimo": 7, "octavo": 8, "noveno": 9, "decimo": 10, "undecimo": 11,
             "duodecimo": 12, "vigesimo": 20}
_WORD_VALUES: dict[str, int] = {w: i for i, w in enumerate(_UNITS)} | {"un": 1, "una": 1, "veintiun": 21, "cien": 100,
                                                                     "ciento": 100, "mil": 1000} | _TENS | _ORDINALS


def _spelled_numbers(text: str) -> set[float]:
    """Numbers written as words ("dieciséis", "treinta y dos", "quinto", "duodécimo")."""

    plain = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    tokens = re.findall(r"[a-z]+", plain)
    values: set[float] = set()
    for i, token in enumerate(tokens):
        stem = token[:-1] if token.endswith("s") and token[:-1] in _WORD_VALUES else token
        stem = stem[:-1] + "o" if stem.endswith("a") and stem[:-1] + "o" in _ORDINALS else stem
        if stem not in _WORD_VALUES:
            continue
        value = _WORD_VALUES[stem]
        values.add(float(value))
        if token in _TENS and i + 2 < len(tokens) and tokens[i + 1] == "y" and tokens[i + 2] in _WORD_VALUES:
            values.add(float(value + _WORD_VALUES[tokens[i + 2]]))
    return values


def _numbers(text: str) -> set[float]:
    """Spanish number parsing: '.' + 3 digits is a thousands separator, ',' is decimal."""

    values: set[float] = set()
    for raw in _NUMBER.findall(text):
        cleaned = re.sub(r"\.(?=\d{3}(\D|$))", "", raw).replace(",", ".")
        try:
            values.add(round(float(cleaned), 4))
        except ValueError:
            continue
    return values


def check_numbers(shot: dict[str, Any], nearby_text: str) -> list[str]:
    """Every number shown on screen must be said in the narration around the shot."""

    said = _numbers(nearby_text) | _spelled_numbers(nearby_text)
    errors: list[str] = []
    shown: list[str] = []
    if shot.get("type") == "stat" and isinstance(shot.get("stat"), dict):
        value = str(shot["stat"].get("value", ""))
        if not re.search(r"\d", value):
            errors.append(f"{shot['id']}: stat.value {value!r} no contiene ninguna cifra; usa broll")
        shown.append(value)
    if isinstance(shot.get("panel"), dict):
        shown += [str(row.get("value", "")) for row in shot["panel"].get("rows", []) if isinstance(row, dict)]
    for value in shown:
        invented = sorted(n for n in _numbers(value) if n not in said)
        if invented:
            errors.append(f"{shot['id']}: la cifra {value!r} no se dice en este plano ni en los anteriores ({', '.join(map(str, invented))}); muéstrala en el plano donde se dice, o usa broll")
    return errors


# Too-long lists are trimmed rather than retried: the minimums are what matter.
_BROLL_LIMITS = {"queriesEn": 5, "queriesEs": 2, "queries": 5, "queriesLocal": 2, "entities": 5, "mustContain": 4, "avoid": 5}


def _trim_broll(broll: dict[str, Any]) -> dict[str, Any]:
    trimmed = dict(broll)
    for key, limit in _BROLL_LIMITS.items():
        if isinstance(trimmed.get(key), list):
            seen: set[str] = set()
            items = []
            for item in trimmed[key]:
                text = " ".join(str(item).split())
                if text and text.casefold() not in seen:
                    seen.add(text.casefold())
                    items.append(text)
            trimmed[key] = items[:limit]
    return trimmed


def _with_event(broll: dict[str, Any], event: str | None) -> dict[str, Any]:
    """Every shot of a story event searches for that event first, so consecutive shots draw on
    the same competition/footage instead of any podium or any gym."""

    if not event:
        return broll
    key = "queriesEn" if "queriesEn" in broll else "queries"
    queries = [q for q in broll.get(key, []) if isinstance(q, str)]
    if event.casefold() not in (q.casefold() for q in queries):
        queries = [event, *queries][:5]
    return {**broll, key: queries, "event": event}


_LABEL_KINDS = {"nombre": "name", "name": "name", "nota": "score", "score": "score", "lugar": "place",
                "place": "place", "fecha": "date", "date": "date"}


def _plain(text: str) -> str:
    return unicodedata.normalize("NFKD", text.casefold()).encode("ascii", "ignore").decode()


def _on_screen_label(raw: Any, text: str) -> dict[str, str] | None:
    """A lower-left tag only if everything on it is said in this shot (names and numbers alike)."""

    if not isinstance(raw, dict):
        return None
    kind = _LABEL_KINDS.get(str(raw.get("tipo") or raw.get("kind") or "").casefold())
    value = " ".join(str(raw.get("texto") or raw.get("text") or "").split())[:40]
    if not kind or not value:
        return None
    said = _plain(text)
    words = [w for w in re.findall(r"[a-z]+", _plain(value)) if len(w) >= 3]
    if any(w not in said for w in words) or not (_numbers(value) <= (_numbers(text) | _spelled_numbers(text))):
        return None
    return {"kind": kind, "text": value}


def _with_subject(broll: dict[str, Any], person: str | None) -> dict[str, Any]:
    """Protagonist first: a shot that names nobody else shows the protagonist."""

    if not person or broll.get("entities"):
        return broll
    return {**broll, "entities": [person]}


def _merge(structural: dict[str, Any], label: dict[str, Any]) -> dict[str, Any]:
    shot = {k: structural[k] for k in ("id", "startWord", "endWord", "start", "end", "text", "chapter")}
    kind = str(label.get("type") or "broll")
    if structural.get("chapterTitle"):
        kind = "chapter"
        shot["chapterTitle"] = structural["chapterTitle"]
    elif kind == "chapter":
        kind = "broll"
    shot["type"] = kind
    for key in ("broll", "panel", "stat", "panelId"):
        if label.get(key) not in (None, "", {}):
            shot[key] = label[key]
    if tag := _on_screen_label(label.get("rotulo"), structural["text"]):
        shot["label"] = tag
    if isinstance(shot.get("broll"), dict):
        shot["broll"] = _with_subject(_with_event(_trim_broll(shot["broll"]), structural.get("event")),
                                      structural.get("subject"))
    if kind == "broll":
        shot.pop("panel", None), shot.pop("stat", None), shot.pop("panelId", None)
    if kind == "chapter":
        shot.pop("panel", None), shot.pop("stat", None), shot.pop("panelId", None)
    if kind == "datacard":
        shot.pop("broll", None), shot.pop("stat", None)
    if kind == "stat":
        shot.pop("panel", None), shot.pop("panelId", None)
    if kind == "split":
        shot.pop("stat", None)
    return shot


def normalize_groups(shots: list[dict[str, Any]]) -> None:
    """Give consecutive shots that show the same panel (or the same stat) one global panelId.

    Batches are labelled independently, so the LLM's panelIds ("p1") are only meaningful
    between neighbours. A group renders as one continuous panel while the b-roll keeps
    cutting underneath; every shot in a group takes the group's type.
    """

    group = 0
    previous: dict[str, Any] | None = None
    for shot in shots:
        kind = shot["type"]
        same = False
        if previous is not None:
            if kind in ("datacard", "split") and previous["type"] in ("datacard", "split"):
                raw, prev_raw = shot.get("panelId"), previous.get("_rawPanelId")
                same = (raw is not None and raw == prev_raw) or shot["panel"]["title"] == previous["panel"]["title"]
            elif kind == "stat" and previous["type"] == "stat":
                same = shot["stat"]["value"] == previous["stat"]["value"]
        raw_id = shot.get("panelId")
        if same:
            shot["panelId"] = previous["panelId"]
            shot["type"] = previous["type"]
            if shot["type"] == "split" and not shot.get("broll"):
                shot["broll"] = previous["broll"]
            if shot["type"] == "datacard":
                shot.pop("broll", None)
        elif kind in ("datacard", "split", "stat"):
            group += 1
            shot["panelId"] = f"g{group:02d}"
        else:
            shot.pop("panelId", None)
        shot["_rawPanelId"] = raw_id
        previous = shot if shot["type"] in ("datacard", "split", "stat") else None
    for shot in shots:
        shot.pop("_rawPanelId", None)
    # Singleton stats need no group id.
    counts: dict[str, int] = {}
    for shot in shots:
        if shot.get("panelId"):
            counts[shot["panelId"]] = counts.get(shot["panelId"], 0) + 1
    for shot in shots:
        if shot["type"] == "stat" and counts.get(shot.get("panelId", ""), 0) == 1:
            shot.pop("panelId", None)


# --- Stage entry points ----------------------------------------------------------------


def inputs(ctx: RunContext) -> list:
    return [ctx.work_dir / "words.json"]


def run(ctx: RunContext) -> None:
    cfg = ctx.section("planner")
    words_file = WordsFile.model_validate(ctx.read_json("words.json"))
    words = words_file.words

    chapters, context, outline = plan_chapters(ctx, words_file)
    subject, events = parse_story(outline, _sentences(words))
    peak = " ".join(str(outline.get("peak") or "").split())[:160] if subject else ""
    hook_seconds = float(cfg.get("hook_seconds", 30))
    print(f"   {len(chapters)} capítulos: " + " | ".join(c.title for c in chapters if c.showTitle))
    if subject or events:
        print(f"   Protagonista: {subject or '—'} · {len(events)} tramos de la historia")
    cuts, cut_starts = cut_shots(
        words,
        words_file.durationSeconds,
        target=float(cfg.get("target_shot_seconds", 2.6)),
        forced_starts={c.startWord for c in chapters},
        with_times=True,
    )
    chapter_starts = [c.startWord for c in chapters]
    structural: list[dict[str, Any]] = []
    for number, (first, last) in enumerate(cuts, start=1):
        start = cut_starts[number - 1]
        end = cut_starts[number] if number < len(cuts) else words_file.durationSeconds
        chapter = max(i for i, s in enumerate(chapter_starts) if s <= first)
        item = {
            "id": f"s{number:03d}",
            "startWord": first,
            "endWord": last,
            "start": round(start, 3),
            "end": round(end, 3),
            "text": " ".join(w.text for w in words[first : last + 1]),
            "chapter": chapter,
        }
        if first == chapters[chapter].startWord and chapters[chapter].showTitle:
            item["chapterTitle"] = chapters[chapter].title
        if start < hook_seconds:  # first seconds: ask for the most striking footage
            item["hook"] = True
        # The hook of a video about someone shows their peak moment, whatever the narration says.
        if event := (peak if peak and start < hook_seconds else event_at(events, first)):
            item["event"] = event
        if subject:
            item["subject"] = subject_person(subject)
        structural.append(item)
    print(f"   {len(structural)} planos cortados ({len(structural) / (words_file.durationSeconds / 60):.1f} cortes/min)")

    batch_size = int(cfg.get("batch_size", 24))
    batches = [structural[i : i + batch_size] for i in range(0, len(structural), batch_size)]
    header = (
        f"TÍTULO DEL VÍDEO: {words_file.title}\n"
        f"CONTEXTO VISUAL: {context or '(deducir del texto)'}\n"
        + (f"PROTAGONISTA: {subject}\n" if subject else "")
        + "CAPÍTULOS: " + " | ".join(c.title for c in chapters if c.showTitle)
    )

    def label(batch: list[dict[str, Any]]) -> list[dict[str, Any]]:
        first, last = structural.index(batch[0]), structural.index(batch[-1])
        before = " ".join(s["text"] for s in structural[max(0, first - 3) : first])
        after = " ".join(s["text"] for s in structural[last + 1 : last + 4])
        batch_header = f"{header}\nTEXTO ANTERIOR: {before or '(inicio)'}\nTEXTO POSTERIOR: {after or '(final)'}"
        return _label_batch(ctx, batch, batch_header, int(cfg.get("max_attempts", 3)), nearby)

    # Narration a number may legitimately come from: this shot, 6 before (cumulative panels), 1 after.
    nearby = {
        s["id"]: " ".join(x["text"] for x in structural[max(0, i - 6) : i + 2]) for i, s in enumerate(structural)
    }

    with ThreadPoolExecutor(max_workers=int(cfg.get("parallel", 4))) as pool:
        shots = [shot for batch_result in pool.map(label, batches) for shot in batch_result]
    normalize_groups(shots)

    shots_file = ShotsFile(
        slug=ctx.slug,
        title=words_file.title,
        durationSeconds=words_file.durationSeconds,
        context=context,
        subject=subject,
        events=events,
        chapters=chapters,
        shots=[Shot.model_validate(s) for s in shots],
    )
    ctx.write_json(OUTPUT, shots_file.model_dump(exclude_none=True))
    (ctx.work_dir / REVIEW).write_text(render_review(shots_file), encoding="utf-8")
    counts: dict[str, int] = {}
    for shot in shots_file.shots:
        counts[shot.type] = counts.get(shot.type, 0) + 1
    print("   Tipos: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1])))
    print(f"   Revisión legible: {(ctx.work_dir / REVIEW).relative_to(ctx.root)}")


def render_review(shots_file: ShotsFile) -> str:
    lines = [f"# Planos — {shots_file.title}", "", f"Contexto: {shots_file.context or '—'}", ""]
    current = -1
    for shot in shots_file.shots:
        if shot.chapter != current:
            current = shot.chapter
            chapter = shots_file.chapters[current]
            lines += ["", f"## {chapter.title}" + ("" if chapter.showTitle else " (intro, sin rótulo)"), ""]
            lines += ["| id | tiempo | tipo | texto | qué se ve |", "|---|---|---|---|---|"]
        if shot.type == "stat" and shot.stat:
            what = f"**{shot.stat.value}** {shot.stat.label}"
        elif shot.panel:
            what = f"[{shot.panel.title}] " + "; ".join(f"{r.label}: {r.value}" for r in shot.panel.rows)
        elif shot.type == "chapter":
            what = f"**{shot.chapterTitle}**"
        else:
            what = ""
        if shot.broll:
            what += (" · " if what else "") + f"{shot.broll.visualIntent} `{shot.broll.queries[0]}`"
        lines.append(
            f"| {shot.id} | {_fmt_time(shot.start)}–{_fmt_time(shot.end)} | {shot.type} | {shot.text} | {what} |"
        )
    return "\n".join(lines) + "\n"


def validate(ctx: RunContext) -> bool:
    ShotsFile.model_validate(ctx.read_json(OUTPUT))
    return True
