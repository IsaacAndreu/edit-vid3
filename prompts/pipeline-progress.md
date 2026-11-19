# Progreso: fiabilidad, puntería y velocidad del pipeline

Plan: el prompt «fiabilidad, puntería y velocidad del pipeline de vídeos» (noviembre de 2026). Estados:
**hecho** (con su test), **descartado** (por qué), **apagado: probar en el servidor** (con el comando y qué mirar),
**pendiente**.

Suite antes de empezar (18-11-2026): 922 verdes, 1 fallo previo
(`tests/test_analysis.py::FineTests::test_best_span_inside_one_scene_in_source_seconds`: al doble de detectores le
faltaba `text_edges`; arreglado en el primer commit, era del test, no del código).

## Bloque 1 · Fase 0 (red de seguridad)

| Punto | Estado | Test |
|---|---|---|
| 0.1 pyflakes obligatorio | hecho: `pyflakes` en `requirements.txt` (lo usa la puerta), `pytest`+`pyflakes` en `requirements-dev.txt`, `pytest.ini`, el test ya no se salta | `tests/test_no_undefined_names.py` |
| 0.2 importación de todo | hecho: dentro de la comprobación rápida (`python -m pipeline.puerta`) | `tests/test_puerta.py::test_the_real_code_passes_the_quick_check` |
| 0.2 extremo a extremo con las `STAGES` reales | hecho: 5 escenarios (acepta, rechaza, descargas, sin material, mínimo) + 9 casos de `apertura.run_request`; ramas cubiertas: apertura 89 %, coldopen 81 %, fallback 74 %, shorts 85 %. Encontró el fallo de `protagonist-photo`. **Tarda ~5 min** (ffmpeg real a 1080p): la CI lo lleva; para ir rápido en local, `--deselect tests/test_e2e_stages.py` | `tests/test_e2e_stages.py` |
| 0.3 CI | hecho: `.github/workflows/tests.yml` (typecheck, comprobación rápida, pytest) | — |
| 0.3 puerta antes del despliegue | hecho: `pipeline/puerta.py`; el estudio, la cola (`_git_update`) y `--actualizar` hacen `git fetch`, comprueban el commit nuevo en una carpeta temporal (pyflakes + importar) y solo entonces `merge --ff-only`. Si falla: se quedan con el código anterior, Telegram, y el commit malo queda en `out/_puerta.json` | `tests/test_puerta.py` |
| 0.4 medir de verdad | hecho: el marcador guarda `waitSeconds`, `failedAttempts`, `failedSeconds`; cada intento fallido va a `.stages/<etapa>.fallos.jsonl`; `current.json` dice `waiting` mientras espera turno; `out/_cola/<slug>.log` en modo añadir; `--tiempos` separa trabajo, espera e intentos fallidos y muestra el trabajo perdido en vídeos sin terminar | `tests/test_tiempos_esperas.py` |

En el servidor: `python main.py --tiempos 7` tras unos días con el código nuevo (las columnas de espera e intentos
fallidos solo tienen datos de los marcadores escritos desde ahora).

## Bloque 2 · Fase 1, puntos 1-3

| Punto | Estado | Test |
|---|---|---|
| 1.1 tramos que no envenenan la caché | hecho: `pipeline/fileio.py`; todo se escribe a `.part<pid>-<hilo>-<nombre>`, se valida con ffprobe y se renombra; los tramos antiguos sin sidecar se validan una vez; descargas enteras con nombre por proceso y `flock` por vídeo; limpieza de huérfanos al arrancar | `tests/test_fileio.py` |
| 1.2 estado compartido entre procesos | hecho: rechazos, `.bots`, cuarentena, vuelta de cookies, `ytdlp-info.json`, player JS y sesiones del proxy con `flock` + escritura atómica; rechazos recargados por mtime; JSON roto apartado como `.corrupto-<fecha>` | `tests/test_fileio.py` |
| 1.3 plazos en todo | hecho: ffprobe/ffmpeg de ingest y archive, clientes de OpenAI, DuckDuckGo; descargas enteras con `throttledratelimit`, `fragment_retries` y plazo total proporcional al tamaño | `tests/test_fileio.py::test_whole_downloads_carry_a_deadline_and_crawl_detection` |

## Bloque 3 · «Lo que dicen estos datos» 1-10

| Punto | Estado | Test |
|---|---|---|
| 1 errores de programación tardíos | puerta + CI (bloque 1) + prueba de extremo a extremo | `tests/test_e2e_stages.py` |
| 1 planner con JSON inválido | hecho: `llm.parse_json_reply` repara bloque ```json, texto alrededor, saltos de línea crudos y coma final; el bucle del esquema toma un JSON inválido como un intento más | `tests/test_llm_json.py` |
| 1 «no hay transcriptor» con la clave puesta | hecho: causa encontrada, `atlas_guion.make_in_queue` (la vía de la cola) no pasaba transcriptor; solo `--atlas-guion` lo hacía | `tests/test_atlas_guion.py::test_the_queue_passes_a_transcriber_when_the_key_exists` |
| 1 «2 validation errors for Timeline» en doblajes | hecho, **causa probable** (sin el log del servidor): con una voz más corta, paneles y rótulos del final quedaban con duración negativa, y el último clip de terceros podía pasar de 5 s. Confirmar con el log del doblaje si vuelve a pasar | `tests/test_dub.py::test_retime_output_always_validates_as_a_timeline` |
| 2 «otros» con causa | hecho: toda fila fallida lleva `detail` y `cause` (`error_cause`); `--youtube-stats` muestra causas, también de filas antiguas; los vídeos ya descartados lanzan `Refused` y no escriben fila; túnel sin código = transitorio, otra sesión | `tests/test_error_causes.py` |
| 3 por qué no HLS | instrumentado: cada tramo lleva `route` y `notHls`. **Pendiente de un dato del servidor**: `python -m pipeline.diag_hls 7` (sin red; escribe `out/_diag_hls.md`) dice si las extracciones en caché traen m3u8 y si la selección de yt-dlp las encuentra; y tras unos días con el código nuevo, la línea «Por qué no fue HLS» | `tests/test_hls_route.py` |
| 3 tramos por rango de bytes | **apagado, probar en el servidor**: `sourcing.youtube.byte_ranges: true` en `config.local.yaml` y un vídeo; mirar en `--youtube-stats` «download (rango)», GB por vídeo terminado y «Material descartado»/notas «sin HLS» (deberían bajar) | `tests/test_byte_ranges.py` |
| 4 ritmo por sesión | **apagado, probar en el servidor**: `pace_per_session: true` (con `session_min_interval: 2.0`, `session_concurrency: 1`, `proxy_connections_max: 6`); comparar con `python main.py --youtube-stats 2` antes/después: % de fallidas, bot y 429 por hora, esperas. Ojo: `requests_per_hour` (presupuesto horario) sigue mandando | `tests/test_session_pace.py` |
| 5 429 de `get` | hecho: eran los subtítulos (timedtext): ritmo propio (`captions_min_interval` 3 s) y caché negativa (`captions.fallo.json`, 30 min tras 429) | `tests/test_captions_negative.py` |
| 6 metadatos | `youtube.com/` = la portada que yt-dlp baja para la configuración de `web_safari` en cada extracción. **Apagado, sonda**: `python -m pipeline.sonda_ytcfg` y, si dice «se puede encender», `player_skip: [configs]`. El filtrado con la API ya existía (`passes_search_filters`, `unplayable`). Bajar candidatos por plano: pendiente de los datos del bloque 4 | `tests/test_player_skip.py` |
| 7 análisis en HD | **apagado**: `analysis.hd_windows_top: 1`; comparar `--youtube-stats` (archivo a360 + archivo hd: MB y minutos) y la duración de analysis + ingest en `--tiempos` | `tests/test_analysis_adaptive.py::test_hd_windows_top_brings_the_best_windows_in_hd` |
| 8 vídeos «no disponibles» | hecho: `no-disponible` en `.rechazados.json`, ninguna etapa lo vuelve a pedir; una petición sin HLS de un vídeo no se reintenta en el mismo proceso | `tests/test_gone_videos.py` |
| 9 aviso de proxy de pago | hecho: `proxy_down_text`; las notas siguen sin contar como definitivas, ahora también «no pudo abrir el túnel» | `tests/test_proxy_down_text.py` |
| 10 render | pendiente (fase 4, después de los bloques 1-4) | — |

También entró aquí la fase 1.6 (esperas sin hueco cogido), porque tocaba el mismo bloque de `_call`.

## Bloque 4 · «Que el clip sea de lo que se está contando» 1-9 y «Contenido sin topes fijos»

| Punto | Estado | Test |
|---|---|---|
| 1 `protagonist-photo` | hecho (también lo encontró la prueba e2e) | `tests/test_fallback_methods.py` |
| 2 medir antes de tocar | hecho: `Selection.judgeRank/pickedBy/thumbnailsOnly/alternatives`, `FallbackItem.judged`; el manifiesto ya no deja `decidedBy` nulo (`heredado:<plano>` u `otro:<carpeta>`); tabla «De dónde salió cada plano» en `diagnostico.md` y por canal en `--informe-analisis` | `tests/test_origen.py` |
| 3 búsqueda | hecho: con API, suceso + la búsqueda más concreta (la del momento primero); 30 resultados por búsqueda de la API (mismo coste); orden por nombre completo, suceso y año en título/descripción. **Apagado**: `api_local_query` (+100 unidades/plano) | `tests/test_search_aim.py` |
| 4 momento dentro del vídeo | hecho: miniaturas una cada 6 s hasta 120 (solo CPU). **Apagado**: `analysis.chapter_windows` (una descarga más donde casa un capítulo). **Pendiente**: localizar por subtítulos en todos los planos con la narración traducida (necesita traducir la narración con el LLM y más peticiones de subtítulos: hay que decidir el coste) | `tests/test_analysis_adaptive.py` |
| 5 texto de CLIP | hecho: momento + intención visual, sin búsquedas ni nombres (`analysis.clip_queries: true` vuelve a lo de antes). **Probar en el servidor** otro modelo: `analysis.model`/`pretrained` en un canal y comparar «primera elección del juez» en `--informe-analisis` | `tests/test_judge.py` |
| 6 juez | hecho: miniaturas distintas; error de API → reintento y relleno (`judge.on_error`); continuación solo de segundos vistos (`continue_unseen`); hoja + contexto guardados; `python -m pipeline.rejuzgar <vídeo> <modelo>`. **Apagado**: `frames_per_candidate`, `tile_width`, `model_hook` | `tests/test_judge.py`, `tests/test_judge_sheets.py` |
| 7 relleno | hecho: primero las opciones que el juez ya aceptó (sin llamada). **Apagado**: `fallback.judge_pexels`, `fallback.judge_filler`. `rounds_rest` sigue en 1 hasta ver la tabla | `tests/test_fallback_methods.py` |
| 8 planner | hecho: instrucciones de búsqueda para cualquier tema, con ejemplos de seis tipos de canal; no rehace vídeos planificados | `tests/test_planner.py` |
| 9 cuota | hecho: `api_overflow: mixto` (apagado: el valor por defecto sigue «esperar»). La caché de búsquedas ya era global. **Pendiente**: `playlistItems` para canales de confianza; medir `scene_search` con `--comparar-escenas` | `tests/test_api_overflow.py` |
| Sin topes fijos | los topes de GB y los filtros ya se pueden poner por canal y por vídeo (capas de `RunContext.create`). Tabla «Material descartado» en `diagnostico.md`. **No hecho**: el límite de 5 s (`MAX_THIRD_PARTY_SECONDS`) sigue fijo: lo usan 29 sitios, incluidas las validaciones de `Timeline` y `Selection`, que no ven la configuración; hacerlo configurable exige pasar el límite por el esquema y es arriesgado para los vídeos a medias. Documentado en `docs/VPS.md` 3h | `tests/test_descartes.py` |

## Bloques 5-6 · resto de fase 1, fases 2-5

| Punto | Estado | Test |
|---|---|---|
| 1.4 segmentos HLS | hecho: 3 a la vez por la misma sesión (`hls_segment_workers`), 2 reintentos por segmento (`hls_segment_retries`), a disco en streaming, se conservan los ya bajados al renovar enlaces, y si la sesión cambió de IP se re-extrae antes de pedir | `tests/test_hls_local.py` |
| 1.6 esperas sin hueco cogido | hecho (bloque 3) | `tests/test_session_pace.py` |
| 2.1 vídeo a medias «terminado» | hecho: el render trabaja sobre `.video-final.render.mp4` y renombra tras el postflight; marca `out/<slug>/.haciendo` desde el render hasta la última etapa; `is_done` la exige ausente (los vídeos antiguos sin marca siguen hechos) | `tests/test_done_only_when_finished.py` |
| 2.2 cortacircuitos | hecho: en los dos modos de cola; bug = tipo + archivo:línea; `queue.breaker_same_stage` (3) fallos seguidos en una etapa; en paralelo «sin saldo / clave muerta» (salida 77) y «tope de gasto» (78) paran los arranques | `tests/test_cortacircuitos.py` |
| 1.5 reintentos pasajeros en casa/directo | hecho: 2 reintentos con espera aleatoria (`transient_retries`), nunca ante bot/429; `_calm_down` conectado al primer 429; `rate_retries` (muerto) fuera | `tests/test_transient_retries.py` |
| 1.7 except silenciosos | hecho: dejan una línea en el registro (youtube.py, análisis, citas); los subtítulos ya tenían caché negativa | — |
| 1.8 imágenes y APIs | hecho: un ritmo por host (`HostPacers`; Wikimedia 1 s, el resto 0,25 s, en paralelo), sin cerrojo global; `download_file` y `fetch_image` reintentan; Serper reintenta; la API de YouTube reintenta y devuelve la cuota | `tests/test_images_and_api_retries.py` |
| 1.9 yt-dlp con vuelta atrás | hecho: sonda tras cada versión nueva, vuelta a la anterior si la nueva falla y la vieja no, versión mala recordada (`out/_ytdlp.json`); `youtube_update_probe: false` la apaga | `tests/test_ytupdate.py` |
| 1.10 ruta antigua | hecho: `fetch_media.py` retirado (nadie lo importaba); `third_party_media`, `candidate_analyzer` y `clients/youtube_client` marcados obsoletos | — |
| 2.3 perro guardián | hecho: corta la etapa que pasa de `queue.stage_minutes` (360) + 20 min por minuto de vídeo, o el proceso que lleva `queue.silent_minutes` (180) sin escribir con una etapa en marcha; plazos en `render._run`, el bundle y el render de Remotion | `tests/test_guardian.py` |
| 2.4 estado y reinicio | hecho: `out/_vigilar.json` tras cada vídeo; la cola en paralelo mira el código nuevo cada 2 min; al parar se cierran los procesos de vídeo; `install-service.sh` con `KillMode=mixed` y `TimeoutStopSec=120` (**hay que volver a ejecutarlo en el servidor**) | `tests/test_guardian.py` |
| 2.5 preflight | hecho: `pipeline/preflight.py` (importación, config, herramientas, Remotion; avisos de perfiles rotos, voz, navegador, proxies) y comprobación por vídeo antes de la primera etapa de pago | `tests/test_preflight_checks.py` |
| 2.6 topes de gasto | hecho: `budget.guard` antes de cada hoja del juez y cada plano del relleno, con el gasto de este intento. **Propuesta de valores** (no cambiados): `budget.daily_usd: 15`, `budget.proxy_gb_per_day: 25` (≈3 vídeos de metraje con los 8,6 GB por vídeo terminado de la semana), `per_video_usd` sigue en 1,5 | `tests/test_budget_guard.py` |

## Fases 3-5 · el motor (19-11-2026)

| Punto | Estado | Test |
|---|---|---|
| 3.1 doble codificación | en parte: las ventanas a360 ya no van a crf 16 (crf 26, ultrafast). **No hecho**: unir los segmentos HD sin recodificar y dejar el corte a `normalise_video` (cambia los píxeles de los clips finales: hay que medir SSIM con material real) | `tests/test_hls_route.py` |
| 3.2 re-extracciones | pendiente: no borrar `info.json` cuando solo caducan las URLs | — |
| 3.3 rasgos por ventana en el análisis | pendiente (CPU; el análisis espera sobre todo a las descargas) | — |
| 3.4 detalles y búsquedas en paralelo | descartado: no se puede garantizar el mismo número de peticiones (el bucle para al tener 3 vídeos válidos) | — |
| 3.5 ingest `-ss` antes de `-i` | pendiente (los tramos HD ya empiezan casi en el segundo pedido: poco que ganar) | — |
| 3.6 sonda de recursos directos | hecho: `python -m pipeline.sonda_directo [vídeo]` → `out/_sonda_directo.md`. **Lánzala en el servidor** | `tests/test_sonda_directo.py` |
| 3.7 soltar el turno `red` | pendiente | — |
| 4.1 empaquetar Remotion una vez | hecho: paquete por firma del código en `cache/render/bundles/`, carpeta propia por trabajo (pueden solaparse), `_remotion_sig` memorizado. Comprobado: PNG idéntico byte a byte, 2,1 s frente a 4,7 s por llamada | `tests/test_render_bundle.py` |
| 4.2 ffmpeg sin esperar a Remotion | hecho: la pasada condensada en segundo plano; mismas órdenes, otro orden | `tests/test_e2e_stages.py`, `tests/test_render.py` |
| 4.3 pasada condensada por tramos | pendiente | — |
| 4.4 claves de caché más estrechas | pendiente (riesgo: invalidar mal) | — |
| 4.5 subtítulos con el codificador del render | hecho (paso seguro): NVENC si el render lo usa; sin gráfica, los mismos argumentos. **No hecho**: meterlos en el grafo de cada segmento | — |
| 4.6 comprobaciones en una pasada | pendiente | — |
| 4.7 Shorts | hecho: `shorts.parallel` (2) a la vez, carpeta temporal por Short, paquete compartido. **No hecho**: intermedio ultrafast/crf 12 (cambia píxeles) | `tests/test_shorts_native.py` |
| 4.8 doblajes con caché global | pendiente | — |
| 4.9 Atlas/MapStory `useMemo` | pendiente (necesita el bucle visual de `CLAUDE.md` contra `referencias/atlas/frames/`) | — |
| 4.10 nada de red en el render | en parte: el preflight avisa si Remotion no tiene navegador; `npm install` sigue en `ensure_node_modules` | `tests/test_preflight_checks.py` |
| 5.1 people en paralelo | **descartado**: su plan B usa los clips HD que baja ingest; adelantarlo cambiaría el resultado | — |
| 5.2 factcheck en paralelo | hecho: al lado de align y planner, esperado antes de la primera etapa de pago (`speed.parallel_stages`) | `tests/test_parallel_stages.py` |
| 5.3 package a la vez que el render | pendiente (ya posible: los trabajos de Remotion tienen carpeta propia) | — |
| 5.4 voces en paralelo | pendiente | — |
| 5.5 align con su propio hueco | pendiente | — |

**Cómo medirlo en el servidor**: `python main.py --tiempos 7` antes y después (columna «render» y «Shorts»), y en el
registro de un render: «Remotion: N fotogramas en X s» y «ffmpeg: N segmentos en Y s» ahora se solapan.
