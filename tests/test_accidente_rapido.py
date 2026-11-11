"""Shorts de última hora (pipeline/accidente_rapido.py): candidatos, aeropuertos, guion y storyboard, sin red ni IA."""

from datetime import datetime

from pipeline import accidente_rapido as ar

ROWS = [{"ident": "KPBI", "gps_code": "KPBI", "icao_code": "KPBI", "iata_code": "PBI", "name": "Aeropuerto de prueba",
         "municipality": "West Palm Beach", "iso_country": "US", "longitude_deg": "-80.0956", "latitude_deg": "26.6832"}]


def _story(name="Avion Palm", channels=2, speed=5000, title="Avión se estrella cerca del aeropuerto"):
    return {"name": name, "channels": channels, "speed": speed,
            "videos": [{"title": title, "channel": "Canal A"}, {"title": title, "channel": "Canal B"}]}


def test_candidates_need_aviation_several_channels_and_speed():
    assert ar.candidates([_story()], set(), 2, 2000)
    assert not ar.candidates([_story(channels=1)], set(), 2, 2000)
    assert not ar.candidates([_story(speed=100)], set(), 2, 2000)
    assert not ar.candidates([_story(title="Partido de fútbol")], set(), 2, 2000)
    assert not ar.candidates([_story()], {ar._key(_story())}, 2, 2000)


def test_airport_by_icao_or_iata():
    assert ar.find_airport(ROWS, "kpbi")["lat"] == 26.6832
    assert ar.find_airport(ROWS, "PBI")["city"] == "West Palm Beach"
    assert ar.find_airport(ROWS, "XXXX") is None and ar.find_airport(ROWS, None) is None


def test_storyboard_is_vertical_and_anchored_to_the_script():
    info = {"title": "T", "model": "bizjet", "aircraft": "reactor",
            "segments": {"gancho": "Uno dos tres cuatro cinco.", "lugar": "Seis siete ocho nueve diez.",
                         "avion": "Once doce trece catorce.", "datos": "Quince dieciseis diecisiete.", "cierre": "Fin del vídeo de prueba."},
            "facts": [{"text": "x", "status": "confirmed", "sources": ["Canal A", "Canal B"]}]}
    out = ar.storyboard("s", info, ar.find_airport(ROWS, "KPBI"), datetime(2026, 1, 1, 12, 0))
    assert out["vertical"] is True
    types = [s["type"] for s in out["storyboard"]["scenes"]]
    assert types == ["atlas-globe", "atlas-relief-map", "atlas-aircraft", "atlas-known", "atlas-statement"]
    assert out["storyboard"]["scenes"][1]["start"] == {"say": "Seis siete ocho nueve"}
    assert ar.script_of(info).startswith("Uno dos tres")
