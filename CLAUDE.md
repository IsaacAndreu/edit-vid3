# Reglas del sistema Atlas (para todas las sesiones)

Este repo construye vídeos de estilo "Atlas" con Remotion. El plan está en
`prompts/atlas-plan.md`; el estilo, en `prompts/atlas-master-prompt.md`; el progreso, en
`prompts/atlas-progress.md`.

1. Lee `prompts/atlas-plan.md` y `prompts/atlas-master-prompt.md` antes de escribir código.
2. Ejecuta sólo la fase pedida. No adelantes trabajo de fases posteriores.
3. Ningún texto, coordenada, cifra o color de un vídeo concreto dentro de un componente.
   Los colores salen de `remotion/atlas/theme.ts`; el contenido, del storyboard.
4. No inventes datos geográficos ni cifras. Si falta un dato, falla o pregunta.
5. **Bucle visual**: tras cada escena, renderiza al menos dos fotogramas con
   `npx remotion still` (mitad y final de la escena), ábrelos, compáralos con el fotograma
   equivalente de `referencias/atlas/frames/` y corrige. Repite hasta que encaje o hasta
   5 intentos; si no encaja, dilo con claridad y enseña ambos.
6. `npm run typecheck` debe pasar antes de cada commit.
7. Al terminar la fase: commit, y un resumen de qué cumple cada criterio de aceptación,
   cuál no, y los fotogramas renderizados. Actualiza `prompts/atlas-progress.md`.
8. Si una decisión de la sección 2 del plan resulta inviable, para y explícalo; no la cambies
   por tu cuenta.

## Comandos útiles

- `npm run typecheck`
- `npm run atlas:anchors <storyboard.json> <transcript.json>` → storyboard con tiempos absolutos
- `npm run atlas:stills <storyboard.json>` → `out/stills/<slug>/` (2 fotogramas por escena + hoja de contactos)
- `npx remotion still remotion/index.ts AtlasVideo out.png --props=<storyboard.json> --frame=N`
- `python3 scripts/accidentes/vuelo.py <tabla_fdr.csv> scripts/accidentes/casos/<caso>.json` → `public/accidentes/<caso>/vuelo.json`
- `npm run atlas:data -- flight-ground public/accidentes/<caso>/vuelo.json` → terreno bajo la trayectoria
- `npx remotion still remotion/index.ts AtlasShort out.png --props=<storyboard.json> --frame=N` → versión vertical
- Plan y progreso de los accidentes aéreos: `prompts/accidentes-plan.md`, `prompts/accidentes-progress.md`
- `python3 scripts/accidentes/buscar_casos.py --escanear 2010 2024` → `out/_accidentes/casos.md` (expedientes de la NTSB con tabla del FDR)
- `python3 scripts/accidentes/buscar_casos.py --preparar <NTSB> <caso>` → esqueleto de `scripts/accidentes/casos/<caso>.json`
- `python3 scripts/accidentes/sonido.py public/accidentes/<caso>/vuelo.json` → sonido de motores sintetizado del N1
