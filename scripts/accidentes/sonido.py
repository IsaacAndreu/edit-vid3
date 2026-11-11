"""Sonido de los motores de un vuelo real, sintetizado con el N1 del FDR: public/accidentes/<caso>/motores.mp3.

    python3 scripts/accidentes/sonido.py public/accidentes/<caso>/vuelo.json

No es una grabación: es un sonido de reactor genérico (rugido de banda ancha + silbido del fan) cuyo volumen y tono
siguen el N1 de cada motor segundo a segundo, a tiempo real desde la primera muestra de vuelo.json. Cuando el N1 cae
(las aves, un fallo), el sonido cae a la vez. Las escenas lo reproducen con `engineSound`.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

RATE = 22050


def n1_series(points: list[dict], k: int) -> np.ndarray:
    s = np.array([p["s"] for p in points], dtype=float)
    v = np.array([(p["n1"][k] if p["n1"][k] is not None else np.nan) for p in points], dtype=float)
    ok = ~np.isnan(v)
    t = np.arange(0, s[-1] - s[0], 1 / RATE)
    return np.interp(t, s[ok] - s[0], v[ok]) if ok.any() else np.zeros_like(t)


def engine(n1: np.ndarray, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    x = n1 / 100.0
    # rugido: ruido blanco con un paso bajo de un polo cuya frecuencia de corte sube con el N1
    noise = rng.standard_normal(len(x))
    cutoff = 150 + 2600 * x ** 1.5
    alpha = np.exp(-2 * np.pi * cutoff / RATE)
    roar = np.empty_like(noise)
    acc = 0.0
    for i in range(len(noise)):          # filtro variable: bucle sencillo (unos segundos para un vuelo de minutos)
        acc = alpha[i] * acc + (1 - alpha[i]) * noise[i]
        roar[i] = acc
    # silbido del fan: un tono cuya frecuencia sigue el N1, con algo de vibrato
    freq = 180 + 1900 * x
    phase = 2 * np.pi * np.cumsum(freq) / RATE
    whine = np.sin(phase) * 0.25 + np.sin(2 * phase) * 0.08
    amp = 0.05 + 0.95 * x ** 2
    return (roar * 3.0 + whine * x) * amp


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    path = Path(sys.argv[1])
    data = json.loads(path.read_text(encoding="utf-8"))
    pts = data["points"]
    mix = engine(n1_series(pts, 0), 1) + engine(n1_series(pts, 1), 2)
    mix = mix / (np.max(np.abs(mix)) or 1) * 0.85
    pcm = (mix * 32767).astype(np.int16)
    out = path.parent / "motores.mp3"
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "m.wav"
        with wave.open(str(wav), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(pcm.tobytes())
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-b:a", "96k", str(out)], check=True)
    print(f"{out}: {len(pcm) / RATE:.0f} s de motores sintetizados desde el N1 (desde la hora {pts[0]['s']})")


if __name__ == "__main__":
    main()
