from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path
from typing import Literal

import requests

from ..config import Settings
from ..timing import METRICS


ImageQuality = Literal["medium", "high"]


class OpenAIImageClient:
    def __init__(self, settings: Settings, *, model: str = "gpt-image-2") -> None:
        # Imported lazily so modules that only need Pexels/YouTube load without the SDK.
        from openai import OpenAI

        self._client = OpenAI(api_key=settings.openai_api_key)
        self._model = model

    def image_path(self, prompt: str, output_dir: Path, quality: ImageQuality = "medium") -> Path:
        """Deterministic file for a prompt+quality, so a repeated run reuses the paid image."""

        digest = hashlib.sha1(f"{self._model}|{quality}|{prompt}".encode("utf-8")).hexdigest()[:12]
        return output_dir / f"generated-{digest}.png"

    def generate_image(
        self,
        prompt: str,
        output_dir: Path,
        *,
        quality: ImageQuality = "medium",
    ) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        image_path = self.image_path(prompt, output_dir, quality)
        if image_path.is_file() and image_path.stat().st_size > 0:
            METRICS.count("openai_images.cache_hits")
            return image_path

        METRICS.count(f"openai_images.generated.{quality}")
        with METRICS.timed("openai_images.generate"):
            response = self._client.images.generate(
                model=self._model,
                prompt=prompt,
                size="1536x1024",
                quality=quality,
                output_format="png",
            )
        result = response.data[0]
        encoded_image = getattr(result, "b64_json", None)
        if encoded_image:
            self._store(image_path, base64.b64decode(encoded_image))
            return image_path

        image_url = getattr(result, "url", None)
        if image_url:
            image_response = requests.get(image_url, timeout=60)
            image_response.raise_for_status()
            self._store(image_path, image_response.content)
            return image_path

        raise RuntimeError("OpenAI Images no devolvió ni b64_json ni URL para la imagen generada.")

    @staticmethod
    def _store(image_path: Path, content: bytes) -> None:
        """Write through a temp file: a partial image must never look like a cached one."""

        partial = image_path.with_name(f".{image_path.name}.part")
        partial.write_bytes(content)
        os.replace(partial, image_path)
