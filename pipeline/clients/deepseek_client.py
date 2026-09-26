from __future__ import annotations

import json
from typing import Any, Sequence

from openai import OpenAI

from ..config import Settings
from ..types import WordTimestamp


SEGMENTATION_SYSTEM_PROMPT = """
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
      "templateName": "kinetic-text-hook | kenburns-image | lower-third | multi-shot-montage | news-image-montage | number-callout | stat-overlay | blueprint-data-panel | timeline-graphic | comparison-panel | title-card | whip-transition",
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


def _timed_words_json(words: Sequence[WordTimestamp]) -> str:
    return json.dumps(
        [
            {"index": index, "word": word["word"], "start": word["start"], "end": word["end"]}
            for index, word in enumerate(words)
        ],
        ensure_ascii=False,
    )


class DeepSeekClient:
    def __init__(self, settings: Settings) -> None:
        self._client = OpenAI(api_key=settings.llm_api_key, base_url=settings.deepseek_base_url)
        self._model = settings.llm_model

    def segment_script(
        self,
        script_text: str,
        words: Sequence[WordTimestamp],
    ) -> list[dict[str, Any]]:
        if not script_text.strip():
            raise ValueError("El guion está vacío.")
        if not words:
            raise ValueError("No hay timestamps de palabras para segmentar el guion.")

        user_prompt = (
            "Segmenta el siguiente guion. Responde en JSON siguiendo exactamente el esquema indicado.\n\n"
            f"GUION:\n{script_text.strip()}\n\n"
            f"PALABRAS CON TIMESTAMP:\n{_timed_words_json(words)}"
        )

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
            max_tokens=16000,
            # DeepSeek V4 enables thinking by default. Disable it explicitly
            # because this call only needs fast structured JSON output.
            extra_body={"thinking": {"type": "disabled"}},
        )

        choice = response.choices[0]
        if choice.finish_reason == "length":
            raise RuntimeError("DeepSeek truncó la segmentación; aumenta max_tokens o reduce el guion.")

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
