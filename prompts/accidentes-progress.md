# Progreso: reconstrucciones de accidentes aéreos

Plan: `prompts/accidentes-plan.md`. Caso de prueba: **US Airways 1549** (amerizaje en el Hudson, 15 ene 2009; sin
fallecidos). Datos: expediente público de la NTSB DCA09MA026 (tabla del FDR, dominio público) e informe AAR-10/03.

## A0 — Datos y esquema ✅
- `scripts/accidentes/vuelo.py`: tabla del FDR → `public/accidentes/<caso>/vuelo.json` (1 muestra/s, posición
  interpolada entre las fijas de 4 s, altitud de presión + corrección del altímetro, rumbo, N1, velocidad, flaps…).
- Caso `scripts/accidentes/casos/us1549.json`: fuentes, corrección (293 ft por 30,24 inHg, AAR p. 23), 12 hechos con
  su página y 5 cifras del informe.
- Validador (`check`): tiempos crecientes, saltos de altitud/posición imposibles, velocidades fuera de rango, hechos
  sin fuente. **Detectó** dos muestras de 16380 ft al cruzar el cero (complemento a dos de 14 bits: −4 ft) y la
  velocidad 511,875 kt = sin lectura en tierra; ambos se tratan y se dicen en `notes`.
- Región `nueva-york` (Mercator, z14): agua de los polígonos de mar de OSM (`@geo-maps/earth-seas-100m`, ODbL) más los
  ríos conectados por altura; la costa de Natural Earth 50m no servía a escala de ciudad.
- Terreno bajo la trayectoria: `npm run atlas:data -- flight-ground <vuelo.json>` (Terrarium, mediana de 5).
- Esquema: `flightPlaybackSchema` (reloj del vuelo `from`→`to` a `rate`), hitos, instrumentos; 4 escenas nuevas.
- **Puerta superada**: la trayectoria sale limpia del FDR (`docs/accidentes/a1-trayectoria.jpg`).

## A1 — Trayectoria en el mapa ✅  (`flight` en atlas-relief-map)
Estela que crece, avión orientado por la trayectoria, hitos a su hora, instrumentos (hora, altitud, velocidad, N1 en
barras), `follow` y `trail: full`. `docs/accidentes/a1-trayectoria.jpg`.

## A2 — Perfiles ✅  (atlas-flight-profile)
Altitud con el terreno debajo, N1 de los dos motores, velocidad con líneas de referencia (300 kt).
`docs/accidentes/a2-altitud.jpg`, `a2-motores.jpg`, `a2-velocidad.jpg`.

## A3 — Vuelo en 3D ✅  (`flight` en atlas-terrain-3d)
Trayectoria en el aire con la misma exageración, sombra en el suelo, cortina de líneas, avión orientado, hitos.
Bloque `hudson-1549` con la textura de la región (`build-terrain … [region]`). `docs/accidentes/a3-vuelo-3d.jpg`.

## A4 — Cabina y avión ✅  (atlas-cockpit, atlas-aircraft)
Frases del CVR/ATC a su hora con su `ref` (traducidas y dicho en `sourceNote`); instrumentos del FDR. Siluetas
genéricas `narrowbody` y `bizjet`, vista superior y lateral, piezas resaltables. `a4-cabina.jpg`, `a4-avion.jpg`.

## A5 — «Lo que se sabe» y vertical ✅  (atlas-known, AtlasShort)
Tarjetas confirmado/sin confirmar/se desconoce con fuente y fecha. Composición `AtlasShort` 1080×1920 (vídeo 16:9
entero en el centro + `meta.short`). `a5-lo-que-se-sabe.jpg`, `a5-short.jpg`.
**Límite**: en vertical los textos del 16:9 quedan al 56 %; un diseño vertical propio de cada escena sería otra fase.

## A6 — Vídeo de referencia ✅ (falta la revisión humana)
`materiales/Hudson1549/{guion.txt, escenas.json}`: 9 escenas, ~90 s, todas las cifras del informe o del FDR.
`python main.py --atlas-guion Hudson1549` → `out/hudson1549/atlas.mp4`. Hoja de contactos en
`docs/accidentes/a6-hoja.jpg`. En el cloud, sin voz (tiempos estimados); con la voz del programa los anclajes se
recalculan. **Antes de publicar**: una persona revisa las cifras y las traducciones de las frases.

## A7 — Producción ✅
- Canal `canales/accidentes-aereos.yaml` (verificación de datos que bloquea la voz, radar de noticias de accidentes).
- `--atlas-guion` genera los vuelos: `{"kind": "flight", "case", "table": URL del FDR}` (descarga, `vuelo.py`,
  terreno) y regiones/bloques de ciudad (`margin`, `water`, `region` del bloque 3D).
- Catálogo para la IA: sección «Vuelos reales» en `docs/atlas-authoring.md`.
- Tests: `tests/test_accidentes.py` (conversión, cruce del cero, validador, datos del caso, pipeline).

## B — De cerca ✅  (atlas-flight-cam, atlas-pfd)
- `remotion/atlas/flight/aircraft3d.ts`: bimotor de pasillo único y reactor ejecutivo construidos en código (fuselaje
  torneado, alas con flecha y diedro, estabilizadores, motores), sin modelos de terceros ni libreas.
- Orientación con el cabeceo, el alabeo y el rumbo del FDR. El rumbo es magnético: se le suma la diferencia mediana
  entre la trayectoria y el rumbo en vuelo, calculada de los propios datos (incluye la deriva por viento).
- Cámaras `chase`, `side`, `orbit`, `ground` (teleobjetivo) y `cockpit` (el horizonte se inclina con el alabeo; marco
  genérico de parabrisas); transiciones de 1,6 s. Cúpula de cielo y niebla por distancia para que no se vea el borde
  del bloque (`hudson-cerca`, 27×24 km, z14, textura de la región).
- PFD genérico (`remotion/atlas/flight/pfd.tsx`): horizonte artificial, arco de alabeo, cintas de velocidad y altitud,
  rumbo; en una esquina de la vista 3D o a pantalla grande con las frases del informe (`atlas-pfd`).
- Fotogramas: `docs/accidentes/b-persecucion.jpg`, `b-lateral.jpg`, `b-cabina.jpg`, `b-desde-el-suelo.jpg`, `b-pfd.jpg`.
- **Límites**: ~10 s por fotograma en el cloud (render de software); sin edificios (solo relieve); el avión no lleva
  librea ni detalle de fabricante; la cabina es un marco genérico, no el interior de un modelo concreto.

### B2 — Personalización ✅
- Cinco tipos genéricos: pasillo único, fuselaje ancho, regional (motores en la cola, cola en T), turbohélice (ala
  alta, hélices como disco), ejecutivo. Pinturas genéricas (`LIVERIES` en theme.ts) y matrícula pintada.
- Panel de cabina (`cockpitPanel`): PFD de los dos pilotos y N1 en esfera, con los datos del instante.
- Fotogramas: `docs/accidentes/b2-*.jpg`. Pendiente: edificios (necesita OSM vía Overpass, host no permitido aún).

## Pendiente / decisiones para el usuario
- Elegir los siguientes casos (informes con tabla del FDR pública: la NTSB suele publicarla; BEA/AAIB a veces no).
- Trayectorias ADS-B para casos sin FDR público: OpenSky solo no comercial; ADS-B Exchange con licencia.
- Los vídeos de `--atlas-guion` no pasan por el doblaje automático: para otros idiomas, un guion y unas escenas por idioma.
