# Plan de construcción — sistema "Atlas"

Objetivo: que este repo produzca vídeos como `atlasprueba.mp4` (estilo descrito en
`atlas-master-prompt.md`) de forma repetible, con un modelo de código trabajando por sesiones.

Documentos relacionados:
- `prompts/atlas-master-prompt.md` — qué aspecto tiene (estilo, escenas, reglas).
- `prompts/atlas-tibet-storyboard.md` — el vídeo de referencia, escena a escena.
- `referencias/atlas/frames/` — 45 fotogramas del original, nombrados `m-ss_tipo-de-escena.jpg`.
- Este archivo — cómo construirlo y en qué orden.

---

## 1. Por qué falla si se pide de golpe, y cómo lo evita este plan

| Riesgo | Medida |
|---|---|
| El modelo no ve lo que renderiza y da por bueno algo feo | Bucle visual obligatorio: renderizar fotogramas sueltos y compararlos con `referencias/atlas/frames/` antes de cerrar cada tarea |
| Inventa geografía (contornos, rutas, alturas) | Toda la geografía sale de datos descargados por scripts; el storyboard sólo lleva coordenadas `[lon, lat]` y cifras con fuente |
| Cada sesión inventa su propio formato de datos | Esquema del storyboard fijado en este plan (sección 4) y validado con zod |
| Trabajo demasiado grande para una sesión | 9 fases; una sesión por fase; cada una acaba con commit y criterio de aceptación |
| Se invierte todo y el mapa no convence | Puerta de decisión al final de la fase 3: si el mapa no se parece, se para ahí |
| El contexto se pierde entre sesiones | `CLAUDE.md` en la raíz con las reglas fijas (lo crea la fase 0) |

## 2. Decisiones de arquitectura (cerradas; no reabrir en cada sesión)

1. **Composición nueva `AtlasVideo`**, separada de `YoutubeVideo`. La actual encadena escenas
   con corte seco y props planas (`SceneProps`); Atlas necesita fundidos, capas persistentes y
   datos anidados. No se toca el pipeline existente de clips de stock.
2. **1920×1080, 30 fps.** Tiempos del storyboard en segundos; la conversión a frames es interna.
3. **Carpeta `templates/atlas/`**: `theme.ts`, `schema.ts`, `AtlasVideo.tsx`, `layers/`,
   `scenes/`, `overlays/`, `geo/`, `anim/`.
4. **Mapas planos en SVG con `d3-geo`** sobre una textura de relieve **ya proyectada** por un
   script (una imagen por "paquete de región"). La cámara es un paneo/zoom sobre esa imagen y
   los vectores usan la misma proyección, así no se reproyecta ningún raster por fotograma.
5. **Globo y terreno 3D con `@remotion/three`**: esfera con textura equirectangular; malla
   desplazada por el mapa de alturas con faldón lateral para el bloque.
6. **Sincronía por anclas de texto**, no por segundos escritos a mano: cada revelado apunta a
   una frase de la narración y un script lo resuelve contra las marcas de Whisper.
7. **Datos geográficos generados una vez** en `public/atlas-data/`, versionados si pesan poco
   y regenerables con `npm run atlas:data`.

Dependencias a añadir: `d3-geo`, `d3-contour`, `d3-shape`, `topojson-client`, `world-atlas`,
`zod`, `three`, `@react-three/fiber`, `@remotion/three`, `@remotion/google-fonts`, `sharp`
(sólo scripts). Fijar `@remotion/*` a la misma versión que `remotion` (4.0.525).

## 3. Capa de datos

Fuentes comprobadas como accesibles desde el entorno cloud de este repo:

| Dato | Fuente | Uso |
|---|---|---|
| Costas y países | paquete npm `world-atlas` (TopoJSON 110m/50m) | tierra, mar, siluetas a escala |
| Vectores finos (10m, lagos, ríos) | GitHub `nvkelso/natural-earth-vector` (GeoJSON) | zooms cercanos |
| Elevación | teselas Terrarium en `s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png` | todo lo demás |

Fórmula Terrarium: `metros = R*256 + G + B/256 − 32768`. Verificarla en la documentación
antes de usarla y comprobar con un punto conocido (Everest ≈ 8 849 m).

Scripts en `scripts/atlas-data/` (Node), todos deterministas y con caché en disco:

- `build-region.ts <id>` — a partir de `{id, bbox, projection, zoom}` genera en
  `public/atlas-data/regions/<id>/`: `relief.jpg` (sombreado + tinte hipsométrico pergamino,
  ya proyectado), `relief-night.jpg`, `height.png` (16 bits), `meta.json` (proyección y escala).
- `build-contour.ts <id> <metros>` — contorno de elevación simplificado como GeoJSON
  (p. ej. meseta = tierra por encima de 3 000 m).
- `build-profile.ts <lonlat A> <lonlat B>` — perfil de elevación por círculo máximo, JSON.
- `build-cells.ts <bbox>` — máximo de elevación por celda de 1°×1°, JSON.
- `build-globe.ts` — textura equirectangular del mundo, claro y noche.

Si un host no responde, el script falla con mensaje claro. Nunca se sustituye por datos inventados.

## 4. Esquema del storyboard (`templates/atlas/schema.ts`)

Contrato único entre quien escribe el vídeo y quien lo renderiza. Se implementa con zod y se
pasa a `Composition` como `schema`.

```ts
type LonLat = [number, number];
type Accent = 'danger' | 'data' | 'good' | 'amber';

/** Momento en el tiempo: ancla a la narración o segundo absoluto. */
type At =
  | { say: string; nth?: number; offset?: number } // frase literal del guion
  | { t: number };                                 // segundos desde el inicio del vídeo

/** Texto con resaltado: "Clear-headed for *a minute or less*" */
type Rich = { text: string; accent?: Accent };

interface AtlasStoryboard {
  meta: {
    slug: string; title: string;
    brand: { name: string; icon: string };
    chapters: { numeral: string; label: string }[];
  };
  audio: { voice: string; music?: string; transcript: string };
  scenes: AtlasScene[];
}

interface SceneBase {
  id: string;
  type: string;                 // clave del registro, p. ej. 'atlas-relief-map'
  start: At;                    // termina cuando empieza la siguiente
  theme: 'paper' | 'night';
  chapter?: number;             // índice en meta.chapters; controla el indicador
  enter: 'fade' | 'continuous'; // 'continuous' = hereda la cámara de la escena anterior
  kicker?: string;              // antetítulo mono
  title?: Rich;
  sourceNote?: string;
  overlays?: Overlay[];
  sources?: string[];           // URL o cita de cada dato usado; obligatorio si hay cifras
}

type Overlay =
  | { kind: 'info-card'; at: At; until?: At; corner: 'tl'|'tr'|'bl'|'br';
      kicker?: string; title: Rich; lines?: { text: string; at?: At }[]; sub?: string }
  | { kind: 'stamp'; at: At; text: string; x: number; y: number }
  | { kind: 'counter'; at: At; corner: 'tl'|'tr'|'bl'|'br';
      kicker: string; steps: { value: string; at: At }[]; sub?: string }
  | { kind: 'legend'; at: At; corner: 'tl'|'tr'|'bl'|'br';
      items: { style: 'dashed'|'solid'|'fill'; accent: Accent; label: string }[] };

interface ReliefMapScene extends SceneBase {
  type: 'atlas-relief-map';
  region: string;                                   // paquete en public/atlas-data/regions
  camera: { at: At; center: LonLat; zoom: number }[];
  shapes?: { id: string; source: string;            // ruta a GeoJSON generado
             at: At; stroke?: Accent; fill?: boolean; label?: string; sub?: string;
             moveTo?: LonLat }[];                    // moveTo = silueta trasladada a escala
  routes?: { id: string; path: LonLat[]; at: At; drawSeconds: number;
             style: 'solid'|'dashed'|'dotted'; accent: Accent; label?: string;
             icon?: 'plane'; greatCircle?: boolean }[];
  points?: { name: string; at: At; pos: LonLat; value?: string;
             marker: 'city'|'airport'|'event'; accent?: Accent }[];
  labels?: { text: string; at: At; pos: LonLat; style: 'region'|'mono'; accent?: Accent }[];
  arrows?: { from: LonLat; to: LonLat; at: At; accent: Accent }[];
  graticule?: { at: At; cells: string;               // JSON de build-cells
                threshold?: { value: number; at: At }; highlight?: LonLat };
}
```

El resto de escenas (`atlas-globe`, `atlas-terrain-3d`, `atlas-elevation-profile`,
`atlas-dial`, `atlas-bar-compare`, …) añaden su interfaz al mismo archivo en la fase que las
construye, siguiendo las mismas convenciones: `at: At` en todo lo que aparece, colores sólo por
`Accent`, textos sólo por `Rich` o string, geografía sólo por `LonLat` o ruta a un archivo generado.

## 5. Reglas para todas las sesiones (contenido de `CLAUDE.md`)

1. Lee `prompts/atlas-plan.md` y `prompts/atlas-master-prompt.md` antes de escribir código.
2. Ejecuta sólo la fase pedida. No adelantes trabajo de fases posteriores.
3. Ningún texto, coordenada, cifra o color de un vídeo concreto dentro de un componente.
   Los colores salen de `theme.ts`; el contenido, del storyboard.
4. No inventes datos geográficos ni cifras. Si falta un dato, falla o pregunta.
5. **Bucle visual**: tras cada escena, renderiza al menos dos fotogramas con
   `npx remotion still` (mitad y final de la escena), ábrelos, compáralos con el fotograma
   equivalente de `referencias/atlas/frames/` y corrige. Repite hasta que encaje o hasta
   5 intentos; si no encaja, dilo con claridad y enseña ambos.
6. `npm run typecheck` debe pasar antes de cada commit.
7. Al terminar la fase: commit, y un resumen de qué cumple cada criterio de aceptación,
   cuál no, y los fotogramas renderizados.
8. Si una decisión de la sección 2 resulta inviable, para y explícalo; no la cambies por tu cuenta.

## 6. Fases

Cada fase es una sesión. Prompt para lanzarla, igual siempre:

> Lee `CLAUDE.md`, `prompts/atlas-plan.md` y `prompts/atlas-master-prompt.md`.
> Ejecuta la **Fase N** del plan completa y nada más. Cumple el bucle visual y los criterios
> de aceptación, haz commit y termina con el informe que pide la regla 7.

(En la fase 0 todavía no existe `CLAUDE.md`: se omite de la lista.)

### Fase 0 — Cimientos
- Crear `CLAUDE.md` con la sección 5.
- Instalar dependencias; comprobar en la documentación de Remotion el ajuste de renderizador
  OpenGL necesario para `@remotion/three` en render sin pantalla y dejarlo en `remotion.config.ts`.
- `templates/atlas/schema.ts` (sección 4) y `theme.ts` (tokens del prompt maestro).
- `AtlasVideo.tsx`: resuelve tiempos, monta escenas con fundido de 0,5 s, registro propio de escenas.
- `anim/`: utilidades `reveal`, `drawOn`, `countUp`, con el easing del prompt maestro.
- Capas globales: fondo papel/noche, grano, viñeta, marca, indicador de capítulos.
- `scripts/atlas/resolve-anchors.ts`: storyboard + transcripción → tiempos absolutos; error si
  una frase no aparece o aparece más de una vez sin `nth`.
- `npm run atlas:stills <storyboard>`: dos fotogramas por escena en `out/stills/<slug>/` más
  una hoja de contactos.
- Fuentes vía `@remotion/google-fonts`.

**Aceptación**: un storyboard de prueba con dos escenas vacías (papel y noche) renderiza 6 s
con fundido, marca e indicador; el fondo coincide con `1-00_chapter-card.jpg` y
`8-28_cta-end.jpg`; un storyboard inválido falla con mensaje legible.

### Fase 1 — Escenas de texto y superposiciones
`atlas-chapter-card`, `atlas-agenda`, `atlas-title-overlay`, `atlas-statement`,
`atlas-card-row`, `atlas-checklist`, `atlas-recap`, `atlas-cta`; superposiciones `info-card`,
`stamp`, `counter`, `legend`, nota de fuente.

**Aceptación**: réplicas de `0-52_agenda`, `1-00_chapter-card`, `4-05_cta-mid`,
`5-07_statement-card-row`, `7-05_checklist`, `8-16_recap`, `8-28_cta-end` reconocibles como la
misma pieza (composición, jerarquía tipográfica, color); los revelados entran en orden.

### Fase 2 — Gráficos sin geografía
`atlas-dial`, `atlas-bar-compare`, `atlas-dot-density`, `atlas-runway-compare`.

**Aceptación**: réplicas de `2-25_dial-countdown`, `7-58_dial-saved`, `1-11_bar-compare`,
`6-28_bar-compare-threshold`, `5-39_dot-density`, `5-47_runway-compare`; las cifras cuentan y
terminan exactamente en el valor del storyboard.

### Fase 3 — Datos y mapa de relieve  ← puerta de decisión
- Scripts `build-region` y `build-contour`; paquete `tibet` y contorno de 3 000 m.
- `atlas-relief-map` con todas las capas de la sección 4 salvo `graticule`, y cámara por keyframes.

**Aceptación**: réplicas de `0-21_relief-map-region`, `0-44_relief-map-routes-card`,
`2-04_relief-map-history-card`, `6-47_relief-map-backup-airports`. La silueta de la meseta,
las costas y la posición de las ciudades coinciden con el original; las rutas se dibujan; la
cámara panea sin saltos; un clip de 15 s se ve fluido.

**Puerta**: enseñar al usuario cuatro parejas original/render. Si el mapa no convence, se
itera aquí antes de seguir; el resto del sistema depende de esta pieza.

### Fase 4 — Perfiles de altitud y rejilla
- Scripts `build-profile` y `build-cells`.
- `atlas-elevation-profile` (terreno intercambiable, trayectoria con avión, umbrales, línea
  escalonada, bandas, tramos en infracción).
- Capa `graticule` del mapa con cifras por celda y relleno por umbral.

**Aceptación**: réplicas de `2-10`, `2-37`, `2-45`, `3-42` y `4-45` (perfiles) y de
`1-33_graticule-cells-card`, `1-37_graticule-fill-legend`. El perfil Karakórum–Hengduan sale de
datos reales y su forma se parece a la del original.

### Fase 5 — Globo y terreno 3D
`atlas-globe` (claro y noche, rutas de círculo máximo, región resaltada) y `atlas-terrain-3d`
(inclinación desde cenital, exageración vertical, umbral coloreado, etiquetas, avión con línea
de altitud).

**Aceptación**: réplicas de `0-12_globe-routes-legend`, `7-28_globe-light-card`,
`0-06_terrain3d-night-hook`, `0-28_terrain3d-threshold`, `1-19_terrain3d-labels`; el render sin
pantalla funciona y un clip de 10 s no parpadea.

### Fase 6 — Diagramas
`atlas-diagram`: carga un SVG con capas identificadas, cambia estados y dibuja llamadas.
Ilustraciones necesarias para el vídeo de referencia: asiento con mascarilla, cabina cenital,
avión bimotor cenital, fuselaje con asientos/carga, botellas de oxígeno, silueta de avión.

**Aceptación**: réplicas de `2-54`, `3-30`, `4-18`, `7-16`, `7-21`. Si la calidad de las
ilustraciones generadas no llega, se entregan los SVG con los ids de capa documentados para que
el usuario los sustituya por dibujos propios sin tocar código.

### Fase 7 — Vídeo de referencia completo
- Convertir `atlas-tibet-storyboard.md` en `storyboards/tibet.json`, con fuentes en cada cifra.
- Generar todos los datos, la hoja de contactos completa y revisarla escena a escena.
- Render completo con audio; revisión de ritmo (ninguna pantalla quieta más de 2 s).

**Aceptación**: vídeo de 8–9 min que sigue el storyboard; lista explícita de escenas que se
apartan del original y por qué. `atlas-valley-flight` es opcional: si no se aborda, se
sustituye por un perfil de altitud y se anota.

### Fase 8 — Producción de vídeos nuevos
- `pipeline/atlas/`: guion + voz → transcripción (ya existe) → borrador de storyboard hecho por
  un modelo a partir del guion, el catálogo de escenas y el esquema → validación zod →
  generación de datos → hoja de contactos → render.
- Entrada en `main.py`: `--style atlas`.
- `docs/atlas-authoring.md`: catálogo de escenas con una imagen y un ejemplo de JSON de cada una.

**Aceptación**: un segundo vídeo corto (2–3 min) de otro tema y otra región sale del pipeline
sin tocar componentes.

## 7. Flujo para cada vídeo nuevo (una vez construido)

1. Guion con la estructura del prompt maestro (gancho, pregunta, contexto, agenda, capítulos,
   giro, resumen, cierre) y voz grabada.
2. Lista de hechos: cada cifra, fecha y nombre con su fuente.
3. Lista de lugares: regiones, ciudades y rutas con coordenadas.
4. Borrador de storyboard (pipeline de la fase 8) y revisión humana.
5. `npm run atlas:data` → `npm run atlas:stills` → revisar la hoja de contactos.
6. Ilustraciones nuevas, si el tema las pide.
7. Render, masterizado de audio y postflight existentes.

Lo que se reutiliza sin cambios: tema, capas, todas las escenas, scripts de datos, pipeline.
Lo que cambia por vídeo: storyboard, paquetes de región, ilustraciones específicas.

## 8. Límites conocidos

- El parecido del relieve y del 3D con el original depende de ajuste visual; el plan lo acota
  (puerta de la fase 3) pero no lo garantiza.
- Las ilustraciones son la parte donde más probable es necesitar trabajo manual.
- La narración del vídeo de referencia no está transcrita; el storyboard de Tíbet lleva
  tiempos tomados de la imagen y habrá que reanclarlos al audio que se use.
- Los datos de cada vídeo deben verificarse: el sistema dibuja lo que se le da.
