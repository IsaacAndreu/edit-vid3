import json

from pipeline import ahorro, gasto


def test_reuse_is_priced_with_what_the_same_thing_cost(tmp_path):
    (tmp_path / "config.yaml").write_text("{}\n")
    work = tmp_path / "work" / "v1"
    work.mkdir(parents=True)
    (tmp_path / "out" / "v1").mkdir(parents=True)
    entries = [{"stage": "judge", "provider": "openai", "usd": 0.001, "at": "2026-11-05T10:00:00"} for _ in range(10)]
    entries.append({"stage": "voz", "provider": "genaipro", "usd": 0.2, "at": "2026-11-05T10:00:00", "details": {"chars": 10000}})
    (work / "costs.json").write_text(json.dumps({"entries": entries}))
    for _ in range(30):
        ahorro.record(work, "judge")
    ahorro.record(work, "voice", 5000)
    (work / ".stages").mkdir()
    (work / ".stages" / "render.json").write_text(json.dumps({"seconds": 600}))
    report = gasto.report(tmp_path)
    s = report["savings"]
    assert s["verdicts"] == 30 and abs(s["verdictsUsd"] - 0.03) < 1e-9 and abs(s["voiceUsd"] - 0.1) < 1e-9
    assert abs(s["usd"] - 0.13) < 1e-9 and 0 < s["share"] < 1
    row = next(r for r in report["videos"] if r["slug"] == "v1")
    assert row["workSeconds"] == 600 and abs(row["savedUsd"] - 0.13) < 1e-6


def test_a_resumed_narration_does_not_bill_the_pieces_already_made(tmp_path, monkeypatch):
    import hashlib

    from pipeline import tts

    class Api:
        def __init__(self, *a):
            pass

        def create(self, part, voice):
            raise AssertionError("a piece already made was generated (and paid) again")

    monkeypatch.setattr(tts, "GenAIPro", Api)
    text = "uno " * 50
    monkeypatch.setattr(tts, "pieces", lambda _text, _n: [text])
    voice = {"voice_id": "v", "model_id": "m"}
    settings = json.dumps({k: voice.get(k) for k in ("voice_id", *tts.DEFAULTS)}, sort_keys=True)
    work = tmp_path / ".voz-trozos"
    work.mkdir()
    (work / f"{hashlib.sha1((settings + text).encode()).hexdigest()[:16]}.mp3").write_bytes(b"y" * 10)
    try:
        result = tts.generate("k", "x", voice, tmp_path / "voz.mp3", log=lambda *_: None)
    except tts.TTSError:
        return
    assert result["reusedChars"] == len(text) and result["paidChars"] == 0


def test_narrations_recorded_at_zero_are_priced_per_character(tmp_path):
    """The voices never carried a price: every narration showed 0.00 $ (GenAIPro: 0.022 $ per 1,000 characters)."""
    from types import SimpleNamespace

    from pipeline import tts

    (tmp_path / "config.yaml").write_text("{}\n")
    work = tmp_path / "work" / "v1"
    work.mkdir(parents=True)
    (tmp_path / "out" / "v1").mkdir(parents=True)
    entries = [{"stage": "voz", "provider": "genaipro", "usd": 0, "at": "2026-11-05T10:00:00", "details": {"chars": 14000}},
               {"stage": "doblaje", "provider": "genaipro", "usd": 0.1, "at": "2026-11-05T11:00:00", "details": {"chars": 9000}}]
    (work / "costs.json").write_text(json.dumps({"entries": entries}))
    row = next(r for r in gasto.report(tmp_path)["videos"] if r["slug"] == "v1")
    assert abs(row["usd"] - (0.308 + 0.1)) < 1e-6                     # an entry with its own price keeps it
    ctx = SimpleNamespace(section=lambda name: {"usd_per_1k_chars": 0.03} if name == "tts" else {})
    assert tts.usd_per_1k_chars(ctx) == 0.03
    assert tts.usd_per_1k_chars(ctx, {"usd_per_1k_chars": 0.01}) == 0.01
    assert tts.usd_per_1k_chars(SimpleNamespace(section=lambda name: {})) == 0.022
