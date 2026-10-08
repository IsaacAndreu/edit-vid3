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
MAX_SHOT_SECONDS_DEFAULT = 4.0       # ordinary shots; only `slow` passages go up to MAX_SHOT_SECONDS


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

def outline_system(ctx: RunContext) -> str:
    extra = str(ctx.format.get("guion") or "").strip()                   # formatos/<format>.yaml
    series = str(ctx.section("planner").get("outline") or "").strip()   # the channel series' own notes
    return OUTLINE_SYSTEM + "".join("\n\n" + part for part in (extra, series) if part)


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


PACING_SYSTEM = """
Eres montador de documentales. Recibes las frases numeradas del guion. Marca el RITMO de montaje:
- "slow": frases emotivas o reflexivas donde la imagen debe respirar (un llanto, una pérdida, una
  confesión, el silencio antes de un golpe, una frase final que deja huella). Máximo 1 de cada 8 frases.
- "fast": frases de acción o enumeración rápida (una rutina, una caída, una carrera, una lista de logros).
  Máximo 1 de cada 5 frases.
El resto queda normal. Devuelve SOLO JSON: {"slow": [números], "fast": [números]}
""".strip()


def pacing(ctx: RunContext, words: list[Word]) -> dict[int, str]:
    """Sentence number → "slow" | "fast" (pacing.enabled); {} when off or the call fails."""

    cfg = ctx.section("pacing")
    if not cfg.get("enabled", True):
        return {}
    sentences = _sentences(words)
    listing = "\n".join(f"[{n}] " + " ".join(w.text for w in words[a : b + 1]) for n, (a, b) in enumerate(sentences))
    try:
        result = complete_json(ctx, stage=STAGE, section="planner", system=PACING_SYSTEM, user=f"FRASES:\n{listing}",
                               max_tokens=800)
    except Exception as error:  # pacing is a nicety: never cost the plan
        print(f"   Ritmo: sin marcar ({str(error)[:100]})")
        return {}
    marks: dict[int, str] = {}
    for kind in ("fast", "slow"):                       # slow wins where both are claimed
        for n in result.get(kind) or []:
            if isinstance(n, int) and 0 <= n < len(sentences):
                marks[n] = kind
    slow = sorted(n for n, k in marks.items() if k == "slow")[: max(1, len(sentences) // 8)]
    fast = sorted(n for n, k in marks.items() if k == "fast")[: max(1, len(sentences) // 5)]
    return {**{n: "fast" for n in fast}, **{n: "slow" for n in slow}}


def pace_targets(ctx: RunContext, words: list[Word], marks: dict[int, str], base: float) -> tuple[list[float], list[float], list[str | None]]:
    """Per word: the shot length to aim at, the longest allowed and the pace label."""

    cfg = ctx.section("pacing")
    seconds = {"slow": float(cfg.get("slow_seconds", 4.3)), "fast": float(cfg.get("fast_seconds", 1.9)), None: base}
    # a calm channel (base ≥ 4 s) may hold ordinary shots up to the 5 s third-party limit too
    longest = {"slow": MAX_SHOT_SECONDS, "fast": 3.0, None: min(MAX_SHOT_SECONDS, max(MAX_SHOT_SECONDS_DEFAULT, base + 0.6))}
    labels: list[str | None] = [None] * len(words)
    for n, (a, b) in enumerate(_sentences(words)):
        for i in range(a, b + 1):
            labels[i] = marks.get(n)
    targets, maxes = [seconds[k] for k in labels], [longest[k] for k in labels]
    # The opening cuts fast (the channels that hold viewers cut every ~1.2 s in their first half minute): the first
    # `pacing.hook_seconds` of narration aim at `hook_shot_seconds` per shot, emotional sentences included.
    hook = float(cfg.get("hook_seconds", 30) or 0)
    quick = float(cfg.get("hook_shot_seconds", 1.6))
    for i, word in enumerate(words):
        if word.start < hook and quick < targets[i]:
            targets[i], maxes[i] = quick, min(maxes[i], max(quick + 0.8, 2.4))
    return targets, maxes, labels


def plan_chapters(ctx: RunContext, words_file: WordsFile) -> tuple[list[PlanChapter], str, dict[str, Any]]:
    words = words_file.words
    sentences = _sentences(words)
    listing = "\n".join(
        f"[{n}] ({_fmt_time(words[a].start)}) " + " ".join(w.text for w in words[a : b + 1])
        for n, (a, b) in enumerate(sentences)
    )
    if words_file.chapters:
        chapters = [
            PlanChapter(title=c.title.upper()[:48], startWord=c.wordIndex, fromScript=True) for c in words_file.chapters
        ]
        # The chapters come from the script («## »), but the rest of the outline is still needed: the protagonist,
        # the story's events and the visual context. Skipping it (pati2, every script with automatic chapters)
        # left a story about Trusova without protagonist: no identity checks, no judge context, Pexels people.
        try:
            result = complete_json(
                ctx, stage=STAGE, section="planner", system=outline_system(ctx), max_tokens=2000,
                user=f"TÍTULO: {words_file.title}\n\nLos capítulos ya están en el guion: devuelve \"chapters\": [].\n\n"
                     f"FRASES:\n{listing}")
        except LLMError as error:
            print(f"   Aviso: sin análisis de la historia ({str(error)[:120]})")
            result = {}
        context = str(result.get("context") or "").strip()[:400]
    else:
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
    targets: list[float] | None = None,
    maxes: list[float] | None = None,
):
    """Return shots as (firstWord, lastWord), contiguous and covering all words — and, with
    `with_times`, the start second of each shot (a cut may fall inside a long pause).
    `targets`/`maxes` (one per word) vary the pace: the shot starting at word a aims at targets[a]."""

    n = len(words)
    times = _boundary_times(words, duration)
    forced = []
    for b in sorted(b for b in forced_starts if 0 < b < n):
        # a chapter that starts too close to the start, the end or the previous one cannot be a cut of its own
        # (avion5/avion9: a «## » 1.2 s into the voice made s001 1.2 s long and the whole planner fail)
        previous = words[forced[-1]].start if forced else 0.0
        if words[b].start - previous >= min_seconds and duration - words[b].start >= min_seconds:
            forced.append(b)
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
                aim = targets[a] if targets else target
                most = min(maxes[a], max_seconds) if maxes else min(max_seconds, MAX_SHOT_SECONDS_DEFAULT)
                if any(a < f < b for f in forced):
                    continue
                for i, ta in enumerate(times[a]):
                    if best[a][i] == inf:
                        continue
                    d = tb - ta
                    if d <= 0:
                        continue
                    penalty = ((d - aim) / 0.8) ** 2
                    # Outside 1.5-5 s the plan is invalid: only when nothing else fits. Longer than the pace wants
                    # (the hook's 2.4 s) is a preference, never worth an invalid shot (avion5/avion9: a 1.2 s s001
                    # beat a valid 2.8 s one because both cost the same 1000 per second).
                    if d < min_seconds:
                        penalty += 100_000 * (min_seconds - d + 0.1)
                    elif d > max_seconds:
                        penalty += 100_000 * (d - max_seconds + 0.1)
                    elif d > most:
                        penalty += 300 * (d - most + 0.1)
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
- Un plano suele ser un TROZO de frase («de 2023.», «a las cinco y siete», «unos 4.500 metros»): las búsquedas
  ilustran el SENTIDO de la frase entera y del tramo (TEXTO ANTERIOR/POSTERIOR), nunca las palabras sueltas del
  trozo. Fechas, horas, cifras, unidades y conectores no son cosas que se vean: nada de calendarios, relojes,
  contadores ni altímetros por una fecha, una hora o una cifra; se busca el hecho del que se habla (el avión, la
  fábrica, el atleta, la noticia de ese día).

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
  Son cortos (1,5-2 s). Si su texto dice una FECHA, una HORA o una CIFRA clave («30 de septiembre»,
  «19:46», «413 millones»), haz de ese plano un "stat" con ese dato tal como se dice: en grande
  sobre el metraje, como un titular.
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
                system=LABEL_SYSTEM + (f"\n\nEN ESTE CANAL:\n{note}" if (note := str(ctx.section("planner").get("shots_note") or "").strip()) else ""),
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
    # Still missing (no footage of its own, or never valid): b-roll with the nearest good shot's search, so one
    # stubborn shot never fails the whole video (pati2: «4,22» kept coming back on a datacard without b-roll).
    order = [s["id"] for s in batch]
    for index, shot in enumerate(batch):
        if shot["id"] in good:
            continue
        nearest = sorted((abs(order.index(sid) - index), sid) for sid, c in good.items() if isinstance(c.get("broll"), dict))
        if not nearest:
            continue
        plain = _merge(shot, {"type": "broll", "broll": dict(good[nearest[0][1]]["broll"])})
        try:
            Shot.model_validate(plain)
        except ValidationError:
            continue
        print(f"   {shot['id']}: sin plano válido tras {attempts} intentos → b-roll como {nearest[0][1]}")
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
    # years in the labels too (pati2: «Japón 2024» for a 2026 competition the narration dates right)
    labels = [str(shot["stat"].get("label", ""))] if isinstance(shot.get("stat"), dict) else []
    if isinstance(shot.get("panel"), dict):
        labels += [str(shot["panel"].get("title", ""))]
        labels += [str(row.get("label", "")) for row in shot["panel"].get("rows", []) if isinstance(row, dict)]
    for label in labels:
        years = sorted({int(y) for y in re.findall(r"(?<!\d)(1[89]\d\d|20\d\d)(?!\d)", label)} - {int(n) for n in said})
        if years:
            errors.append(f"{shot['id']}: el año {years[0]} de la etiqueta {label!r} no se dice en este plano ni en los "
                          "anteriores; quítalo o usa el que dice el texto")
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


def compact_figure(value: str) -> str:
    """A figure short enough for the giant number (≤ 16 characters): '25.000 millones de dólares' → '25.000 M$'."""

    value = " ".join(value.split())
    if len(value) <= 16:
        return value
    for pattern, short in ((r"\s*mil millones de (dólares|euros)", r" MM\1"), (r"\s*millones de (dólares|euros)", r" M\1"),
                           (r"\s*mil millones", " MM"), (r"\s*millones", " M"), (r"\s*por ciento", " %"),
                           (r"(dólares|dolares)", "$"), (r"euros", "€"), (r"\s*unidades", " uds."),
                           (r"\s*kilómetros", " km"), (r"\s*pasajeros", " pax")):
        value = re.sub(pattern, short, value, flags=re.IGNORECASE)
    value = re.sub(r"M(M?)(dólares|dolares)", r"M\1$", value)
    value = re.sub(r"M(M?)euros", r"M\1€", value)
    return " ".join(value.split())


def _merge(structural: dict[str, Any], label: dict[str, Any]) -> dict[str, Any]:
    shot = {k: structural[k] for k in ("id", "startWord", "endWord", "start", "end", "text", "chapter")}
    if structural.get("pace"):
        shot["pace"] = structural["pace"]
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
        stat = shot.get("stat") if isinstance(shot.get("stat"), dict) else None
        if stat is not None:
            stat["value"] = compact_figure(str(stat.get("value") or ""))
            if len(stat["value"]) > 16 and isinstance(shot.get("broll"), dict):   # still too long for the giant figure
                shot["type"] = "broll"
                shot.pop("stat", None)
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
    pace_cfg = ctx.section("pacing")
    base = float(pace_cfg.get("base_seconds", cfg.get("target_shot_seconds", 2.6))) if pace_cfg.get("enabled", True) \
        else float(cfg.get("target_shot_seconds", 2.6))
    marks = pacing(ctx, words)
    targets, maxes, paces = pace_targets(ctx, words, marks, base)
    if marks:
        print(f"   Ritmo: {sum(k == 'slow' for k in marks.values())} frases lentas · "
              f"{sum(k == 'fast' for k in marks.values())} rápidas · base {base:.1f} s por plano")
    cuts, cut_starts = cut_shots(
        words,
        words_file.durationSeconds,
        target=base,
        forced_starts={c.startWord for c in chapters},
        with_times=True,
        targets=targets,
        maxes=maxes,
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
        if paces[first] and paces[first] == paces[last]:
            item["pace"] = paces[first]
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
