from pipeline.context import RunContext
from pipeline.rights import STRICT, is_strict, owners, write


def row(n, start, seconds, channel):
    return {"shotId": f"s{n:03d}", "start": start, "end": start + seconds, "channel": channel,
            "category": "terceros (YouTube)", "title": f"clip {n}"}


def test_owner_families_and_names():
    assert is_strict("NBC Sports", STRICT) and is_strict("Universal Pictures", STRICT)
    assert not is_strict("El Universal Deportes", STRICT) and not is_strict("Gymnastea", STRICT)
    rows = [row(1, 0, 4, "Olympics"), row(2, 4, 4, "Olympic Games"), row(3, 8, 3, "Paralympic Games"),
            row(4, 20, 4, "Gymnastea")]
    found = owners(rows, STRICT)
    olympics = next(o for o in found if o["channel"] == "Olympics (COI)")
    assert olympics["seconds"] == 11 and olympics["run"] == 11 and olympics["strict"]
    assert len(olympics["channels"]) == 3


def test_report_and_warnings(tmp_path):
    ctx = RunContext.create("t", root=tmp_path, config={"rights": {"high_seconds": 10}})
    ctx.out_dir.mkdir(parents=True)
    rows = [row(i, 5.0 * i, 4, "NBC Olympics") for i in range(4)] + [row(9, 60, 4, "Fan channel")]
    warnings = write(ctx, rows, 120)
    text = (ctx.out_dir / "derechos.md").read_text("utf-8")
    assert warnings and "Olympics (COI)" in warnings[0]
    assert "| alto | Olympics (COI) |" in text and "| bajo | Fan channel |" in text and "0:10 · s002" in text
