"""«Lo que dicen estos datos» 9: a paid proxy that does not answer is not a home PC with Tailscale, and what was
written while it was down is not a final result."""

from pipeline.sourcing import stale_note
from pipeline.sourcing.youtube import proxy_down_text


def test_texts():
    paid = proxy_down_text("http://user:pw@gw.dataimpulse.com:823", "gw.dataimpulse.com")
    assert "Tailscale" not in paid and "saldo" in paid and "no responde" in paid
    home = proxy_down_text("http://100.64.0.2:8899", "100.64.0.2")
    assert "Tailscale" in home and "no responde" in home


def test_notes_written_while_the_proxy_was_down_are_not_final():
    assert stale_note(proxy_down_text("http://user:pw@gw.dataimpulse.com:823", "gw.dataimpulse.com"))
    assert stale_note("yt-dlp metadata: el proxy residencial no pudo abrir el túnel (502) en 3 sesiones")
    assert not stale_note("yt:abc: dura 2 min")
