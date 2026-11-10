from __future__ import annotations

import json
from typing import Any, Sequence

from ..config import Settings
from ..templates import load_manifest
from ..timing import METRICS
from ..types import WordTimestamp


# Bump when the prompt contract changes in a way the text itself does not capture.
SEGMENTATION_PROMPT_VERSION = "2"
SEGMENTATION_MAX_TOKENS = 16000

_SEGMENTATION_SYSTEM_PROMPT_TEMPLATE = """
Eres un servicio de segmentación para un pipeline de vídeo. Devuelve únicamente
JSON válido, sin Markdown ni texto antes o después del objeto JSON.

Devuelve exactamente esta forma:
{
  "scenes": [
    {
      "text": "titular, cifra o frase visual de 3-10 palabras; nunca la transcripción completa",
      "keywords": ["keyword 1", "keyword 2"],
      "visualIntent": "descripción concreta y específica del plano visual en inglés",
      "mustContain": ["elemento visual obligatorio"],
      "avoid": ["presentador", "logo", "intro"],
      "preferredShot": "wide | medium | close-up | action | archive",
      "sceneType": "hook | narrative | stat | transition",
      "templateName": "__TEMPLATE_NAMES__",
      "start_word_index": 0,
      "end_word_index": 10,
      "timelinePoints": [{"label": "2008", "value": "...", "position": 0.0}],
      "comparisonColumns": [{"title": "...", "items": ["..."]}, {"title": "...", "items": ["..."]}]
    }
  ]
}

Usa los índices de palabra proporcionados para que el consumidor pueda
calcular la duración con timestamps reales. Mantén entre 2 y 3 keywords por
escena cuando sea posible. Esas keywords deben ser consultas visuales concretas
en inglés de 2-5 palabras (por ejemplo, "casino roulette table" o "casino
security camera"), nunca palabras abstractas, frases en español ni solo una
cifra. Elige sceneType según la función narrativa, pero
elige templateName únicamente entre las plantillas compatibles con los campos
disponibles en esta respuesta. No clasifiques ninguna escena como avatar: la
generación/importación de avatar está desactivada en este pipeline.

Para cada escena, genera `visualIntent` como una descripción breve y visible
en inglés de qué debería aparecer en el plano, no una reformulación abstracta
del guion. `mustContain` debe tener 1-3 elementos observables esenciales y
`avoid` debe listar solo distracciones concretas (por ejemplo, presentador,
intro, logo) cuando aplique. `preferredShot` indica el encuadre o acción más
útil. No inventes sucesos visuales; si la escena explica una idea abstracta,
elige una metáfora visual documental reconocible.

Usa sceneType "hook" para la primera escena y para preguntas retóricas o
frases de apertura que deban aparecer como texto grande centrado sobre el vídeo.
Elige "lower-third" únicamente cuando aparezca una persona, empresa, lugar o
institución identificable; no lo uses para cada frase narrativa genérica.
Elige "multi-shot-montage" o "news-image-montage" cuando la frase describa una
secuencia rápida, una lista de ejemplos o material de archivo.
Elige "blueprint-data-panel" para datos técnicos o analíticos. Elige
"timeline-graphic" solo si incluyes 3-6 timelinePoints con position entre 0 y 1.
Elige "comparison-panel" solo si incluyes dos o más comparisonColumns. No uses
"title-card" como plantilla genérica: resérvala para transiciones o separadores
de sección que deban ser pantalla completa y negra.

Para sceneType "stat", escribe text como una cifra principal y una etiqueta
corta, no como una oración larga. Si hay dos cifras comparables, usa
comparisonColumns. Los campos timelinePoints y comparisonColumns son
opcionales; no los incluyas si la escena no contiene esa estructura.

IMPORTANTE: las escenas deben cubrir TODO el audio de forma continua. La primera
escena empieza en 0, cada escena siguiente empieza justo después del final de la
anterior y la última termina en la última palabra. No resumas ni saltees bloques
de narración para reducir el número de escenas; apunta a bloques de 5-15 segundos.
""".strip()

# The template list comes from templates/manifest.json so the prompt, the
# validator and the Remotion registry can never drift apart.
SEGMENTATION_SYSTEM_PROMPT = _SEGMENTATION_SYSTEM_PROMPT_TEMPLATE.replace(
    "__TEMPLATE_NAMES__", " | ".join(load_manifest().llm_template_names)
)


def _timed_words_json(words: Sequence[WordTimestamp]) -> str:
    """Legacy payload: one object per word with index, word, start and end."""

    return json.dumps(
        [
            {"index": index, "word": word["word"], "start": word["start"], "end": word["end"]}
            for index, word in enumerate(words)
        ],
        ensure_ascii=False,
    )


def _compact_words_json(words: Sequence[WordTimestamp]) -> str:
    """Compact payload: ``[index, word, start]`` per word (about a third of the size)."""

    return json.dumps(
        [[index, word["word"], round(float(word["start"]), 2)] for index, word in enumerate(words)],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def build_segmentation_user_prompt(
    script_text: str,
    words: Sequence[WordTimestamp],
    *,
    words_format: str = "compact",
) -> str:
    header = (
        "Segmenta el siguiente guion. Responde en JSON siguiendo exactamente el esquema indicado.\n\n"
        f"GUION:\n{script_text.strip()}\n\n"
    )
    if words_format == "full":
        return header + f"PALABRAS CON TIMESTAMP:\n{_timed_words_json(words)}"
    audio_end = float(words[-1]["end"]) if words else 0.0
    return header + (
        "PALABRAS CON TIMESTAMP (cada elemento es [índice, palabra, segundo_de_inicio]; "
        f"la última palabra termina en el segundo {audio_end:.2f}):\n{_compact_words_json(words)}"
    )


def segmentation_cache_fingerprint(settings: Settings) -> str:
    """Everything, besides script and words, that changes the model's answer."""

    return "|".join(
        [
            SEGMENTATION_PROMPT_VERSION,
            settings.llm_model,
            settings.segment_words_format,
            str(SEGMENTATION_MAX_TOKENS),
            SEGMENTATION_SYSTEM_PROMPT,
        ]
    )


class DeepSeekClient:
    def __init__(self, settings: Settings) -> None:
        # Imported lazily so QA, tests and `doctor` work without the SDK loaded.
        from openai import OpenAI

        self._client = OpenAI(api_key=settings.llm_api_key, base_url=settings.deepseek_base_url)
        self._model = settings.llm_model
        self._words_format = settings.segment_words_format

    def segment_script(
        self,
        script_text: str,
        words: Sequence[WordTimestamp],
    ) -> list[dict[str, Any]]:
        if not script_text.strip():
            raise ValueError("El guion está vacío.")
        if not words:
            raise ValueError("No hay timestamps de palabras para segmentar el guion.")

        user_prompt = build_segmentation_user_prompt(
            script_text, words, words_format=self._words_format
        )

        METRICS.count("deepseek.segmentation_calls")
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SEGMENTATION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0,
            # A full 8-9 minute narration can require dozens of scene objects.
            # This is an output cap for this request, not an account quota.
            max_tokens=SEGMENTATION_MAX_TOKENS,
            # DeepSeek V4 enables thinking by default. Disable it explicitly
            # because this call only needs fast structured JSON output.
            extra_body={"thinking": {"type": "disabled"}},
        )

        choice = response.choices[0]
        if choice.finish_reason == "length":
            raise RuntimeError(
                "DeepSeek truncó la segmentación al llegar a "
                f"{SEGMENTATION_MAX_TOKENS} tokens de salida. Divide el guion en dos vídeos o sube "
                "SEGMENTATION_MAX_TOKENS en pipeline/clients/deepseek_client.py. "
                "La transcripción ya está en caché: relanzar no vuelve a pagar Whisper."
            )

        content = choice.message.content
        if not content:
            raise RuntimeError("DeepSeek devolvió contenido vacío para la segmentación.")

        payload = json.loads(content)
        scenes = payload.get("scenes") if isinstance(payload, dict) else None
        if not isinstance(scenes, list):
            raise ValueError("La respuesta de DeepSeek no contiene un array 'scenes'.")

        return [scene for scene in scenes if isinstance(scene, dict)]


def segment_with_deepseek(
    script_text: str,
    words: Sequence[WordTimestamp],
    settings: Settings,
) -> list[dict[str, Any]]:
    return DeepSeekClient(settings).segment_script(script_text, words)
