from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from typing import Literal

import requests
from openai import OpenAI

from ..config import Settings


ImageQuality = Literal["medium", "high"]


class OpenAIImageClient:
    def __init__(self, settings: Settings, *, model: str = "gpt-image-2") -> None:
        self._client = OpenAI(api_key=settings.openai_api_key)
        self._model = model

    def generate_image(
        self,
        prompt: str,
        output_dir: Path,
        *,
        quality: ImageQuality = "medium",
    ) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        response = self._client.images.generate(
            model=self._model,
            prompt=prompt,
            size="1536x1024",
            quality=quality,
            output_format="png",
        )
        result = response.data[0]
        image_path = output_dir / f"generated-{hashlib.sha1(prompt.encode('utf-8')).hexdigest()[:12]}.png"
        encoded_image = getattr(result, "b64_json", None)
        if encoded_image:
            image_path.write_bytes(base64.b64decode(encoded_image))
            return image_path

        image_url = getattr(result, "url", None)
        if image_url:
            image_response = requests.get(image_url, timeout=60)
            image_response.raise_for_status()
            image_path.write_bytes(image_response.content)
            return image_path

        raise RuntimeError("OpenAI Images no devolvió ni b64_json ni URL para la imagen generada.")
