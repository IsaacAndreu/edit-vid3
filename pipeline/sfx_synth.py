"""Sound effects made in code (numpy): no downloads, no licences, the same sound every time.

The motion-design set was measured on a reference promo (68 events in 32 s, mixed quietly under the music):
- `tick`: very short high ticks (6-7 kHz, ~10 ms) in bursts every ~0.13 s as UI elements appear;
- `click` / `type-*`: keyboard clicks (2-3 kHz, ~20 ms) every ~0.12 s while text types in;
- `whoosh-up`: an airy noise swoosh rising from ~1 kHz to ~5 kHz (0.2-0.45 s), the loudest sound, on transitions;
- `whoosh-down`: the same falling (5 kHz → 250 Hz), shorter;
- `glitch`: four bursts of flat, crushed noise 0.1 s apart (the pixel/scramble moments);
- `pop`: a low tonal blip (~400 Hz falling, 0.1 s) when a card lands;
- `blip`, `blip-up`, `data`: digital square-wave blips and a rapid stream of very high ticks (~10 kHz);
- `scan`: a 0.2-0.3 s band of noise with a resonant sweep (a scanner passing over a receipt);
- `thud`, `impact`, `riser`, `shutter`: the low hit, the stamp, the build-up, the camera.
And the ones the drawn formats need: for the stickman films `slap` (the rule sticker), `buzz` (the phone), `ping`
(a message), `heartbeat`, `knock`; for the map explainers `marker` (a pen stroke), `scribble`, `paper` (a tag sliding
in), `flip` (a page turning), `tape`, `stamp`.

`ensure(root)` writes them once to cache/sfx/<name>.wav (44.1 kHz mono); `path(root, name)` gives one.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SR = 44100
VERSION = 3


def _t(seconds: float) -> np.ndarray:
    return np.arange(int(SR * seconds)) / SR


def _noise(seconds: float, seed: int) -> np.ndarray:
    return np.random.default_rng(seed).uniform(-1, 1, int(SR * seconds))


def _env(n: int, attack: float, decay: float) -> np.ndarray:
    """Fast attack, exponential decay (seconds)."""

    t = np.arange(n) / SR
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    return a * np.exp(-np.maximum(0, t - attack) / max(decay, 1e-4))


def _bandpass(x: np.ndarray, centre: np.ndarray | float, q: float = 4.0) -> np.ndarray:
    """A band-pass whose centre can move over time: short FFT frames (overlap-add), each keeping a band around the
    centre at that moment (a bell on a log-frequency axis, narrower with a higher q)."""

    n, hop = 512, 128
    centre = np.broadcast_to(np.asarray(centre, dtype=float), x.shape)
    pad = np.concatenate([np.zeros(n), x, np.zeros(n)])
    window = np.hanning(n)
    freqs = np.fft.rfftfreq(n, 1 / SR)
    out = np.zeros_like(pad)
    norm = np.zeros_like(pad)
    width = 0.9 / q                                          # octaves (one sigma)
    for i in range(0, len(pad) - n, hop):
        c = centre[min(len(x) - 1, max(0, i - n + n // 2))]
        spec = np.fft.rfft(pad[i:i + n] * window)
        bell = np.exp(-0.5 * (np.log2(np.maximum(freqs, 1) / c) / width) ** 2)
        out[i:i + n] += np.fft.irfft(spec * bell, n) * window
        norm[i:i + n] += window ** 2
    return (out / np.maximum(norm, 1e-6))[n:n + len(x)] * 2


def _lowpass(x: np.ndarray, cutoff: float) -> np.ndarray:
    a = np.exp(-2 * np.pi * cutoff / SR)
    out = np.empty_like(x)
    y = 0.0
    for i, v in enumerate(x):
        y = (1 - a) * v + a * y
        out[i] = y
    return out


def _sine(freq: np.ndarray | float, seconds: float) -> np.ndarray:
    freq = np.broadcast_to(np.asarray(freq, dtype=float), (int(SR * seconds),))
    return np.sin(2 * np.pi * np.cumsum(freq) / SR)


def _norm(x: np.ndarray, peak: float = 0.9) -> np.ndarray:
    m = np.max(np.abs(x)) or 1.0
    fade = np.ones_like(x)
    k = min(len(x), int(0.004 * SR))
    fade[-k:] = np.linspace(1, 0, k)                       # never a click at the end
    return x / m * peak * fade


def _place(parts: list[tuple[float, np.ndarray]], seconds: float) -> np.ndarray:
    out = np.zeros(int(SR * seconds))
    for at, x in parts:
        i = int(at * SR)
        n = min(len(x), len(out) - i)
        if n > 0:
            out[i:i + n] += x[:n]
    return out


# --- the sounds ---------------------------------------------------------------------------------------------------

def tick(freq: float = 6600, seed: int = 1) -> np.ndarray:
    n = int(0.03 * SR)
    t = np.arange(n) / SR
    x = np.sin(2 * np.pi * freq * t) * 0.9 + _bandpass(_noise(0.03, seed), freq, 3) * 0.3
    return _norm(x * _env(n, 0.0005, 0.006), 0.7)


def click(seed: int = 2, pitch: float = 2600) -> np.ndarray:
    n = int(0.04 * SR)
    body = _bandpass(_noise(0.04, seed), pitch, 3) * 1.6 + np.sin(2 * np.pi * pitch * 0.45 * np.arange(n) / SR) * 0.3
    return _norm(body * _env(n, 0.0008, 0.009), 0.8)


def pop() -> np.ndarray:
    s = 0.13
    freq = 430 * np.exp(-np.arange(int(SR * s)) / SR / 0.08) + 260
    x = _sine(freq, s) + _bandpass(_noise(s, 3), 2400, 2) * 0.25 * np.exp(-np.arange(int(SR * s)) / SR / 0.004)
    return _norm(x * _env(len(x), 0.002, 0.05))


def blip(freq: float = 1800, seconds: float = 0.05) -> np.ndarray:
    t = _t(seconds)
    x = np.sign(np.sin(2 * np.pi * freq * t)) * 0.5
    return _norm(_lowpass(x, 6000) * _env(len(t), 0.001, seconds * 0.5), 0.5)


def blip_up() -> np.ndarray:
    return np.concatenate([blip(1400, 0.045), blip(2100, 0.06)])


def data() -> np.ndarray:
    rng = np.random.default_rng(7)
    parts = [(i * 0.075 + rng.uniform(0, 0.015), tick(rng.uniform(8800, 10800), i) * rng.uniform(0.5, 1)) for i in range(9)]
    return _norm(_place(parts, 0.75), 0.6)


def whoosh(start: float, end: float, seconds: float, seed: int = 4) -> np.ndarray:
    n = int(SR * seconds)
    t = np.arange(n) / SR
    curve = start * (end / start) ** (t / seconds)
    x = _bandpass(_noise(seconds, seed), curve, 1.6) + _bandpass(_noise(seconds, seed + 9), curve * 1.5, 2.5) * 0.4
    shape = np.sin(np.pi * np.clip(t / seconds, 0, 1)) ** 1.6
    return _norm(x * shape, 0.85)


def glitch() -> np.ndarray:
    rng = np.random.default_rng(11)
    parts = []
    for i in range(4):
        s = rng.uniform(0.04, 0.07)
        x = _noise(s, 20 + i)
        hold = int(rng.uniform(6, 22))                        # sample-and-hold: crushed, digital
        x = np.repeat(x[::hold], hold)[: int(SR * s)]
        x = np.round(x * 4) / 4
        parts.append((i * 0.1, x * _env(len(x), 0.001, s * 0.8) * rng.uniform(0.6, 1)))
    return _norm(_place(parts, 0.45), 0.7)


def scan() -> np.ndarray:
    s = 0.32
    t = _t(s)
    sweep = 1500 + 3500 * (t / s)
    x = _bandpass(_noise(s, 13), sweep, 8) * 1.2 + _bandpass(_noise(s, 14), 5000, 1.2) * 0.3
    return _norm(x * np.sin(np.pi * t / s) ** 0.6, 0.6)


def thud(freq: float = 62) -> np.ndarray:
    s = 0.5
    t = _t(s)
    body = _sine(freq * (1 + 1.2 * np.exp(-t / 0.03)), s) * np.exp(-t / 0.16)
    attack = _lowpass(_noise(s, 15), 1800) * np.exp(-t / 0.012) * 1.5
    return _norm(body + attack)


def impact() -> np.ndarray:
    s = 1.1
    t = _t(s)
    boom = _sine(48 * (1 + 2 * np.exp(-t / 0.04)), s) * np.exp(-t / 0.35)
    crack = _bandpass(_noise(s, 16), 2200, 1.2) * np.exp(-t / 0.03) * 0.8
    tail = _lowpass(_noise(s, 17), 600) * np.exp(-t / 0.4) * 0.5
    return _norm(boom + crack + tail)


def riser() -> np.ndarray:
    s = 1.6
    t = _t(s)
    curve = 300 * (14 ** (t / s))
    x = _bandpass(_noise(s, 18), curve, 3) + _sine(curve * 0.5, s) * 0.15
    return _norm(x * (t / s) ** 2.2, 0.75)


def shutter() -> np.ndarray:
    a = click(21, 3800)
    b = click(22, 2600)
    return _norm(_place([(0, a), (0.045, b * 0.8)], 0.12), 0.8)


def slap() -> np.ndarray:
    s = 0.25
    t = _t(s)
    hit = _lowpass(_noise(s, 23), 3500) * np.exp(-t / 0.018)
    low = _sine(140 * (1 + np.exp(-t / 0.02)), s) * np.exp(-t / 0.06) * 0.6
    return _norm(hit + low)


def buzz() -> np.ndarray:
    s = 0.36
    t = _t(s)
    x = np.sign(np.sin(2 * np.pi * 172 * t)) * (0.6 + 0.4 * np.sin(2 * np.pi * 31 * t))
    x = _lowpass(x, 900) * np.sin(np.pi * t / s) ** 0.3
    return _norm(_place([(0, x), (0.48, x)], 0.9), 0.6)


def ping() -> np.ndarray:
    s = 0.35
    t = _t(s)
    x = np.sin(2 * np.pi * 1320 * t) * np.exp(-t / 0.08) + np.sin(2 * np.pi * 1760 * t) * np.exp(-np.maximum(0, t - 0.07) / 0.1) * (t > 0.07)
    return _norm(x, 0.6)


def heartbeat() -> np.ndarray:
    beat = thud(55)
    return _norm(_place([(0, beat), (0.22, beat * 0.7)], 0.8), 0.9)


def knock() -> np.ndarray:
    s = 0.2
    t = _t(s)
    one = (_bandpass(_noise(s, 25), 190, 6) * 2 + _bandpass(_noise(s, 26), 900, 3) * 0.6) * np.exp(-t / 0.03)
    return _norm(_place([(0, one), (0.18, one * 0.9), (0.36, one)], 0.65))


def marker(seconds: float = 0.55, seed: int = 27) -> np.ndarray:
    t = _t(seconds)
    rough = 0.55 + 0.45 * np.abs(np.sin(2 * np.pi * 17 * t + np.random.default_rng(seed).uniform(0, 3, len(t)) * 0.2))
    x = _bandpass(_noise(seconds, seed), 3400, 1.4) * rough + _bandpass(_noise(seconds, seed + 1), 900, 2) * 0.3
    return _norm(x * np.sin(np.pi * t / seconds) ** 0.4, 0.55)


def scribble() -> np.ndarray:
    s = 0.85
    t = _t(s)
    strokes = (np.sin(2 * np.pi * 7.5 * t) > -0.2).astype(float)
    return _norm(marker(s, 29) * (0.3 + 0.7 * _lowpass(strokes, 40)), 0.55)


def paper() -> np.ndarray:
    s = 0.38
    t = _t(s)
    x = _bandpass(_noise(s, 31), 1800 + 2500 * (t / s), 0.9) * np.sin(np.pi * t / s) ** 1.5
    return _norm(x + thud(90)[: len(x)] * 0.15 * (t > 0.3), 0.6)


def flip() -> np.ndarray:
    s = 0.3
    t = _t(s)
    flutter = 0.5 + 0.5 * np.sin(2 * np.pi * 38 * t)
    x = _bandpass(_noise(s, 33), 2600, 0.8) * flutter * np.sin(np.pi * t / s)
    return _norm(x, 0.6)


def tape() -> np.ndarray:
    s = 0.45
    rng = np.random.default_rng(35)
    base = _bandpass(_noise(s, 36), 3000, 1.0) * 0.4
    cracks = np.zeros(int(SR * s))
    for _ in range(60):
        i = rng.integers(0, len(cracks) - 200)
        cracks[i:i + 120] += rng.uniform(-1, 1, 120) * np.exp(-np.arange(120) / 25)
    t = _t(s)
    return _norm((base + cracks) * np.sin(np.pi * t / s) ** 0.5, 0.6)


def stamp() -> np.ndarray:
    return _norm(_place([(0, thud(80)), (0.005, slap() * 0.7)], 0.55))


def typing() -> np.ndarray:
    rng = np.random.default_rng(41)
    parts = [(i * 0.11 + rng.uniform(0, 0.03), click(50 + i, rng.uniform(2100, 3100)) * rng.uniform(0.6, 1)) for i in range(7)]
    return _norm(_place(parts, 0.85), 0.75)


SOUNDS = {
    "tick": lambda: tick(), "click": lambda: click(), "pop": pop, "blip": lambda: blip(), "blip-up": blip_up, "data": data,
    "whoosh-up": lambda: whoosh(1100, 5300, 0.42), "whoosh-down": lambda: whoosh(5000, 260, 0.26, 5),
    "swipe": lambda: whoosh(2500, 7000, 0.16, 6), "glitch": glitch, "scan": scan, "thud": lambda: thud(), "impact": impact,
    "riser": riser, "shutter": shutter, "slap": slap, "buzz": buzz, "ping": ping, "heartbeat": heartbeat, "knock": knock,
    "marker": lambda: marker(), "scribble": scribble, "paper": paper, "flip": flip, "tape": tape, "stamp": stamp,
    "typing": typing,
}


def write(path: Path, x: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())


def path(root: Path, name: str) -> Path:
    """cache/sfx/v<N>/<name>.wav, made the first time it is asked for."""

    target = root / "cache" / "sfx" / f"v{VERSION}" / f"{name}.wav"
    if not target.is_file():
        write(target, SOUNDS[name]())
    return target


def ensure(root: Path) -> dict[str, Path]:
    return {name: path(root, name) for name in SOUNDS}


# --- where they go ------------------------------------------------------------------------------------------------

def cine_cues(graphic: dict, fps: int, first: bool) -> list[tuple[str, int, float]]:
    """(sound, frame within the shot, volume) for a stickman-film shot: a soft swipe on each new set, the sticker's
    slap, a hit under a title, ticks while a counter counts, the phone (buzz, then a ping per message), a heartbeat at
    the peephole, a riser under the choice, a thud on the end card."""

    out: list[tuple[str, int, float]] = []
    if graphic.get("end"):
        return [("impact", 0, 0.5)]
    if not first and graphic.get("shot") != "pov-phone":
        out.append(("swipe", 0, 0.12))
    if graphic.get("rule"):
        out += [("slap", int(graphic["rule"].get("at", 0)), 0.55), ("thud", int(graphic["rule"].get("at", 0)), 0.35)]
    if graphic.get("title"):
        out.append(("impact", int(graphic.get("titleAt", 0)), 0.35))
    if graphic.get("counter"):
        out += [("tick", 2 + i * 3, 0.25) for i in range(6)]
    if graphic.get("shot") == "pov-phone":
        out.append(("buzz", 0, 0.4))
        messages = (graphic.get("phone") or {}).get("messages") or []
        out += [("ping", round(fps * 0.4) + i * round(fps * 0.9), 0.3) for i in range(len(messages))]
    if graphic.get("shot") == "peephole":
        out.append(("heartbeat", round(fps * 0.2), 0.55))
    if graphic.get("choice"):
        out.append(("riser", 0, 0.35))
    if graphic.get("move") == "shake":
        out.append(("thud", 0, 0.45))
    return out


def mapa_cues(graphic: dict, fps: int) -> list[tuple[str, int, float]]:
    """A whoosh on each camera jump, the marker on every stroke, paper on every tag, a page turn on every flip, typing
    on the tracker, a stamp, a scribble on the end card."""

    out: list[tuple[str, int, float]] = []
    prev, now = graphic.get("prev") or {}, graphic
    if abs(float(prev.get("zoom", now["zoom"])) - float(now["zoom"])) > 1.5 or \
            abs(float(prev.get("lat", now["lat"])) - float(now["lat"])) + abs(float(prev.get("lon", now["lon"])) - float(now["lon"])) > 2:
        out.append(("whoosh-up" if float(prev.get("zoom", 0)) > float(now["zoom"]) else "whoosh-down", 0, 0.35))
    for name in ("circle", "line", "path"):
        if graphic.get(name):
            out.append(("marker", int(graphic[name].get("at", 0)), 0.4))
    for tag in graphic.get("tags") or []:
        out += [("paper", int(tag.get("at", 0)), 0.45), ("tape", int(tag.get("at", 0)) + 4, 0.18)]
    for strip in graphic.get("strips") or []:
        out += [("paper", int(strip.get("at", 0)), 0.4), ("marker", int(strip.get("at", 0)) + round(fps * 0.25), 0.25)]
    for prop in graphic.get("props") or []:
        out.append(("paper", int(prop.get("at", 0)), 0.45))
        if prop.get("flip"):
            out.append(("flip", int(prop.get("at", 0)) + round(fps * 1.1), 0.5))
    if graphic.get("stamp"):
        out.append(("stamp", int(graphic["stamp"].get("at", 0)), 0.7))
    if graphic.get("tracker"):
        out.append(("typing", round(fps * 0.2), 0.3))
    if graphic.get("line", {}) and (graphic.get("line") or {}).get("count"):
        out.append(("data", int(graphic["line"].get("at", 0)) + round(fps * 0.6), 0.2))
    if graphic.get("end"):
        out += [("paper", round(fps * 0.3), 0.45), ("scribble", round(fps * 1.0), 0.5), ("marker", round(fps * 1.4), 0.4)]
    return out
