"""Ilustraciones vectoriales de Atlas (fase 6): SVG planos con un id por capa y clases de color.

Clases (las pinta remotion/atlas/scenes/diagram.tsx con los colores del tema):
  ink    trazo de tinta          paper  relleno de papel claro     earth  relleno tierra
  glass  cristal azul claro      body   figura humana gris azulado  amber  ámbar (oxígeno)
  grey   gris cálido             seat   asiento                     red    rojo de aviso
  line   sólo trazo, sin relleno

Uso: python3 scripts/atlas-diagrams/build.py  → public/atlas-diagrams/*.svg
Cada SVG documenta sus capas en un comentario al principio; sustituye el dibujo por el tuyo manteniendo los ids.
"""
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "public" / "atlas-diagrams"
OUT.mkdir(parents=True, exist_ok=True)


def svg(name: str, w: int, h: int, layers: dict[str, str], body: str) -> None:
    doc = "\n".join(f"  {k}: {v}" for k, v in layers.items())
    (OUT / f"{name}.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">\n'
        f"<!-- Capas (ids) de {name}:\n{doc}\n-->\n{body}\n</svg>\n"
    )


# ── Bimotor visto desde arriba, morro a la derecha ──────────────────────────────────────────────────
svg("plane-twin-top", 1300, 860, {
    "fuselage": "fuselaje", "wings": "alas", "tail": "estabilizadores",
    "engine-top": "motor del ala de arriba", "engine-bottom": "motor del ala de abajo",
}, """
<g id="wings" class="earth ink">
  <path d="M600,388 L520,40 L620,40 L820,388 Z"/>
  <path d="M600,472 L520,820 L620,820 L820,472 Z"/>
</g>
<g id="tail" class="earth ink">
  <path d="M250,392 L180,250 L225,250 L345,392 Z"/>
  <path d="M250,468 L180,610 L225,610 L345,468 Z"/>
</g>
<path id="fuselage" class="paper ink" d="M190,430 C190,410 215,390 270,388 L1050,388 C1135,388 1180,410 1190,430 C1180,450 1135,472 1050,472 L270,472 C215,470 190,450 190,430 Z"/>
<rect id="engine-top" class="grey ink" x="640" y="200" width="120" height="48" rx="24"/>
<rect id="engine-bottom" class="grey ink" x="640" y="612" width="120" height="48" rx="24"/>
""")


def jet(seats: bool) -> str:
    """Avión de fuselaje ancho visto desde arriba, morro a la izquierda."""
    parts = ["""
<g id="wings" class="earth ink">
  <path d="M780,282 L1060,30 L1130,30 L960,282 Z"/>
  <path d="M780,478 L1060,730 L1130,730 L960,478 Z"/>
</g>
<g id="tail" class="earth ink">
  <path d="M1470,290 L1560,200 L1600,200 L1560,290 Z"/>
  <path d="M1470,470 L1560,560 L1600,560 L1560,470 Z"/>
</g>
<path id="fuselage" class="paper ink" d="M40,380 C60,330 120,282 220,282 L1480,282 C1530,282 1560,300 1575,330 L1640,380 L1575,430 C1560,460 1530,478 1480,478 L220,478 C120,478 60,430 40,380 Z"/>
<g id="crew" class="red">
  <circle cx="125" cy="362" r="11"/><circle cx="125" cy="398" r="11"/><circle cx="165" cy="362" r="11"/><circle cx="165" cy="398" r="11"/>
</g>"""]
    if seats:
        rects = []
        for col in range(34):
            x = 320 + col * 33
            for row, y0 in enumerate((302, 360, 418)):
                for k in range(3 if row != 1 else 2):
                    rects.append(f'<rect x="{x}" y="{y0 + k * 13}" width="20" height="10" rx="2"/>')
        parts.append(f'<g id="seats" class="seat-blue">{"".join(rects)}</g>')
    else:
        boxes = "".join(f'<rect x="{300 + i * 133}" y="304" width="118" height="152"/>' for i in range(9))
        parts.append(f'<g id="cargo" class="earth ink">{boxes}</g>')
    return "\n".join(parts)


svg("widebody-cabin", 1680, 760, {"fuselage": "fuselaje", "wings": "alas", "tail": "cola",
                                  "crew": "tripulación (puntos rojos)", "seats": "asientos de pasajeros"}, jet(True))
svg("cargo-cabin", 1680, 760, {"fuselage": "fuselaje", "wings": "alas", "tail": "cola",
                               "crew": "tripulación (puntos rojos)", "cargo": "contenedores de carga"}, jet(False))

# ── Cabina de mando vista desde arriba ─────────────────────────────────────────────────────────────────
svg("cockpit-top", 1000, 900, {
    "nose": "contorno del morro", "ws-left": "parabrisas izquierdo", "ws-right": "parabrisas derecho",
    "glareshield": "panel de instrumentos", "pedestal": "pedestal central",
    "seat-captain": "asiento y piloto (capitán)", "seat-copilot": "asiento y piloto (copiloto)",
    "belt": "cinturón del copiloto", "debris": "trayectorias de lo que sale por el hueco",
}, """
<path id="nose" class="paper ink" d="M150,880 L150,420 C150,190 330,40 500,40 C670,40 850,190 850,420 L850,880"/>
<path id="ws-left" class="glass ink" d="M220,330 C260,230 340,160 470,130 L470,250 C380,270 330,300 300,345 Z"/>
<path id="ws-right" class="glass ink" d="M780,330 C740,230 660,160 530,130 L530,250 C620,270 670,300 700,345 Z"/>
<path id="glareshield" class="grey ink" d="M200,385 C350,335 650,335 800,385 L795,410 C650,365 350,365 205,410 Z"/>
<rect id="pedestal" class="paper ink" x="440" y="420" width="120" height="70"/>
<g id="seat-captain">
  <rect class="seat ink" x="230" y="500" width="120" height="140" rx="16"/>
  <ellipse class="body ink" cx="290" cy="540" rx="62" ry="22"/>
  <circle class="body ink" cx="290" cy="520" r="24"/>
</g>
<g id="seat-copilot">
  <rect class="seat ink" x="650" y="500" width="120" height="140" rx="16"/>
  <ellipse class="body ink" cx="710" cy="540" rx="62" ry="22"/>
  <circle class="body ink" cx="710" cy="520" r="24"/>
</g>
<g id="belt" class="body-dark">
  <rect x="650" y="582" width="120" height="12"/><rect x="700" y="575" width="20" height="26" class="paper ink"/>
</g>
<g id="debris" class="line dash-ink">
  <path d="M700,560 L600,250"/><path d="M710,560 L560,780"/><path d="M720,560 L780,180"/><path d="M690,560 L470,690"/><path d="M730,560 L860,820"/>
</g>
""")

# ── Pasajero con la mascarilla de oxígeno química ──────────────────────────────────────────────────────
svg("seat-oxygen", 1100, 820, {
    "bin": "maletero superior", "psu": "panel bajo el maletero", "generator": "generador químico de oxígeno",
    "door": "trampilla (gira al caer las mascarillas)", "tube": "tubo de oxígeno", "mask-hanging": "mascarilla colgando",
    "mask-face": "mascarilla puesta", "flow": "puntos de oxígeno por el tubo", "person": "pasajero sentado", "seat": "asiento",
    "floor": "suelo",
}, """
<rect id="bin" class="paper ink" x="60" y="30" width="560" height="90" rx="14"/>
<line class="line" x1="90" y1="70" x2="590" y2="70" style="stroke-opacity:0.35"/>
<g id="psu"><rect class="paper ink" x="190" y="120" width="430" height="44"/></g>
<rect id="generator" class="amber ink" x="215" y="128" width="170" height="26" rx="13"/>
<line id="door" class="line" x1="620" y1="164" x2="590" y2="330" style="transform-box:view-box;transform-origin:620px 164px"/>
<path id="tube" class="line" d="M455,150 C452,240 458,320 445,400" style="stroke:#3D7A5C"/>
<g id="flow" class="good-dots"><circle cx="455" cy="200" r="6"/><circle cx="454" cy="260" r="6"/><circle cx="452" cy="320" r="6"/></g>
<g id="mask-hanging"><path class="amber ink" d="M425,400 L465,400 L470,440 C460,455 430,455 420,440 Z"/></g>
<rect id="seat" class="seat ink" x="300" y="300" width="50" height="320" rx="20"/>
<path class="seat ink" d="M310,600 L520,600 L520,630 L310,630 Z"/>
<line class="line" x1="340" y1="630" x2="340" y2="780"/><line class="line" x1="500" y1="630" x2="500" y2="780"/>
<g id="person" class="body ink">
  <circle cx="400" cy="380" r="44"/>
  <path d="M360,430 C350,500 350,560 360,610 L540,610 L540,570 L440,560 C450,520 455,470 440,430 Z"/>
  <path d="M520,570 L600,570 L620,760 L580,760 L565,610 Z"/>
  <path d="M575,760 L640,760 L640,780 L575,780 Z"/>
  <path d="M430,450 C470,470 480,470 470,430" class="body ink"/>
</g>
<g id="mask-face"><path class="amber ink" d="M432,372 L470,366 L478,404 C468,418 446,418 436,406 Z"/></g>
<line id="floor" class="line" x1="40" y1="780" x2="760" y2="780"/>
""")

# ── Botellas de oxígeno ────────────────────────────────────────────────────────────────────────────────
bottles = "".join(
    f'<g id="bottle-{i + 1}"><rect class="good ink" x="{60 + i * 150}" y="120" width="100" height="420" rx="40"/>'
    f'<rect class="grey ink" x="{90 + i * 150}" y="80" width="40" height="50" rx="6"/></g>'
    for i in range(6)
)
svg("oxygen-bottles", 1000, 600, {f"bottle-{i}": f"botella {i}" for i in range(1, 7)}, bottles)

# ── Silueta de avión de perfil ─────────────────────────────────────────────────────────────────────────
svg("plane-side", 1000, 400, {"plane": "avión de perfil, morro a la derecha"}, """
<g id="plane" class="paper ink" transform="scale(10)">
  <path d="M5 22 C5 18 10 17 20 17 L82 17 C90 17 96 19 98 21 C96 23 90 24.5 82 24.5 L20 24.5 C10 24.5 5 23.5 5 22 Z M8 18 L3 5 L11 5 L23 17 Z M44 21.5 L63 21.5 L51 31 L41 31 Z" style="stroke-width:0.3"/>
</g>
""")
print("\n".join(sorted(p.name for p in OUT.glob("*.svg"))))
