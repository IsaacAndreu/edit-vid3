# Harness de Estudio: mock de `/api`, capturas, métricas y peso

Pruebas de la interfaz del Estudio en un Chromium de verdad, con `/api/*` simulado (30 canales, ~300 vídeos en
todos los estados). Solo dependen de `#app`, de `header nav a` y de las rutas con `#`. Playwright y Chromium ya están
en la máquina de Claude Code (`require('playwright')`); en otro equipo: `npx playwright install chromium`.

Todo se lanza desde esta carpeta (`cd tests/ui`) con el estudio arrancado en el puerto 8099. Lo que generan va a
`out/` (ignorado por git). Cuando una página use un endpoint nuevo, añádelo a `mock.js`/`mock-data.js`: lo que no
está simulado sale en «Sin mock».

| Script | Qué comprueba |
|---|---|
| `shoot.js` | todas las rutas × escritorio/móvil × oscuro/claro: errores de consola, desborde, nodos, alto, capturas |
| `weight.js` | peso de la primera carga y de la siguiente (caché, 304, gzip) |
| `audit.js` | botones y enlaces sin nombre, campos sin etiqueta, imágenes sin alt, clics sin teclado |
| `behave.js` | un refresco con los mismos datos no toca el DOM; navegación rápida; texto y foco conservados |
| `dialogs.js` | avisos y diálogos propios: foco dentro, Esc, foco devuelto, ningún diálogo nativo |
| `paint.test.js` | `paint.js` por sí solo (sin servidor) |

## Arrancar la app

    cd ../.. && python main.py --web 8099 --host 127.0.0.1

## shoot.js: capturas y métricas

    node shoot.js --base http://127.0.0.1:8099 --out out/antes           # dueño: 28 rutas × 4 vistas (~2 min)
    node shoot.js --base http://127.0.0.1:8099 --out out/socio --partner
    node shoot.js --base … --out … --no-shots                                  # solo métricas (~40 s)
    node shoot.js --base … --out … --routes "#/,#/calendario" --only desktop-dark --jobs 6

Por cada ruta × {desktop 1440×900, mobile 390×844 táctil} × {dark, light}:

1. Página nueva con el mock, carga directa de `base/#ruta`, espera a que el DOM lleve 400 ms quieto y no haya
   peticiones en vuelo (tope 12 s). Ahí mide y fotografía (`<ruta>.<vista>.<esquema>.png`, página entera recortada
   a 5000 px de alto, escala 1, animaciones paradas, imágenes `loading=lazy` forzadas a cargar).
2. `about:blank` → carga `#/` (o `#/videos` cuando la ruta es `#/`) → `location.hash = ruta` → `paintMs` = ms hasta
   la última mutación del DOM.

`metrics.json` (un registro por página): `nodes`, `appNodes`, `height`, `styled` (elementos con `style=`),
`overflow` + `offenders`, `scrollWidth`, `loadMs`, `paintMs`, `consoleErrors`, `pageErrors`, `failedRequests`,
`badResponses`, `unmocked`, `denied`, `nav` (enlaces del menú), `coldError`/`measuredFrom` (ver abajo), `shot`.

Código de salida 1 si hay errores de consola/pageerror, desborde horizontal o (con `--partner`) falla una
comprobación del socio. En el móvil el desborde se mide contra 390 px (Chromium aleja el zoom y `innerWidth` crece).

Si la app pinta un error al cargar una ruta directamente (hoy: `#/guiones`), se apunta en `coldError`, y las
métricas y la captura se toman llegando desde `#/` (`measuredFrom: "navegación"`). No cambia el código de salida.

Con `--partner`: rutas de `PARTNER_PAGES` + un ejemplo de cada `PARTNER_PREFIXES` + `#/cuenta`; además comprueba
(`partner-checks.json`) que `#/servidor`, `#/ajustes`, `#/piloto`, `#/experimentos`, `#/biblioteca` y `#/errores`
acaban en `#/` y que el menú es exactamente: `#/nuevo #/ #/subir #/videos #/guiones #/calendario #/tablero
#/competencia #/canal #/estadisticas #/gasto #/voces #/cuenta`. Los 403 que el servidor real da a un socio
(`/api/video/<v>/pilot`, `/api/voices/credits`) se listan aparte y no cuentan como error.

## weight.js: peso en la red

    node weight.js --base http://127.0.0.1:8099 [--route "#/"] [--partner]

Contexto con caché; `/api` y `/files` se contestan con el mock por CDP `Fetch` (no con `page.route`, que apaga la
caché). Carga, recarga, y por cada documento/estático: estado, bytes sin comprimir, lo que pesaría con
`zlib.gzipSync`, bytes transferidos en la primera carga y en la recarga (y de dónde: red, 304, caché), y las
cabeceras Cache-Control / ETag / Last-Modified / Content-Encoding / Vary. Al final, JSON con `totals`:
`firstLoadTransfer`, `repeatLoadTransfer` (medidos), `firstLoadIfGzip` (cuerpos gzip + 250 B de cabeceras por
archivo), `repeatLoadIfGzip` (si además se pudiera revalidar: 250 B por archivo con ETag/Last-Modified/max-age, 0 si
salió de caché, el gzip entero si es `no-store`). El navegador envía `Accept-Encoding: gzip, deflate, br, zstd`.

## mock.js

    const mock = require("./mock");
    const h = await mock.install(page, {partner: false, origin: "http://127.0.0.1:8099"});
    // h.state (mutable), h.unmocked, h.denied, h.blocked · globales: mock.unmocked, mock.denied, mock.blocked
    mock.answer(state, method, url, body, who)   // núcleo sin transporte → {status, contentType, body} | null

- Datos en `mock-data.js`, con PRNG sembrado; lo único que cambia entre ejecuciones es «hoy» (fechas relativas) y
  los textos «desde hace N min».
- 30 canales (27 propios + `gimnasia-br`, `aviones-br`, `historia-rara-en`), 300 vídeos: 3 haciendo, 40 en cola
  (9 con `lastError`, 6 con `quotaWait`, 10 con etapas hechas, 3 generando voz), 12 con error (cada categoría de
  `explain()` + el genérico), 5 incompletos, 4 en pausa, 66 hechos sin subir, 154 subidos, 16 archivados; 26 % Shorts.
- El calendario es un port de `agenda.plan()` (28 días; 60 para fechas de subida y tablero): 342 huecos de
  publicación, 225 sin vídeo. `/api/upload/dates` añade 4 atrasados y 3-4 para hoy.
- GET modelados: session, overview, upload, upload/dates, agenda, scripts, board, radar, stats, spending, gasto,
  proxy, servidor, doctor, settings, notify, users, voices, voices/credits, voices/search, cuenta, search, library,
  library/<key>, piloto, experimentos, tiempos, ytbench, scenebench, errors, mychannel/<canal>, apertura/<token>,
  video/<slug> (+ repeticion, porque, pilot, exportar, capcut), review/<slug>, decisions/<slug>, factura.csv, copia.
- POST: todos los que llama la interfaz devuelven lo que la página espera; cambian el estado en memoria: agenda,
  settings, users, voices, ideas/save, board/idea, review, decisions, experimentos, queue/retry-all,
  mychannel/handle y video/<slug>/{retry,hold,unhold,stop,archive,redo,published,channel}.
- `partner: true` → sesión `{authorised: true, partner: "marc"}`, canales `ajedrez, coches, simulacion-trafico,
  trenes, volcanes`; mismos filtros que `partner_*` de web.py y 403 `{error: "No disponible"}` para lo demás.
- `/api` no modelado → `{}` y queda en `unmocked`.
- Imágenes (`/files/**`, `…/frame…`, `…/preview`, `*.jpg|png|webp`, i.ytimg.com, yt3.ggpht.com, cualquier imagen
  externa) → SVG 16:9 (cuadrado para avatares). `.mp4/.mp3` → 204. Lo demás externo se aborta (`blocked`).
- `alert/confirm/prompt` se anulan en la página (shoot.js).

## Slugs y claves de las rutas con parámetro

| Para | Valor |
|---|---|
| vídeo haciéndose | `delorean` |
| vídeo en cola con `lastError` + `retryAt` | `pegaso-z102` |
| vídeo con error (Traceback) | `saab-quiebra` |
| vídeo hecho sin subir (vídeo, miniaturas, Shorts, 4 doblajes, piloto, zips) | `citroen-ds` |
| vídeo subido (curva «¿Por qué funcionó?», retención) | `lancia-stratos` |
| `#/revisar/…` (60 planos) y `#/decisiones/…` (12 planos) | `citroen-ds` |
| `#/biblioteca/…` | `niki-lauda` |
| `#/buscar/…` | `dingos` |
| socio | `marc` |

Los cinco vídeos están en `coches` (canal del socio): las mismas rutas sirven en los dos modos.

## Lo que no es fiel del todo

- **Tamaño del calendario**: con ~300 vídeos, `/api/agenda` pesa ~140 KB y la página ~5.000 nodos; en producción
  se midieron ~3.800 nodos y 69 KB. La diferencia son los 269 vídeos listados y las `<option>` de «Poner otro…».
- `/api/upload/dates` con días pasados: el servidor real planifica desde hoy; los «atrasados» están puestos a mano.
- Flujos con trabajos en marcha (`job.running`), el reproductor de YouTube de «clip de apertura» (se aborta
  `youtube.com/iframe_api`), subidas por XHR y descargas: contestan algo válido pero no se recorren.
- `/api/voices/search`, `/api/voices/credits`: forma deducida del JS (la real viene de GenAIPro).
- Textos de `diagnosis`, `log`, `audit`, etc.: verosímiles, no copias de un vídeo real.
- Hora del servidor: el mock usa UTC para «hoy»; el servidor real, la hora local.

## El editor con un proyecto de verdad (fixture_editor.py)

El editor (`/editor/<slug>/`) no se puede simular con `mock.js`: necesita un montaje, clips y la voz. Este script
crea un estudio pequeño en una carpeta temporal (enlaza la configuración, `remotion/`, `templates/` y `node_modules`
del repositorio) con dos vídeos: «demo-editor» (25 s, 10 planos de vídeo generado con ffmpeg, una foto, un capítulo,
un gráfico, un rótulo y un barrido) y «demo-largo» (25 min, 600 planos, para medir). Con un puerto, lo sirve:

    python tests/ui/fixture_editor.py /tmp/estudio-prueba 8097
    # http://127.0.0.1:8097/#/editor/demo-editor

Para comparar el reproductor con el render de Remotion en unos fotogramas:

    npx remotion bundle remotion/index.ts --public-dir=/tmp/estudio-prueba/work/demo-editor --out-dir=/tmp/bundle
    npx remotion still /tmp/bundle Documentary /tmp/f180.jpg --props=/tmp/estudio-prueba/work/demo-editor/timeline.json \
      --frame=180 --browser-executable=/opt/pw-browsers/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell

El Chromium de Playwright no trae el códec H.264: el reproductor del editor avisa «MEDIA_ELEMENT_ERROR» al
reproducir los mp4 (en Chrome de verdad no pasa). Los fotogramas parados sí se ven.
