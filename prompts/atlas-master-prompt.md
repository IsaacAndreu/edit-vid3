# Prompt maestro — estilo "Atlas" (reutilizable)

Extraído del análisis fotograma a fotograma de `atlasprueba.mp4` (8:40, 960×540, 24 fps).
Este archivo es **independiente del tema**: define el sistema visual, la librería de escenas y
las reglas de animación. El contenido de cada vídeo va en un storyboard aparte
(ver `atlas-tibet-storyboard.md` como ejemplo completo).

Uso: pega el bloque "PROMPT" entero y, debajo, el storyboard del vídeo que quieras producir.

---

## PROMPT

Eres un motion designer e ingeniero de Remotion. Vas a construir, dentro de este repositorio
(Remotion + React + TypeScript, composición `YoutubeVideo`, escenas registradas en
`templates/registry.ts` y dirigidas por un JSON de props), un sistema de plantillas llamado
**Atlas** y a renderizar con él el storyboard que te doy al final.

Todo debe ser **dirigido por datos**: ningún texto, coordenada, cifra o color del storyboard
puede quedar escrito dentro de un componente. Un vídeo nuevo = un JSON nuevo, cero código nuevo
(salvo ilustraciones SVG específicas, que se añaden como assets).

### 1. Formato

- 1920×1080, 30 fps (la referencia es 24 fps; si se quiere clavar el tacto, renderizar a 24).
- Vídeo 100 % motion graphics: sin metraje real, sin fotos, sin stock, sin avatar.
- Narración en off continua de principio a fin; el visual nunca queda quieto más de ~2 s.
- **No hay cortes secos.** Cada cambio de escena es un fundido cruzado de 0,4–0,6 s o un
  movimiento de cámara continuo (zoom/paneo/inclinación) que convierte una escena en la siguiente.

### 2. Tokens de diseño (`templates/atlas/theme.ts`)

Dos temas; el tema claro es el principal, el oscuro sólo para el gancho inicial y el cierre.

| Token | Claro ("papel") | Oscuro ("noche") |
|---|---|---|
| Fondo | `#E7DFC9` | `#192733` |
| Borde de viñeta | `#C7BDA7` | `#101A22` |
| Tinta (texto/trazo) | `#2A2118` | `#EDE6D3` |
| Tinta suave | `#6F6657` | `#8FA0AB` |
| Tierra del mapa | `#D4C6AB` | `#8FA3AD` |
| Región destacada (relleno) | `#AE8C5F` | rojo translúcido |
| Mar | `#A9C3D0` → `#91A5A8` en profundidad | `#22384A` |
| Acento peligro | `#C8402F` | `#E0A84A` (ámbar) |
| Acento dato | `#2F5673` (azul marino) | `#EDE6D3` |
| Acento positivo | `#3D7A5C` (verde) | — |
| Tarjeta | relleno `#EFE8D8`, doble filete tinta 1 px + 1 px | igual, opacidad 85 % |

(Fondo, viñeta, noche, región y mar están muestreados del vídeo; los acentos son aproximados.)

Acabado global, aplicado como capa sobre toda la composición:
- Textura de papel muy sutil + grano fino animado (opacidad ~4 %).
- Viñeta ovalada suave hacia `Borde de viñeta`.
- Los textos sobre mapa llevan un halo del color del fondo (stroke 3–4 px detrás) para leerse.

Tipografía (tres familias, nunca más):
- **Display serif** de alto contraste, peso semibold, tracking apretado, para titulares y cifras.
  Aproximación libre: *Fraunces* (opsz alto) o *Playfair Display*.
- **La misma serif en cursiva y en color de acento** para la palabra clave del titular. Ésta es
  la firma del estilo: `Clear-headed for` (tinta) + `a minute or less` (cursiva roja).
  Una sola frase resaltada por titular; rojo = peligro, azul = concepto, verde = buena noticia.
- **Monoespaciada en mayúsculas** con tracking amplio (≈0,18 em), tamaño pequeño, para
  antetítulos, etiquetas de ejes, anotaciones y notas de fuente. Aproximación: *IBM Plex Mono*.
- Topónimos de ciudades: serif normal pequeña con punto. Nombres de regiones/países:
  versales muy espaciadas, tinta suave.

### 3. Capas persistentes (HUD)

- **Marca**: arriba a la izquierda, icono + nombre en mono mayúsculas, tamaño mínimo, siempre
  visible. Parametrizable (`brand.name`, `brand.icon`). En la referencia: una manecilla
  tipográfica (☞) y la palabra del canal.
- **Indicador de capítulos**: arriba a la derecha, números romanos `I II III IV V`. Los ya
  vistos en tinta, el actual en rojo con subrayado y una palabra-etiqueta en cursiva debajo
  (`Ground`, `Pressure`…), los pendientes en gris. Aparece tras la primera cortinilla y
  desaparece en el resumen final.

### 4. Librería de escenas (`templates/atlas/*`)

Cada una es un componente registrado con clave estable. Todas reciben `beats[]`: una lista de
revelados con `at` (segundos relativos a la escena) para sincronizar con la voz.

**Mapas**
1. `atlas-globe` — globo ortográfico que rota hasta centrar una región; región resaltada;
   rutas de círculo máximo (discontinua = teórica, continua = real) que se dibujan con un avión
   en la punta; leyenda en tarjeta; titular superpuesto opcional.
2. `atlas-relief-map` — mapa de relieve sombreado tono pergamino con mares azul lavado.
   Capas declarativas: `regions` (contorno rojo + relleno), `routes` (se trazan progresivamente,
   con etiqueta de aerovía), `points` (ciudad/aeropuerto con etiqueta y dato opcional),
   `arrows`, `labels`, `overlayShape` (silueta de otro territorio a la misma escala para
   comparar tamaño), `movingIcon` (avión que recorre una ruta), `graticule` (rejilla de
   1°×1° con número por celda y celdas que se colorean por umbral), y `camera` con keyframes
   `{center, zoom, at}` para paneos y zooms lentos y continuos.
3. `atlas-terrain-3d` — el mismo mapa que se inclina de cenital a oblicuo y se extruye en un
   bloque 3D con el relieve exagerado (siempre rotulado: `HEIGHTS ×30`). Admite umbral
   coloreado (`ABOVE 4 KM`), etiquetas de cordilleras con línea guía, y un avión con línea
   vertical de altitud hasta el suelo.
4. `atlas-valley-flight` — vista 3D rasante de un valle/aeropuerto con trayectorias
   comparadas (línea azul = caso normal, roja discontinua = caso de fallo), cotas de picos
   y leyenda inferior. Es la escena más cara: úsala una vez por vídeo como clímax visual.

**Gráficos**
5. `atlas-elevation-profile` — corte de terreno relleno de color tierra sobre ejes en
   pies/km; línea de vuelo que se dibuja con un avión en la punta; líneas de umbral
   discontinuas; línea roja escalonada ("altitud mínima segura"); bandas sombreadas;
   tramos resaltados en rojo donde la trayectoria viola el umbral. Permite sustituir el
   terreno en vivo (mar abierto → meseta) manteniendo la misma curva: el contraste es el argumento.
6. `atlas-bar-compare` — 2–4 barras que crecen desde la línea base con la cifra contando;
   marco fantasma discontinuo para "2 × el otro"; banda de umbral opcional y lista lateral de etiquetas.
7. `atlas-dial` — esfera de reloj con sector que se llena o se vacía y contador debajo
   (`43 SEC`, `~20 minutes saved`). Rojo para cuenta atrás, verde para ahorro.
8. `atlas-dot-density` — 2–3 cajas con puntos que se van eliminando mientras el porcentaje
   baja (100 % → 70 % → 64 %).
9. `atlas-runway-compare` — dos pistas vistas desde arriba, un avión en cada una, marca de
   despegue que cae más lejos en la segunda.

**Texto y estructura**
10. `atlas-title-overlay` — titular grande sobre la escena anterior atenuada.
11. `atlas-agenda` — título + fila de números romanos que aparecen uno a uno + dos líneas
    de promesa + adelanto del final.
12. `atlas-chapter-card` — filete — numeral romano — filete, y debajo el título con la
    palabra clave en cursiva azul. 4–5 s, entra y sale por fundido.
13. `atlas-statement` — antetítulo mono + titular con resaltado, lienzo vacío debajo
    para que entren tarjetas o un gráfico.
14. `atlas-card-row` — 3–5 tarjetas numeradas que entran de izquierda a derecha, una por frase.
15. `atlas-checklist` — casillas que se marcan con trazo verde, título serif y subtítulo mono.
16. `atlas-diagram` — ilustración esquemática vectorial (trazo tinta, rellenos planos del
    tema) con partes que cambian de estado y llamadas con línea guía. Recibe un SVG con
    ids de capa y una lista de `callouts`/`states`. Estilo: línea uniforme, sin degradados,
    vista lateral o cenital, figuras humanas simplificadas sin rostro.
17. `atlas-recap` — titular + una tarjeta por capítulo (numeral, etiqueta, frase de 4 palabras).
18. `atlas-cta` — tarjeta con pregunta al espectador + botón SUBSCRIBE rojo que pasa a
    SUBSCRIBED oscuro. Versión intermedia (mitad del vídeo) y versión de cierre en tema noche.

**Superposiciones** (se montan sobre cualquier escena vía `overlays[]`)
- `info-card`: antetítulo mono con filete, titular serif, subtítulo en versalitas azules.
  Para fechas, nombres, citas y cifras. Siempre en una esquina libre.
- `stamp`: sello rojo de caucho, texto mono, girado −4°, entra con golpe de escala.
- `counter`: cifra que cuenta hacia su valor final dentro de una tarjeta.
- `legend`, `source-note` (mono diminuta al pie: fuente o "ILLUSTRATIVE").

### 5. Reglas de animación

- **Un revelado por frase de la narración.** Nada aparece antes de que la voz lo nombre;
  cada elemento entra justo cuando se menciona (±0,2 s).
- Las líneas se **dibujan**; las cifras **cuentan**; las barras **crecen**; el texto entra por
  opacidad con un ligero desenfoque. Nada rebota ni hace overshoot, salvo el sello.
- Easing suave (ease-in-out cúbico), duraciones 0,4–0,8 s.
- La cámara de los mapas deriva siempre un poco (zoom lento 2–4 % por plano) aunque no pase nada.
- Las escenas se construyen por acumulación y terminan llenas; el siguiente fundido las limpia.
- Los elementos anteriores se atenúan (opacidad 40–50 %) cuando entra el foco nuevo.

### 6. Reglas editoriales (son parte del estilo)

- Cada gráfico lleva antetítulo que dice qué se ve y, si procede, nota de honestidad:
  `TRUE SCALE`, `HEIGHTS ×30`, `PLANE NOT TO SCALE`, `ILLUSTRATIVE`, `SIMPLIFIED`, fuente y año.
- Texto en pantalla mínimo: etiquetas de 2–6 palabras, nunca frases de la narración enteras.
- Estructura narrativa fija: gancho con imagen fuerte (0:00–0:15) → pregunta-título →
  contexto (≈30 s) → agenda numerada → N capítulos con cortinilla → CTA breve a mitad →
  giro final (la excepción a la regla) → resumen en tarjetas → frase-tesis → CTA de cierre.
- Cada capítulo sigue el patrón: afirmación → gráfico que la prueba → caso real con fecha y
  nombre (tarjeta) → consecuencia.

### 7. Audio

- Voz en off continua, masterizada a −16 LUFS.
- Música ambiental discreta por debajo, que queda sola unos 20 s en el cierre.
- Sin efectos sonoros evidentes.

### 8. Entregables

1. `templates/atlas/` con tema, capas HUD, escenas y superposiciones, registradas en `registry.ts`.
2. Tipos del storyboard (`AtlasScene`, `Beat`, `Overlay`) en `templates/types.ts`.
3. `storyboards/<slug>.json` generado a partir del storyboard de abajo, con `durationInFrames`
   calculados desde los tiempos de la narración (Whisper, ya disponible en `pipeline/transcribe.py`).
4. Un render de prueba de 20 s por tipo de escena antes del render completo.
5. Datos geográficos: Natural Earth (costas, países) y un DEM público (SRTM/ETOPO) para relieve,
   perfiles y rejilla; guardar los derivados en `public/atlas-data/` para reutilizarlos.

Empieza por el tema y las capas globales, sigue con `atlas-relief-map` y
`atlas-elevation-profile` (cubren más de la mitad del metraje) y deja `atlas-valley-flight`
para el final.

### STORYBOARD

<pegar aquí el storyboard del vídeo>
