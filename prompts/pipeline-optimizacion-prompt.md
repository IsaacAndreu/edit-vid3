# Prompt: fiabilidad y velocidad del pipeline de vídeos

Pega todo lo que hay debajo de la línea en una sesión nueva sobre este repositorio.

---

Vas a mejorar el pipeline de vídeos de este repositorio (`edit-vid3`) en dos frentes, por este orden de
importancia: que **ninguna noche se pierda** por una descarga, un proxy o un proceso colgado, y que **cada vídeo
tarde lo menos posible** de guion a `video-final.mp4`. El resultado visual y sonoro de los vídeos no debe cambiar.

Este documento sale de una auditoría de solo lectura del repositorio (noviembre de 2026). Los hallazgos llevan
archivo y línea, pero las líneas se mueven: localiza siempre por nombre de función y confirma en el código antes
de tocar. Si un hallazgo ya no es cierto, sáltalo y dilo en el resumen.

## Cómo funciona hoy (lo mínimo para orientarte)

- Un servidor (VPS Ubuntu, sin gráfica por defecto) corre `python main.py --vigilar` como servicio systemd. La cola
  lanza cada vídeo como subproceso `python main.py --slug <slug>`; hasta `queue.parallel_videos` a la vez, con
  turnos por archivo de bloqueo (`pipeline/locks.py`): `red` (sourcing, ingest) y `cpu` (align, fallback, render).
- Las etapas son una lista estrictamente en serie, `STAGES` en `pipeline/runner.py`: factcheck → align → planner →
  sourcing → analysis → judge → ingest → people → fallback → coldopen → timeline → qa → render → shorts → package.
  Cada una se salta si su marcador `work/<slug>/.stages/<etapa>.json` coincide con la huella de sus entradas.
- Las descargas de YouTube están aisladas en `pipeline/sourcing/youtube.py` (yt-dlp por API de Python). Hay cuatro
  vías: directa, proxy de casa por Tailscale (`scripts/casa/proxy_youtube.py`), varios proxies de casa, y proxy
  residencial de pago por GB con sesión fija por vídeo (`pipeline/sourcing/proxy_sessions.py`). `docs/VPS.md`
  (apartados 3d-3f) explica cada una y por qué existe cada regla; léelo entero antes de tocar descargas.
- El render (`pipeline/render.py`) es híbrido: el metraje sencillo lo compone ffmpeg por segmentos; lo que lleva
  rótulos, gráficos o transiciones pasa por Remotion (CLI, `npx remotion bundle` + `render`) en una sola pasada
  «condensada»; luego se une todo sin recodificar y se hacen pasadas enteras de doctor, look, subtítulos y comprobaciones.
- Los vídeos Atlas, simulaciones y accidentes aéreos se dibujan enteros en Remotion (`pipeline/atlas_guion.py`,
  `remotion/atlas/`, `remotion/sim/`).

Lee también `CLAUDE.md` (reglas del repo: `npm run typecheck` antes de cada commit; nada de datos inventados),
`README.md`, `config.yaml` (sus comentarios cuentan qué se probó y falló) y `docs/MIGRAR.md` (cómo se lanzan los tests).

## Lo que ya se aprendió en producción y no debes deshacer

Cada una de estas reglas costó una noche. Si una mejora choca con alguna, gana la regla y lo explicas.

- **No subas el ritmo de peticiones a YouTube.** `queue.slots.red: 2` dobló los 429 y los «no eres un bot»;
  `sourcing.parallel: 6` también bloqueó más. Paralelizar está bien cuando el número de peticiones por hora no
  sube (el `Pacer` y el `HourlyBudget` de `pipeline/sourcing/common.py` siguen mandando) o cuando los bytes van a
  hosts que no cuentan (segmentos de un tramo ya extraído, miniaturas de `i.ytimg.com`, bancos de imágenes).
- **Proxy residencial: todo lo de un vídeo por la misma sesión/IP.** Extraer por una IP y bajar por otra dio un 1 %
  de éxito. Las URLs de vídeo están atadas a la IP que extrajo.
- **`web_safari` como único cliente falla todas las extracciones**; se mantiene `[default, web_safari]`.
- **ffmpeg no baja por el proxy residencial** (no entiende su 407): los segmentos HLS los baja el programa.
- Lo que YouTube negó por un proxy de casa **no** se reintenta por otro proxy ni con cuenta; la cuarentena es por IP.
- Un resultado escrito durante una caída del proxy no cuenta como definitivo (`ProxyDown`, notas «no responde»).
- Las claves de `config.yaml` que entran en la huella de una etapa rehacen los vídeos a medias si cambian: los
  valores nuevos van con valor por defecto en el código (como ya se hace, ver comentarios «no se escriben aquí») y
  las que solo afectan a velocidad se añaden a `SPEED_KEYS` en `pipeline/runner.py`.
- Las cookies son de cuentas secundarias y nunca van a git; no añadas nada que las registre o las suba.

## Límites de tu entorno

Trabajas en un contenedor sin los datos del servidor: no hay `work/`, `out/`, `cache/`, claves, proxies ni acceso
fiable a YouTube. Por tanto:

- No hay tiempos reales por etapa en el repo. No inventes cifras de mejora: describe el cambio y cómo medirlo en el
  servidor con `python main.py --tiempos` y `work/*/.stages/*.json`.
- Todo cambio de descargas se demuestra con tests que usan dobles (como hacen `tests/test_residential_*.py` y
  `tests/test_cookie_rotation.py`), nunca contra YouTube.
- Lo que solo puede confirmarse en el servidor (velocidad real, tasa de bloqueos, GB de proxy) queda detrás de una
  opción apagada por defecto, con el comando exacto para que el usuario lo pruebe y lo compare.
- Para el render sí puedes medir aquí: hay storyboards y materiales de ejemplo (`storyboards/`, `materiales/`) y
  Chromium instalado. Antes de dar por buena una optimización de render, renderiza el mismo tramo antes y después y
  compara fotogramas (por ejemplo con el filtro `ssim` de ffmpeg); si no es idéntico o casi (SSIM ≥ 0,99 donde el
  cambio implique recodificar), no entra.

## Forma de trabajar

- Rama: la que te indique la sesión. Un commit por mejora, con mensaje que diga qué problema resuelve.
- Cada mejora lleva su test. `python -m pytest tests -q` y `npm run typecheck` pasan antes de cada commit; si la
  suite ya tenía fallos antes de empezar, apúntalos al principio y no los mezcles con los tuyos.
- Lleva el progreso en `prompts/pipeline-progress.md`: por cada punto, hecho / descartado (por qué) / pendiente de
  probar en el servidor (con el comando). Si la sesión se corta, la siguiente continúa desde ahí.
- Sigue las fases en orden. La 0 y la 1 protegen a las demás: no adelantes trabajo de velocidad hasta tenerlas.
- No cambies el comportamiento por defecto en nada que afecte a peticiones a YouTube, calidad de imagen o gasto;
  esas mejoras entran apagadas y documentadas. Todo lo demás (escrituras atómicas, timeouts, cachés, paralelismo
  local) entra encendido.
- Si un punto resulta inviable o más arriesgado de lo que parece, no lo fuerces: explícalo en el progreso y sigue.

## Fase 0 · Red de seguridad antes de tocar nada

Hoy no hay CI ni configuración de pytest, y el estudio web hace `git pull` de `main` cada 2 minutos: un error de
nombre llegó a producción y paró todos los vídeos con metraje (commit `eaa0c7d`).

1. **El test de nombres indefinidos no se ejecuta.** `tests/test_no_undefined_names.py` hace
   `pytest.importorskip("pyflakes")` y pyflakes no está en `requirements.txt` ni en `scripts/vps/setup-ubuntu.sh`.
   Añade pyflakes y pytest a las dependencias de desarrollo y haz que el test falle, no que se salte.
2. **Test de importación de todo** `pipeline/` y `main.py`, y **una prueba de extremo a extremo con las `STAGES`
   reales** y dobles de red/LLM/TTS/Remotion sobre un vídeo diminuto (`tests/test_runner.py` hoy parchea las
   etapas con falsas, así que no detecta nada de esto).
3. **CI**: `.github/workflows/` con typecheck + pytest en cada push y PR. Y una **puerta antes del despliegue**:
   `web._reload_on_new_code`, la actualización del vigilante en `main.py` y `pipeline/actualizar.py` ejecutan la
   comprobación rápida (pyflakes + importación) sobre el código recién bajado y, si falla, se quedan con el
   anterior y avisan por Telegram.
4. **Medir de verdad.** El marcador de etapa guarda `seconds` sin la espera del turno, solo en éxito, y
   `current.json` se sella antes de coger el turno (`runner.py`, `run_stages`). Guarda también `waitSeconds`, los
   intentos fallidos con su duración, y abre `out/_cola/<slug>.log` en modo añadir. Que `pipeline/tiempos.py`
   muestre espera y trabajo por separado: sin esto no se sabrá si las fases siguientes sirven.

## Fase 1 · Descargas que no fallan ni se quedan colgadas

Todo en `pipeline/sourcing/youtube.py` salvo que se indique.

1. **Tramos truncados que envenenan la caché (lo más grave).** `_cut`, el corte HLS de `_fetch_hls_locally` y el
   remux final de `_fetch_range` escriben directamente en el nombre definitivo, y `_library_range` da por bueno
   cualquier archivo cuyo nombre cubra el tramo. El servicio se reinicia solo tras cada `git pull`, así que un
   ffmpeg matado a medias deja un tramo corrupto que se reutiliza para siempre. Escribe a `.part`, valida con
   ffprobe (duración y pista de vídeo), renombra, y limpia huérfanos al arrancar. Aplica lo mismo a las descargas
   enteras (`wip_<prefijo>`, nombre fijo con cerrojo solo dentro del proceso: dos vídeos se pisan).
2. **Estado compartido entre procesos sin cerrojo.** `.rechazados.json`, `.bots`, los archivos de cuarentena y la
   vuelta de cookies (`origin.tmp`, nombre fijo) se leen-modifican-escriben bajo un cerrojo de hilo y con
   `write_text` no atómico, pero cada vídeo es un proceso. Usa el patrón de `flock` + escritura atómica que ya
   existe en `common.py` (`HourlyBudget`), recarga los rechazos por mtime, y si el JSON está corrupto no lo trates
   como vacío en silencio: registra y conserva una copia.
3. **Plazos en todo.** Sin `timeout`: `_cut`, el remux, los ffprobe, `normalise_video`/`normalise_image`
   (`pipeline/ingest.py`), `_to_mp4` y `storyboard` (`pipeline/sourcing/archive.py`), DuckDuckGo
   (`pipeline/sourcing/images.py`), el cliente del juez (`pipeline/judge.py`). Las descargas enteras no tienen
   plazo total ni detección de estrangulamiento: añade plazo proporcional al tamaño, `throttledratelimit` y
   `fragment_retries` a las opciones de yt-dlp.
4. **Segmentos HLS: reintento, reanudación y paralelo.** `_fetch_hls_locally` baja los segmentos de un tramo uno
   tras otro, sin reintento por segmento, cargando cada uno en memoria, y borra la carpeta de trabajo en cada
   intento. Baja 3-4 a la vez por la misma sesión (son bytes de un vídeo ya extraído, no peticiones nuevas de
   extracción), con 2-3 reintentos por segmento, escribiendo a disco en streaming y conservando los ya bajados
   entre intentos. Cuando una rotación de sesión cambia la IP, re-extrae primero: reintentar las URLs viejas desde
   la IP nueva gasta un intento de pago en un 403 seguro.
5. **Reintento de errores transitorios en casa/directo.** En `_call`, un timeout, un 5xx o una conexión cortada
   acaban en `RuntimeError` y el candidato se pierde; solo la vía residencial reintenta. Añade 2 reintentos con
   espera creciente y aleatoria para esos casos (nunca para «no eres un bot» ni 429, que tienen su propia lógica).
   `_calm_down` y `rate_retries` son código muerto: conéctalos o bórralos.
6. **Esperas con el hueco cogido.** `_call` espera el enfriamiento y el presupuesto horario (`HourlyBudget.take`,
   que puede esperar hasta que cambie la hora) con un hueco de `_slots` ocupado. Espera primero, coge el hueco después.
7. **Errores tragados.** `captions()` devuelve `[]` ante cualquier error sin guardarlo, y se llama por opción y por
   plano: un 429 se vuelve a pedir cada vez. Caché negativa con caducidad corta y una línea de registro. Haz lo
   mismo (al menos registrar) en los demás `except` silenciosos de `youtube.py`, `analysis/__init__.py`
   (`prefetch_sections` y alrededores) y `pipeline/quotes.py`.
8. **Imágenes.** Un único `Pacer(1.0)` para todos los hosts, que duerme con el cerrojo cogido (≈1 imagen/s en
   todo el vídeo), y en `ingest.fetch_image` un cerrojo global alrededor del GET. Un pacer por host, hosts en
   paralelo, reintentos en `download_file`, y captura `RequestException` en `fetch_image`. Serper y la API de
   datos de YouTube (`pipeline/ytapi.py`) no reintentan errores de red, y la API descuenta la cuota antes del GET:
   un reintento y devolución de la cuota si falla.
9. **yt-dlp sin fijar y actualizado a ciegas.** `update_ytdlp()` (`main.py`) hace `pip install -U` al arrancar
   cada cola. Hay que seguir a YouTube, pero con red: guarda la versión que funcionaba, actualiza, lanza la sonda
   de `pipeline/ytcheck.py` y, si la sonda falla con la nueva y pasaba con la anterior, vuelve atrás y avisa.
10. **Ruta antigua.** `pipeline/fetch_media.py` y `pipeline/clients/youtube_client.py` no usan proxy ni caché y
    nada importa `fetch_media`. Confirma que no se usan y retíralos, o márcalos claramente como obsoletos.

## Fase 2 · Una cola que no pierde vídeos ni noches

1. **Un vídeo a medias figura como terminado.** `housekeeping.is_done` es «existe `video-final.mp4`», y
   `render._render` mueve el archivo a ese nombre en `join` antes del doctor, el look, los subtítulos y las
   comprobaciones finales. Un corte ahí, o un fallo en shorts o package, deja el vídeo «hecho» para siempre.
   Renderiza a un nombre temporal y renombra tras las comprobaciones; `is_done` exige además el marcador de la
   última etapa (ojo con los vídeos ya subidos y limpiados: `REMOVED` sigue valiendo).
2. **Cortacircuitos en los dos modos de cola.** La pausa por bug repetido (commit `294c95d`) solo existe en
   `run_parallel`, exige la misma línea de error y no cubre `KeyError`, `IndexError`, etc.; llévala también al
   bucle secuencial y agrupa por tipo de excepción + archivo:línea, más «N fallos seguidos en la misma etapa».
   Al revés, `out_of_credit` y `BudgetReached` solo se tratan en el bucle secuencial: en paralelo, una clave
   muerta o el tope de gasto marcan ERROR todos los vídeos uno tras otro, retenidos 6 h cada uno.
3. **Perro guardián que mata, no solo avisa.** El latido lo escribe un hilo aparte (prueba que el proceso vive, no
   que avanza), y `run_parallel` lee la salida del hijo sin plazo. Añade plazo por etapa en `run_stages`
   (generoso, configurable, proporcional a la duración del vídeo), timeouts en `render._run` y
   `Renderer.remotion`, y corte del hijo si lleva demasiado sin escribir nada. Un vídeo cortado así queda como
   fallo reintentable, con la etapa y el tiempo en el aviso.
4. **Estado que sobrevive a un reinicio.** `out/_vigilar.json` se guarda al final de la ronda; guárdalo tras cada
   resultado. Pasa `new_code` a `run_parallel` para que el vigilante se reinicie con el código nuevo. En
   `scripts/vps/install-service.sh`, `KillMode=mixed` y un `TimeoutStopSec` que deje cerrar bien los hijos.
5. **Preflight completo.** `preflight()` (`main.py`) mira claves, disco, binarios y un GET directo a youtube.com;
   no mira importaciones, clave de voz, proxy configurado, Chrome/`node_modules` ni la forma de la configuración.
   Reutiliza las comprobaciones de `pipeline/chequeo.py` (`--doctor`), que la cola nunca llama, y añade una
   comprobación barata por vídeo antes de que sourcing empiece a gastar proxy.
6. **Topes de gasto por defecto.** `budget.daily_usd` y `budget.proxy_gb_per_day` valen 0 (sin tope), y
   `per_video_usd` solo se mira entre etapas. No cambies los valores por tu cuenta: propón valores en el resumen y
   añade la comprobación dentro de judge y fallback, que es donde se gasta.

## Fase 3 · Menos bytes y menos esperas en las descargas

1. **Doble codificación de cada tramo.** Los tramos HLS se recodifican con x264 crf 16 al cortarlos (también las
   ventanas de análisis a 360p, que nadie va a ver) y otra vez en `normalise_video`. Une los segmentos sin
   recodificar y deja que el corte exacto lo haga `normalise_video`; para las ventanas `a360` nunca crf 16.
   Comprueba que el corte sigue siendo exacto al fotograma.
2. **Re-extracciones evitables por el proxy residencial** (≈2,9 MB cada una). `_fresh_full_info` exige la misma
   sesión viva (28 min), así que un ingest que llega más tarde que el análisis re-extrae cada vídeo elegido, y
   además borra `info.json`, con lo que se recalculan miniaturas y filtros. No borres `info.json` cuando solo han
   caducado las URLs, y estudia bajar el tramo HD de los finalistas mientras la sesión de su análisis sigue viva
   (detrás de una opción: cambia cuántos bytes se piden).
3. **Mismo trabajo repetido en el análisis.** `fine_options` (`pipeline/analysis/__init__.py`) recalcula
   fotogramas, CLIP, escenas, OCR y caras por cada par (plano, ventana) y abre el vídeo varias veces por ventana.
   Calcula los rasgos una vez por ventana, guárdalos, y puntúa por plano; mueve ese cálculo a los hilos que ya bajan.
4. **Detalles y búsquedas en serie por plano** (`youtube.py`, bucles de candidatos y de consultas). Solo si el
   número total de peticiones no cambia: 2-3 a la vez respetando el pacer. Si no puedes garantizarlo, déjalo.
5. **Ingest**: `-ss` antes de `-i` con un pre-roll corto en vez de decodificar desde el principio, un solo
   `probe` por clip (hoy dos más `cropdetect`), y mismo `-g`/timescale que los segmentos finales.
6. **Experimento, apagado por defecto: bytes de vídeo directos tras extraer por el proxy.** Hoy no existe ninguna
   separación «extracción por proxy / bytes directos» y el código afirma que las URLs van atadas a la IP. Si fuera
   viable para algún tipo de recurso (subtítulos, por ejemplo) sería el mayor ahorro de GB, pero no está
   demostrado y lo más probable es que para el vídeo no lo sea. No lo implementes como ruta de producción: escribe
   una sonda (junto a `pipeline/ytbench.py`) que el usuario lance en el servidor y que diga, con un vídeo de
   prueba, qué recursos responden directos y cuáles dan 403.
7. **Turno `red` por etapa entera.** Con `red: 1`, un segundo vídeo de metraje espera todo el sourcing del
   primero. El pacer y el presupuesto por hora ya son compartidos entre procesos, así que en teoría el turno
   sobra; en la práctica `red: 2` dobló los bloqueos. No lo cambies por defecto: añade una opción para soltar el
   turno durante el trabajo que no toca la red (CLIP, cortes locales) y deja escrito cómo comparar bloqueos antes
   y después con `python main.py --youtube-stats`.

## Fase 4 · Render más rápido sin cambiar un píxel

Todo en `pipeline/render.py` salvo que se indique. Compara fotogramas antes y después en cada punto.

1. **Se empaqueta Remotion 6-10 veces por vídeo.** `Renderer.remotion` borra y recrea `public/` y `bundle/` en
   cada llamada (fotogramas de prueba, audio de simulación, pasada condensada, insignias, fondo, pantalla final,
   cada Short, miniaturas). Empaqueta una vez por firma del código (`_remotion_sig`), guárdalo en la caché global y
   cambia solo el `public/` de cada trabajo, con carpetas por trabajo para que dos renders puedan solaparse (hoy
   no pueden). `_remotion_sig` relee 177 archivos en cada llamada: memorízalo por proceso.
2. **Los segmentos de ffmpeg esperan a Remotion sin necesitarlo.** El pool de segmentos rápidos arranca cuando
   acaba la pasada de Remotion. Lánzalos a la vez (necesitan las insignias antes), repartiendo núcleos con
   `-threads` para no pelearse con Chrome.
3. **La pasada condensada es un bloque único.** Un fallo al 90 % la rehace entera, y cualquier cambio de un rótulo
   también. Renderiza por tramos con `--frames`, cada uno con su clave, 2-3 procesos a la vez según núcleos. Trae
   reanudación y re-render incremental tras retoques en el editor.
4. **Claves de caché demasiado anchas.** La clave del render incluye todo `remotion/` y todo el props: tocar
   `remotion/atlas` invalida el render, las insignias, el fondo y la pantalla final de todos los vídeos de
   metraje a medias. Limita la huella a los archivos alcanzables desde cada composición (`render.inputs`,
   `_remotion_sig`). Las huellas de etapa releen directorios enteros en cada comprobación (`runner.py`): cachea
   los resúmenes por tamaño + mtime.
5. **Subtítulos y look: una recodificación entera de más.** `subtitulos.burn` recodifica toda la película tras el
   montaje, y se llama sin `encoder`, así que usa libx264 aunque NVENC esté activo. Paso seguro: pásale el
   codificador del render. Paso mayor: meter subtítulos y look en el grafo de filtros de cada segmento, para
   quitar una generación de pérdida y una pasada completa.
6. **Comprobaciones finales en varias pasadas.** `doctor.detect` (dos veces si arregla algo), `ritmo.activity` y
   `ritmo.loudness` (dos decodificaciones), `simulacion.qa`, hoja de gráficos. Una sola decodificación con varias
   salidas, en paralelo con el quemado de subtítulos. La mezcla de audio corre dos veces para el loudnorm de dos
   pasadas: mide con una pasada ligera y aplica en la segunda.
7. **Shorts nativos**: cada uno empaqueta por su cuenta, renderiza con el preset por defecto de Remotion y se
   recodifica después; los tres van en serie (`pipeline/shorts.py`). Un solo paquete, intermedio
   `ultrafast`/crf 12 como en el render principal, y en paralelo.
8. **Doblajes**: `pipeline/dub.py` rehace QA, render, shorts y package en `work/<slug>-<idioma>/render` porque la
   caché de segmentos es por carpeta de trabajo. Llévala a la caché global con clave por contenido.
9. **Vídeos dibujados** (Atlas, mapas): `Atlas.tsx` y `MapStory.tsx` reconstruyen `geoPath` sobre los datos del
   mundo en cada fotograma, sin `useMemo`; `rivers.json` (1,66 MB) va dentro del paquete. Memoriza las capas
   estáticas. `pipeline/atlas_guion.py` empaqueta desde el código cada vez, sin concurrencia ni preset, y
   `scripts/atlas/stills.ts` vuelve a empaquetar y abre un navegador por fotograma: reutiliza paquete y navegador.
   Aquí aplica el bucle visual de `CLAUDE.md` (fotogramas contra `referencias/atlas/frames/`).
10. **Nada de red durante el render.** Hoy puede dispararse `npm install` dentro del render, la descarga de Chrome
    si falta `/opt/pw-browsers`, y la del modelo YuNet en su primer uso. Muévelo al preflight de la fase 2: detrás
    de un proxy esas descargas son cuelgues en mitad de la noche.

## Fase 5 · Etapas en paralelo

1. **`people`** solo depende de `shots.json` y espera detrás de sourcing, analysis, judge e ingest; además el juez
   lee `people.json`, que en la primera pasada aún no existe. Ejecútala junto a sourcing (sus búsquedas de fotos
   no van a YouTube) y decláralo en `judge.inputs`.
2. **`factcheck`** no alimenta ninguna etapa: en paralelo con align y planner.
3. **`package`** (títulos y miniaturas) no necesita render ni shorts: a la vez que el render, cuidando que no
   compitan dos renders de Remotion (para eso sirve el punto 1 de la fase 4).
4. **Voces**: `tts.prepare_all` hace una narración cada vez, y dentro de cada una los trozos se crean, esperan y
   bajan uno tras otro (`pipeline/tts.py`). Crea todas las tareas y luego espera y descarga en paralelo, con un
   tope por proveedor configurable; conserva los trozos en caché tras el éxito (hoy se borran).
5. **`align` ocupa un turno `cpu`**: dos minutos de Whisper esperan detrás de dos renders. Dale su propio hueco y
   limita sus hilos (`pipeline/whisper_local.py` usa todos los núcleos); prueba el filtro VAD solo si la
   alineación con el guion da el mismo resultado.

Para expresar esto en el runner, añade dependencias declaradas a `Stage` y ejecuta en paralelo las que no dependen
entre sí, sin cambiar el formato de los marcadores ni invalidar los vídeos a medias.

## Al terminar

Deja en `prompts/pipeline-progress.md` y en tu mensaje final, por fase: qué entró y con qué test; qué descartaste
y por qué; qué queda apagado a la espera de una prueba en el servidor, con el comando y qué número mirar; y
cualquier fallo de la suite que ya existiera. Actualiza `docs/VPS.md` y `README.md` donde el comportamiento haya
cambiado (entre otras cosas, `docs/VPS.md` dice que el PO Token añade el cliente `mweb` y el código no lo hace por
defecto; `pipeline/README.md` describe una línea de comandos que ya no existe).
