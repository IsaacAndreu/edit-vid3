# Progreso del sistema Atlas

Lo actualiza cada sesión al cerrar una fase (regla 7 de `CLAUDE.md`).
Para continuar: `/atlas-goal` (siguiente fase pendiente) o `/atlas-goal N`.

| Fase | Estado |
|---|---|
| 0 — Cimientos | ✅ completada |
| 1 — Texto y superposiciones | pendiente |
| 2 — Gráficos sin geografía | pendiente |
| 3 — Datos y mapa de relieve (puerta) | pendiente |
| 4 — Perfiles y rejilla | pendiente |
| 5 — Globo y terreno 3D | pendiente |
| 6 — Diagramas | pendiente |
| 7 — Vídeo de referencia completo | pendiente |
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
- `templates/atlas/`: `schema.ts` (zod, §4 del plan), `theme.ts`, `fonts.ts` (Fraunces + IBM
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
- Icono de marca: admite un carácter (☞) o una ruta a imagen en `public/`. El original usa una
  manecilla dibujada y rellena; si se quiere igual, añadir un SVG y poner su ruta en `brand.icon`.
