"""Local CLIP (OpenCLIP) text/image embeddings with a global on-disk cache.

Frame embeddings are cached per video (cache/embeddings/<model>/<video>.npz) and per image,
so a video used by several shots — or by a later project — is only encoded once.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Sequence

import cv2
import numpy as np

_MEAN = np.array([0.48145466, 0.4578275, 0.40821073], np.float32)
_STD = np.array([0.26862954, 0.26130258, 0.27577711], np.float32)


class ClipScorer:
    def __init__(self, *, cache_dir: Path, model: str = "ViT-B-32", pretrained: str = "laion2b_s34b_b79k",
                 batch_size: int = 64, threads: int = 0) -> None:
        self.cache_dir = cache_dir / "embeddings" / f"{model}-{pretrained}"
        self.model_name = model
        self.pretrained = pretrained
        self.batch_size = batch_size
        self.threads = threads
        self._model = None
        self._tokenizer = None
        self._lock = threading.Lock()

    def _load(self) -> None:
        if self._model is not None:
            return
        import open_clip
        import torch

        if self.threads:
            torch.set_num_threads(self.threads)
        model, _, _ = open_clip.create_model_and_transforms(self.model_name, pretrained=self.pretrained)
        model.eval()
        self._model = model
        self._tokenizer = open_clip.get_tokenizer(self.model_name)

    @staticmethod
    def _prep(bgr: np.ndarray) -> np.ndarray:
        rgb = bgr[:, :, ::-1]
        h, w = rgb.shape[:2]
        scale = 224 / min(h, w)
        resized = cv2.resize(rgb, (max(224, round(w * scale)), max(224, round(h * scale))), interpolation=cv2.INTER_AREA)
        h, w = resized.shape[:2]
        y, x = (h - 224) // 2, (w - 224) // 2
        crop = resized[y : y + 224, x : x + 224].astype(np.float32) / 255.0
        return ((crop - _MEAN) / _STD).transpose(2, 0, 1)

    def embed_images(self, images: Sequence[np.ndarray]) -> np.ndarray:
        if not images:
            return np.zeros((0, 512), np.float32)
        import torch

        with self._lock:
            self._load()
            chunks = []
            for i in range(0, len(images), self.batch_size):
                batch = torch.from_numpy(np.stack([self._prep(im) for im in images[i : i + self.batch_size]]))
                with torch.no_grad():
                    vectors = self._model.encode_image(batch).float()
                chunks.append(torch.nn.functional.normalize(vectors, dim=-1).numpy())
        return np.concatenate(chunks)

    def embed_texts(self, texts: Sequence[str]) -> np.ndarray:
        import torch

        with self._lock:
            self._load()
            with torch.no_grad():
                vectors = self._model.encode_text(self._tokenizer(list(texts))).float()
            return torch.nn.functional.normalize(vectors, dim=-1).numpy()

    def shot_vector(self, prompts: Sequence[str]) -> np.ndarray:
        """One direction for the shot: normalised mean of its prompt embeddings."""

        vectors = self.embed_texts(prompts)
        mean = vectors.mean(axis=0)
        return mean / (np.linalg.norm(mean) or 1.0)

    # --- cached per source --------------------------------------------------------------

    def cached(self, key: str, compute) -> tuple[np.ndarray, np.ndarray]:
        """(times or [0], vectors) for `key`, computing and storing them if needed."""

        path = self.cache_dir / f"{key}.npz"
        if path.is_file():
            try:
                data = np.load(path)
                return data["times"], data["vectors"]
            except (OSError, ValueError, KeyError):
                pass
        times, images = compute()
        vectors = self.embed_images(images)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.stem + ".tmp.npz")
        np.savez_compressed(tmp, times=np.asarray(times, np.float32), vectors=vectors.astype(np.float16))
        tmp.replace(path)
        return np.asarray(times, np.float32), vectors.astype(np.float16)
