# Progreso del sistema Atlas

Lo actualiza cada sesión al cerrar una fase (regla 7 de `CLAUDE.md`).
Para continuar: `/atlas-goal` (siguiente fase pendiente) o `/atlas-goal N`.

| Fase | Estado |
|---|---|
| 0 — Cimientos | ✅ completada |
| 1 — Texto y superposiciones | ✅ completada |
| 2 — Gráficos sin geografía | ✅ completada |
| 3 — Datos y mapa de relieve (puerta) | ✅ completada (el usuario pidió seguir) |
| 4 — Perfiles y rejilla | ✅ completada |
| 5 — Globo y terreno 3D | ✅ completada |
| 6 — Diagramas | ✅ completada |
| 7 — Vídeo de referencia completo | ⏭ la hace el usuario con el programa, fuera de la nube |
| 8 — Producción de vídeos nuevos | pendiente |

## Fase 0 — Cimientos

**Criterios de aceptación**
- ✅ `storyboards/test-phase0.json` (escena papel 0–3 s + escena noche 3–6 s) renderiza 6,0 s
  (`npm run atlas:render -- out/test-phase0.mp4 --props=storyboards/test-phase0.json`) con
  fundido de 0,5 s, marca e indicador de capítulos.
- ✅ Fondo frente a `1-00_chapter-card.jpg`: centro #e9e1cc (original #ebe4cd), esquina #c7bda8
  (#c7bca6). Frente a `8-28_cta-end.jpg`: borde #182631 (#1a2732), esquina #111a22. El centro
  del original nocturno es más claro porque lleva terreno encima; eso es contenido de escena.
- ✅ Storyboard inválido (`storyboards/test-invalid.json`) falla con un mensaje de una línea
  que nombra cada campo: `Storyboard inválido — meta.slug: … · scenes.0.theme: … · scenes.1.type: …`.
- ✅ Anclas: `npm run atlas:anchors` resuelve `{say, nth, offset}`; falla si la frase no
  aparece o aparece varias veces sin `nth` (probado con `storyboards/test-anchors.json`).

**Qué hay**
- `CLAUDE.md`, `.claude/commands/atlas-goal.md` (comando `/atlas-goal`).
- `remotion/atlas/`: `schema.ts` (zod, §4 del plan), `theme.ts`, `fonts.ts` (Fraunces + IBM
  Plex Mono vía `@remotion/google-fonts`), `time.ts` (anclas y tiempos de escena),
  `context.tsx`, `ui.tsx` (Mono, RichTitle, halo), `anim/` (reveal, drawOn, countUp, stampHit,
  drift, dimAfter), `layers/` (fondo, viñeta, grano, marca, indicador), `AtlasVideo.tsx`,
  `scenes/` (registro + `atlas-blank`), `overlays/` (registro vacío; falla si se usa uno sin componente).
- `scripts/atlas/`: `resolve-anchors.ts`, `stills.ts` (2 fotogramas por escena + hoja de
  contactos en `out/stills/<slug>/`), `validate.ts`, `load.ts`.
- `npm run atlas:render | atlas:anchors | atlas:stills | atlas:validate`.

**Desviaciones y decisiones menores**
- Esquema: añadidos `meta.duration` (opcional; si falta se usa la duración de `audio.voice`),
  `audio.voice` y `audio.transcript` opcionales (borradores mudos), `lines[].accent` en
  `info-card`, y la escena `atlas-blank` (lienzo vacío para pruebas). `stamp.x/y` son fracciones 0–1.
- Las rutas del storyboard (voz, transcripción, GeoJSON) son relativas a `public/`.
- Anclas: la composición las resuelve sola en `calculateMetadata` leyendo `audio.transcript`;
  el script hace lo mismo fuera de Remotion para revisar tiempos.
- OpenGL: `remotion.config.ts` usa `swangle` (SwiftShader sobre ANGLE, lo que usa Remotion
  Lambda sin GPU); `REMOTION_GL=angle` para máquinas con GPU. Se comprobará en la fase 5.
- Navegador: en el contenedor cloud se usa el Chromium completo de `/opt/pw-browsers`
  (el headless-shell no confía en el CA del proxy y no baja las fuentes). Fuera, `REMOTION_BROWSER`
  o el navegador de Remotion.
- Icono de marca: admite un carácter o una ruta a imagen en `public/`. Por defecto ✦ ATLAS;
  cada vídeo usa la marca de su canal.

## Fase 1 — Escenas de texto y superposiciones

Storyboard de prueba: `storyboards/test-phase1.json` (11 escenas, 44 s).
Comparativas: `npm run atlas:stills -- storyboards/test-phase1.json` y
`npm run atlas:compare -- <salida.jpg> <render.png>=<referencia>`.

**Criterios de aceptación**
- ✅ Réplicas reconocibles de `0-52_agenda`, `1-00_chapter-card`, `4-05_cta-mid`,
  `5-07_statement-card-row`, `7-05_checklist`, `8-16_recap`, `8-28_cta-end` (composición,
  jerarquía tipográfica y color). Tres rondas de bucle visual: centro de la viñeta movido bajo el
  contenido (desvaía el texto), viñeta bajo las tarjetas, checklist más compacto, recap más grueso.
- ✅ Los revelados entran en orden (numerales de la agenda, tarjetas, casillas, líneas de la
  info-card, pasos del contador).
- ✅ Superposiciones `info-card`, `stamp`, `counter` (cada número del texto cuenta y el último
  fotograma es el texto exacto del storyboard), `legend` y nota de fuente (`sourceNote`).

**Diferencias conocidas con el original**
- La serif es Fraunces; la del original es más condensada y de más contraste. Se nota en
  titulares largos (ocupan ~8 % más de ancho).
- El fondo nocturno del CTA final lleva terreno 3D en el original; aquí el CTA admite
  `backdrop: "previous"` y lo tendrá cuando exista `atlas-terrain-3d` (fase 5).
- Marca: ✦ ATLAS en todas las pruebas.

**Esquema añadido**: `atlas-chapter-card {of}`, `atlas-agenda {numerals[], tagline, notes[]}`,
`atlas-title-overlay {dim}`, `atlas-statement`, `atlas-card-row {cards[]}`,
`atlas-checklist {items[]}`, `atlas-recap {items[] uno por capítulo}`,
`atlas-cta {layout: card|stack, button{label, doneLabel, clickAt}}`. Todas aceptan `titleAt`
y `backdrop: "previous"` (la escena anterior sigue animándose detrás, atenuada).

## Fase 2 — Gráficos sin geografía

Storyboard de prueba: `storyboards/test-phase2.json` (6 escenas, 36 s).

**Criterios de aceptación**
- ✅ Réplicas de `2-25_dial-countdown`, `7-58_dial-saved`, `1-11_bar-compare`,
  `6-28_bar-compare-threshold`, `5-39_dot-density`, `5-47_runway-compare`. Dos rondas de bucle
  visual (posiciones verticales del gráfico de umbral, la densidad y las pistas; dispersión de puntos).
- ✅ Las cifras cuentan y terminan exactamente en el valor del storyboard: la esfera muestra
  `to` en el último fotograma; barras y porcentajes usan el texto `display` literal al acabar.

**Esquema añadido**
- `atlas-dial {dial{max, from, to, at, seconds, fill: remaining|elapsed, accent, hand}, readout{text con {value}, style: mono|serif}}`
- `atlas-bar-compare {axis{max, step, format "{v} KM", style: grid|ticks, base}, labels: below|above, bars[{label, value, display, at, style: earth|hatched, valueAccent, inside}], ghost, threshold{band}, side{kicker, items}}`
- `atlas-dot-density {grid, boxes[{label, percent, display, at, accent}]}` — los puntos que
  desaparecen son siempre los mismos (semilla fija).
- `atlas-runway-compare {notes[], runways[{label, liftoff (0–1), at, seconds, liftoffLabel}], footer}`
- `sourceNote` pasa a ir centrada al pie, como en el original.
- Icono genérico de avión cenital en `remotion/atlas/icons.tsx` (se reutilizará en mapas).

**Diferencias conocidas**: el avión de la pista no deja la estela de humo del original.

## Integración con el proyecto real (tras fusionar main)

- `templates/atlas` → `remotion/atlas`; `AtlasVideo` registrada en `remotion/Root.tsx` (el Root.tsx de la raíz
  y `templates/` son el esqueleto antiguo). Fuentes Fraunces e IBM Plex Mono desde `@fontsource` (render sin red).
- El Atlas automático (`pipeline/atlas.py` → `remotion/components/graphics/Atlas.tsx`) usa ya el aspecto de
  referencia: fuentes, paleta, tarjetas con doble filete, sello, titular centrado con halo, barras verticales.
- Vista `"scene"` en `pipeline/atlas.py`: la IA puede pedir dial, compare, density, runway, agenda, recap y cards;
  `remotion/atlas/embed.tsx` las dibuja con los mismos componentes que `AtlasVideo`. Cifras sólo del guion
  (`check_scene`). VERSION 21.
- Marca: ✦ ATLAS en todas partes, también tapada en los fotogramas de referencia.

## Fase 3 — Datos y mapa de relieve

Scripts (`npm run atlas:data -- …`): `region <id>` (Terrarium z7 → textura proyectada día/noche + alturas 16 bits),
`contour <id> <m>`, `country <nombre>`. Paquete `tibet` (cónica conforme, 5600×3413 px), contorno de 3 000 m
(≈2,98 M km², una forma con el hueco de Qaidam), silueta de Groenlandia.
Fórmula Terrarium comprobada en tilezen/joerd `docs/formats.md`; Everest en z12 = 8 749 m (real 8 849 m).

Escena `atlas-relief-map`: textura con cámara por keyframes (geodésica + zoom logarítmico + deriva 3 %),
siluetas (relleno + contorno, o movida por la esfera a escala real con `moveTo`), rutas que se trazan (rectas o
de círculo máximo, con avión opcional), puntos (ciudad, aeropuerto, suceso) con nombres que no se pisan,
etiquetas y flechas. Acento nuevo `ink`.

Storyboard de prueba: `storyboards/test-phase3.json` (5 escenas). Comparativa: `out/stills/test-phase3/cmp3.jpg`.

**Criterios**
- ✅ Réplicas de `0-21`, `0-24` (Groenlandia a escala: ~0,7 del ancho de la meseta, como el original),
  `0-44/0-46`, `2-04`, `6-47`; silueta de la meseta, costas y ciudades en su sitio real.
- ✅ Las rutas se dibujan; la cámara panea por keyframes.
- ✅ Clip de 15 s (`out/test-phase3-clip.mp4`, sin versionar) sin saltos: la detección de cortes de ffmpeg no encuentra ninguno.
- Rendimiento: el papel y el grano eran filtros SVG de ruido recalculados por fotograma (~2 s/fotograma sin GPU);
  ahora usan la tesela `remotion/data/grain.png` como el Atlas automático: texto ~0,45 s y relieve ~0,75 s por
  fotograma en este contenedor de 4 núcleos (el globo del Atlas automático, >3,6 s).

**Datos no verificados (marcados en pantalla como ILLUSTRATIVE)**: el trazado de las aerovías L888 e Y1 y las
distancias a los aeropuertos de reserva son aproximados en el storyboard de prueba; para un vídeo real deben salir
de una fuente (AIP de China). Las coordenadas de ciudades son las reales.

**Pendiente para usar el relieve en el pipeline automático**: el render del pipeline usa `--public-dir=work/<slug>`;
habrá que copiar el paquete de región a esa carpeta (o servir `public/atlas-data` desde allí).

## Fase 4 — Perfiles de altitud y rejilla

Scripts: `npm run atlas:data -- profile <id> <lon,lat> <lon,lat>` (círculo máximo, Terrarium z9; cada muestra es el
máximo en ±2 km a los lados) y `cells <id> <bbox> [zoom] --peaks <json>` (máximo por celda de 1°×1°; las cumbres
medidas con fuente mandan si el DEM las suaviza: Everest 8.849 m, K2 8.611 m en
`scripts/atlas-data/peaks/himalaya-karakoram.json`).
Datos: `profiles/karakoram-hengduan` (2.462 km), `profiles/chongqing-lhasa` (780 km), `cells/tibet-plateau`
(70–105 E, 25–42 N, 595 celdas).

Escena `atlas-elevation-profile`: terreno real (o mar abierto, con cambio en vivo), ejes en pies y km, trayectoria
por puntos con curva suave o lineal y avión de perfil, umbrales, bandas, altitud mínima segura escalonada calculada
del propio perfil (máximo por tramo + margen, redondeado a 100 ft), descenso que se detiene en ella, línea de despeje
sobre el terreno, tramos por debajo de la MSA en rojo, marcas verticales y notas.
Capa `graticule` del mapa: MSA por celda con el formato del original (31¹ = 31.100 ft), cifras rojas por encima del
umbral, relleno, celda destacada. La leyenda admite `sub`; las líneas de una info-card con titular van en versalitas.

Storyboard: `storyboards/test-phase4.json`. Comparativa: `docs/atlas/fase4.jpg`.

**Criterios**
- ✅ Réplicas de `2-10`, `2-37`, `2-45`, `3-42`, `4-45`, `1-33`, `1-37` (dos rondas de bucle visual).
- ✅ El perfil Karakórum–Hengduan sale de datos reales y su forma se parece a la del original.
- ✅ La rejilla da las mismas cifras que el original en la zona del Everest (31¹ en su celda; 28⁹, 29⁹, 30²… al lado)
  y el relleno por encima de 20.000 ft dibuja la misma forma.

**Diferencias**
- Los extremos exactos del perfil del original no se conocen: con los elegidos sale 2.462 km (el rótulo usa la
  distancia real del perfil, no los 2.760 km del original).
- En `4-45` la MSA calculada queda casi siempre por debajo de 22.630 ft, así que apenas hay tramos rojos; el original
  usa un escalón más alto. Se respeta el dato.
- `3-42`: una sola trayectoria (el original dibuja también la vuelta a Chengdu). La posición de Xiaojin en el perfil
  es aproximada (`FLIGHT PATH SIMPLIFIED`).
- Papel: grano del fondo bajado a 4,5 % (salía grisáceo).

## Fase 5 — Globo y terreno 3D

WebGL sin GPU: funciona con `--gl=swangle` (SwiftShader sobre ANGLE); `angle` y `swiftshader` a secas fallan en el
contenedor. `scripts/atlas/stills.ts` ya lo pasa, y `pipeline/render.py` usa `swangle` por defecto.

Scripts: `npm run atlas:data -- globe [ancho] [zoom]` (textura equirectangular del mundo, día y noche, con relieve,
mar por profundidad e hielo de Natural Earth) y `terrain <id> <bbox> <columnas> <zoom> <curvas_m> [suavizado]`
(rejilla de alturas en km + textura con sombreado y curvas de nivel). Datos: `globe/earth-{paper,night}.jpg`,
`terrain/everest` (49×27 km), `terrain/tibet-3d` (2.988×1.548 km, suavizado 3 celdas para ×30).

`atlas-globe`: esfera de three.js con cámara ortográfica a escala de píxel; las capas vectoriales (siluetas, rutas de
círculo máximo que se trazan sólo en la cara visible, puntos con nombre, etiquetas) usan d3 `geoOrthographic` con la
misma rotación y escala: el contorno de la meseta cae sobre su relieve en la textura. Deriva lenta (0,25°/s, +3 %).
La región destacada es roja también de noche. La leyenda es tarjeta de papel en ambos temas.

`atlas-terrain-3d`: malla de la rejilla con exageración vertical, paredes y filetes de tinta, cámara por keyframes
(inclinación, giro, distancia, objetivo), extrusión animada desde el mapa plano, umbral teñido en rojo con su borde
(shader), rótulos de cordillera, cumbre con línea guía, cifras, línea de crucero, avión con línea de altitud y
estela, eje en km y rótulo de base. Todo lo 2D se proyecta con una copia de la misma cámara.

Storyboard: `storyboards/test-phase5.json`. Comparativa: `docs/atlas/fase5.jpg`.

**Criterios**
- ✅ Réplicas de `0-12_globe-routes-legend`, `7-28_globe-light-card`, `0-06_terrain3d-night-hook`,
  `0-28_terrain3d-threshold`, `1-19_terrain3d-labels` (y `8-23` de cierre). Tres rondas de bucle visual.
- ✅ El render sin pantalla funciona.
- ✅ Clip de 10 s (meseta: extrusión, inclinación, umbral y paso a la escena encadenada) sin parpadeo: sin cortes
  detectados por ffmpeg y sin picos aislados en la diferencia entre fotogramas (máx. 3,1 fuera del fundido de tema).
  Arreglos hechos para ello: la deriva de cámara continúa entre escenas encadenadas del mismo bloque; el objetivo de
  cámara se interpola desde el centro del bloque; el indicador de capítulos entra con fundido; las entradas
  `continuous` también se funden (el encuadre coincide, así que sólo se desvanece lo que cambia).
- Render: ~0,95 s por fotograma con 3D en este contenedor de 4 núcleos sin GPU.

**Diferencias**
- El relieve 3D del original está más suavizado; aquí se ve más detalle del DEM (ajustable con el suavizado).
- El Everest del DEM es 8.665 m a esta resolución; el rótulo dice 8.849 m (el dato oficial, del storyboard).

## Fase 6 — Diagramas

`atlas-diagram`: carga un SVG de `public/atlas-diagrams/` y lo dibuja dentro de un rectángulo de pantalla. Las capas
(ids) cambian de estado con la voz —opacidad, relleno, trazo, discontinuo, desplazamiento, giro, escala—, cada cambio
interpolado desde el anterior; los colores salen del tema por clases (`ink`, `paper`, `earth`, `glass`, `body`,
`amber`, `grey`, `seat`, `red`…), así que el SVG no lleva colores de un vídeo. Llamadas con línea guía desde un punto
del dibujo y barras que se vacían o se llenan (`meters`).

Ilustraciones (`python3 scripts/atlas-diagrams/build.py`), cada una con sus capas documentadas en un comentario:
`seat-oxygen` (maletero, generador, trampilla, tubo, mascarilla colgando/puesta, pasajero, asiento),
`cockpit-top` (morro, parabrisas izq./dcho., panel, pedestal, asientos con pilotos, cinturón, trayectorias),
`plane-twin-top` (fuselaje, alas, cola, motor de arriba/abajo), `widebody-cabin` (asientos, tripulación),
`cargo-cabin` (contenedores, tripulación), `oxygen-bottles` (botella-1…6), `plane-side`.
Para usar dibujos propios: un SVG cualquiera con los mismos ids (o ids nuevos que nombre el storyboard).

Storyboard: `storyboards/test-phase6.json`. Comparativa: `docs/atlas/fase6.jpg`.

**Criterios**
- ✅ Réplicas reconocibles de `2-54`, `3-30`, `4-18`, `7-16`, `7-21`.
- La calidad de las ilustraciones generadas llega para estas cinco; para dibujos más finos, sustituir el SVG.

**Diferencias**: la figura del pasajero es más esquemática que la del original; las trayectorias de la cabina son
líneas discontinuas fijas (el original las anima).
