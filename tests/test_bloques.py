"""«Material primero», stage 2: the script by blocks from the case file. Model simulated."""

import json

import pytest

from pipeline import bloques
from pipeline.context import RunContext

EXPEDIENTE = {"title": "Top 3 persecuciones", "kind": "top", "minutes": 6, "items": [
    {"n": 1, "name": "Dallas", "whereWhen": "Texas, 2019", "sources": [
        {"id": "orig1", "url": "https://www.youtube.com/watch?v=orig1", "channel": "Dallas PD", "subtitles": "en", "segments": [
            {"start": 0, "end": 120, "type": "secuencia", "seen": "persecución", "said": "", "fact": None, "speaker": None},
            {"start": 130, "end": 140, "type": "declaracion", "seen": "agente", "said": "get out of the car now",
             "fact": None, "speaker": {"name": None, "role": "policía", "confidence": 0.6}},
            {"start": 150, "end": 160, "type": "dato", "seen": "rótulo", "said": "it lasted four hours",
             "fact": "duró 4 horas", "speaker": None}]}]},
    {"n": 2, "name": "Houston", "sources": [
        {"id": "news2", "url": "u2", "channel": "KHOU", "subtitles": "en", "segments": [
            {"start": 5, "end": 20, "type": "declaracion", "seen": "vecina", "said": "I heard the sirens all night",
             "fact": None, "speaker": {"name": "Maria Lopez", "role": "testigo", "confidence": 0.9}}]}]}]}


def ask(system, user):
    assert "[t1] secuencia" in user and "dice: «get out of the car now»" in user and "ORDEN" in system
    return {"criterion": "por duración", "criterion_refs": ["t3"], "blocks": [
        {"type": "tarjeta", "item": 1, "number": 3, "title": "Dallas"},
        {"type": "narrador", "text": "Esta persecución duró cuatro horas.", "refs": ["t3"]},
        {"type": "narrador", "text": "Alcanzó 200 kilómetros por hora.", "refs": []},          # no source: dropped
        {"type": "narrador", "text": "Y entonces, todo cambió.", "refs": []},                   # a connector: stays
        {"type": "secuencia", "ref": "t1", "start": 10, "end": 100},                            # cut to the cap
        {"type": "declaracion", "ref": "t2", "translation": "¡Sal del coche ahora!", "speaker": "Sargento Pérez"},
        {"type": "declaracion", "ref": "t1"},                                                   # footage, not a statement
        {"type": "declaracion", "ref": "t9"}]}                                                  # invented


@pytest.fixture
def ctx(tmp_path):
    (tmp_path / "config.yaml").write_text("content: {max_third_party_seconds: 45}\n")
    c = RunContext.create("top3", root=tmp_path)
    c.write_json("expediente.json", EXPEDIENTE)
    return c


def test_the_blocks_are_made_safe_against_the_case_file(ctx):
    result = bloques.write(ctx, ask=ask)
    kinds = [b["type"] for b in result["blocks"]]
    assert kinds == ["tarjeta", "narrador", "narrador", "secuencia", "declaracion"]
    seq = result["blocks"][3]
    assert (seq["start"], seq["end"]) == (10, 55)                                    # 45 s cap of the channel
    statement = result["blocks"][4]
    assert statement["said"] == "get out of the car now" and statement["speaker"] is None   # never the model's «Pérez»
    assert statement["role"] == "policía" and statement["translation"] == "¡Sal del coche ahora!"
    assert any("200 kilómetros" in n for n in result["notes"]) and result["criterionRefs"] == ["t3"]
    est = result["estimate"]
    assert est["voiceSeconds"] == 10 and est["footageSeconds"] == 45 and est["downloadMB"] == round(55 * bloques.MB_PER_SECOND)


def test_a_top_without_a_justified_order_says_so():
    index = bloques.segment_index(EXPEDIENTE)
    assert "no se justifica" in bloques.check({"criterion": "porque sí", "blocks": []}, index, 45)["notes"][0]


def test_the_owner_removes_or_changes_a_statement_before_spending(ctx):
    bloques.write(ctx, ask=ask)
    changed = bloques.edit(ctx, 4, "cambiar", "t4")
    assert changed["blocks"][4]["speaker"] == "Maria Lopez" and changed["blocks"][4]["said"].startswith("I heard")
    with pytest.raises(ValueError, match="no es una declaración"):
        bloques.edit(ctx, 4, "cambiar", "t1")
    removed = bloques.edit(ctx, 2, "quitar")
    assert len(removed["blocks"]) == 4 and removed["edited"]
    assert json.loads((ctx.work_dir / bloques.OUTPUT).read_text())["estimate"]["voiceSeconds"] == 15
