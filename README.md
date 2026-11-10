# edit-vid3

Convierte un guion (`.txt`) y una voz en off (`.mp3`) en un vídeo largo de YouTube 1920x1080 a 30 fps.
El orquestador es Python (`pipeline/`); la composición es Remotion + React (`Root.tsx`, `templates/`).

## Puesta en marcha

```bash
python -m pip install -r requirements.txt
npm install
cp .env.example .env        # y rellena las tres claves
python main.py doctor       # comprueba el entorno, sin llamadas de pago
```

Hacen falta `ffmpeg`/`ffprobe`, Node y Deno en el `PATH`. yt-dlp usa Deno para resolver los
desafíos de YouTube ([guía EJS de yt-dlp](https://github.com/yt-dlp/yt-dlp/wiki/EJS)).
`python main.py doctor --apis` verifica además las claves con peticiones gratuitas.

## Uso diario

Una carpeta por vídeo, con `guion.txt` y `voz.mp3`:

```bash
python main.py materiales/Video1
```

La salida va a `out/Video1/Video1.mp4`. La forma larga sigue funcionando:

```bash
python main.py --guion guion.txt --voz narracion.mp3 --output video_final.mp4
```

| Comando | Para qué |
|---|---|
| `python main.py <proyecto>` | Run completo. Si se interrumpe, **repite el mismo comando**: continúa donde lo dejó. |
| `python main.py <proyecto> --skip-render` | Se detiene tras generar props e informe. |
| `python main.py <proyecto> --redo-scenes 12,20-22` | Busca otro plano solo para esas escenas, evitando el anterior. |
| `python main.py <proyecto> --fresh` | Ignora caché y checkpoint: lo rehace todo. |
| `python main.py render out/Video1/Video1.mp4` | Solo render + master + postflight (tras tocar una plantilla). |
| `python main.py report out/Video1/Video1.mp4` | Regenera el informe HTML. |
| `python main.py studio out/Video1/Video1.mp4` | Abre Remotion Studio con ese run. |
| `python main.py clean --keep 3 --yes` | Borra los assets de los runs antiguos. Sin `--yes` solo lista. |
| `python main.py doctor` | Comprueba el entorno. |

`make help` lista los mismos atajos (`make video PROYECTO=materiales/Video2`, `make check`...).

Otras opciones: `--skip-third-party` (sin YouTube), `--skip-audio-master`, `--media-concurrency N`,
`--render-concurrency N`, `--overrides fichero.json`, `--skip-preflight`, `--verbose`.

## Qué deja cada run

Junto al MP4 (`out/Video1/`):

| Fichero | Contenido |
|---|---|
| `Video1.report.html` | **Empieza por aquí.** Una ficha por escena: plano elegido, contact sheet, fuente, puntuaciones, candidatos descartados, avisos de QA y tiempos. |
| `Video1.props.json` | Entrada de Remotion. Solo existe si la QA ha pasado. |
| `Video1.timeline.json` | Marcadores por escena con toda la procedencia del material. |
| `Video1.qa.json`, `Video1.postflight.json` | Validación antes y después del render. |
| `Video1.timing.json` | Segundos por paso y por escena, y contadores de llamadas. |
| `Video1.media.json` | Checkpoint del material: lo que permite reanudar. |
| `Video1.log` | Detalle completo, incluido el error original de yt-dlp, ffmpeg o las APIs. |

Los clips, contact sheets e imágenes están en `public/pipeline-assets/Video1/`.
Las transcripciones y segmentaciones se guardan por contenido en `.cache/edit-vid3/`: repetir
un run con el mismo audio y guion no vuelve a llamar a Whisper ni a DeepSeek.

## Corregir una escena

1. Abre el informe y anota el número de la escena.
2. Para que el pipeline busque otro plano: `python main.py materiales/Video1 --redo-scenes 23`.
3. Para decidir tú, crea `materiales/Video1/overrides.json` y repite el comando:

```json
{
  "scenes": {
    "23": { "media": "planos/ruleta.mp4" },
    "31": { "keywords": ["casino security camera"], "visualIntent": "CCTV room with monitors" },
    "40": { "text": "5,26 % de ventaja", "templateName": "stat-overlay" }
  }
}
```

`media` es un vídeo o imagen local (ruta relativa al JSON); esa escena no consulta ningún proveedor.
Solo se vuelven a resolver las escenas que cambian.

## Material de terceros

Cada escena narrativa busca primero clips públicos en YouTube con yt-dlp, puntúa ventanas de
subtítulos, descarga los finalistas y pide a DeepSeek que confirme la relevancia visual sobre un
contact sheet. **Cada clip de YouTube queda limitado a cinco segundos**, tanto al prepararlo como
en la QA previa al render (también en `main.py render`). Si no hay candidato válido se usa Pexels
y, como último recurso, GPT Image. La fuente, el autor, los timestamps y el motivo de cada
elección quedan en el timeline, en el informe y en un manifiesto junto a cada clip.

No se usan cookies ni cuentas. Si YouTube deja de responder, el pipeline lo desactiva para el
resto del run, sigue con Pexels y avisa; al repetir el comando reintenta solo esas escenas.

## Ajustes

Todos opcionales, en `.env` (ver `.env.example`):

| Variable | Por defecto | Efecto |
|---|---|---|
| `MEDIA_CONCURRENCY` | 3 | Escenas que buscan material a la vez. `1` = secuencial. |
| `YOUTUBE_PARALLEL` | 4 | Operaciones simultáneas de yt-dlp. Bájalo si YouTube empieza a rechazar peticiones. |
| `YOUTUBE_SINGLE_PASS` | 1 | Metadatos y subtítulos en una sola extracción por vídeo. `0` = dos pasadas. |
| `PEXELS_DOWNLOAD` | 1 | Copia local de los ficheros de Pexels para el render. |
| `SEGMENT_WORDS_FORMAT` | compact | Formato de las palabras enviadas a DeepSeek. `full` = formato anterior. |
| `REMOTION_CONCURRENCY` | (Remotion) | Pestañas de render, p. ej. `6` o `75%`. Mide con `npm run benchmark`. |

## Añadir una plantilla

1. Crea el componente en `templates/components/`; recibe `SceneProps`.
2. Regístralo en `templates/registry.ts`.
3. Descríbelo en `templates/manifest.json`: tipos de escena, qué media necesita y sus reglas.

El manifiesto es la única fuente de verdad: lo leen el prompt de segmentación, la QA, la etapa de
material y `Root.tsx`. `npm run typecheck` falla si registro y manifiesto no coinciden.

| Campo | Significado |
|---|---|
| `sceneTypes` | En qué tipos de escena puede elegirla el segmentador. |
| `media` | `none`, `single` (un vídeo o imagen) o `shots` (montaje). Con `none` no se busca material. |
| `background` | `Root.tsx` pinta el material detrás de la plantilla. |
| `thirdParty` | Puede recibir clips de YouTube. |
| `preferVideo` | En Pexels, vídeo antes que foto. |
| `requiresNumber`, `requiresField`, `maxDurationInFrames` | Reglas que comprueba la QA. |

## Desarrollo

```bash
make check          # tests de Python (sin red ni claves) + tipos de las plantillas
npm run start       # Remotion Studio con example-props.json
```

La generación e importación de avatar sigue desactivada; `--avatar-dir` queda reservado.
