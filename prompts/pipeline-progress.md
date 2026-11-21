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
| 3.2 re-extracciones | hecho (parte segura): `info.json` ya no se borra cuando solo caducan los enlaces; se reescribe al volver a extraer (si la extracción falla, sigue ahí, y un vídeo rechazado una vez por «bot» no pasa a darse por perdido), y un plano que esperaba el turno de ese vídeo mientras otro lo re-extraía usa esos enlaces nuevos en vez de extraer otra vez. **No hecho**: bajar el HD de los finalistas mientras vive la sesión del análisis (cambia los bytes pedidos: iría apagado) | `tests/test_single_extraction.py` |
| 3.3 rasgos por ventana en el análisis | pendiente (CPU; el análisis espera sobre todo a las descargas) | — |
| 3.4 detalles y búsquedas en paralelo | descartado: no se puede garantizar el mismo número de peticiones (el bucle para al tener 3 vídeos válidos) | — |
| 3.5 ingest `-ss` antes de `-i` | pendiente (los tramos HD ya empiezan casi en el segundo pedido: poco que ganar) | — |
| 3.6 sonda de recursos directos | hecho: `python -m pipeline.sonda_directo [vídeo]` → `out/_sonda_directo.md`. **Lánzala en el servidor** | `tests/test_sonda_directo.py` |
| 3.7 soltar el turno `red` | hecho, apagado: `queue.release_red_turn` presta el turno de red durante el precálculo CLIP del final de la búsqueda y lo recupera antes de seguir. **No hecho** en ingest: allí las descargas y los cortes locales van mezclados en los mismos hilos. Comparar: `--youtube-stats 1` una noche con y otra sin (bot/429 por hora) | `tests/test_locks.py` |
| 4.1 empaquetar Remotion una vez | hecho: paquete por firma del código en `cache/render/bundles/`, carpeta propia por trabajo (pueden solaparse), `_remotion_sig` memorizado. Comprobado: PNG idéntico byte a byte, 2,1 s frente a 4,7 s por llamada | `tests/test_render_bundle.py` |
| 4.2 ffmpeg sin esperar a Remotion | hecho: la pasada condensada en segundo plano; mismas órdenes, otro orden | `tests/test_e2e_stages.py`, `tests/test_render.py` |
| 4.3 pasada condensada por tramos | pendiente | — |
| 4.4 claves de caché más estrechas | en parte: las huellas de etapa solo releen los bytes cuando cambia el nombre, tamaño, fecha o inodo de una entrada (`.stages/huellas.cache`); el valor es el mismo, los marcadores siguen valiendo. **No hecho**: limitar la huella de render a los archivos de `remotion/` que usa cada composición (riesgo de no rehacer lo que sí cambió) | `tests/test_runner.py` |
| 4.5 subtítulos con el codificador del render | hecho (paso seguro): NVENC si el render lo usa; sin gráfica, los mismos argumentos. **No hecho**: meterlos en el grafo de cada segmento | — |
| 4.6 comprobaciones en una pasada | en parte: la mezcla de audio se hace una vez (la pasada de medida la guarda en float 32 y la segunda solo aplica la ganancia; idéntica byte a byte). **No hecho**: juntar doctor/ritmo/simulación en una decodificación | `tests/test_render.py` |
| 4.7 Shorts | hecho: `shorts.parallel` (2) a la vez, carpeta temporal por Short, paquete compartido. **No hecho**: intermedio ultrafast/crf 12 (cambia píxeles) | `tests/test_shorts_native.py` |
| 4.8 doblajes con caché global | pendiente | — |
| 4.9 Atlas/MapStory `useMemo` | pendiente (necesita el bucle visual de `CLAUDE.md` contra `referencias/atlas/frames/`) | — |
| 4.10 nada de red en el render | hecho: `preflight.prepare_assets` baja antes de cada ronda los paquetes de Node que falten, el navegador de Remotion y los modelos de caras, con límite de tiempo; `npm install` en el render (último recurso) ya no puede colgarse | `tests/test_preflight_checks.py` |
| 5.1 people en paralelo | **descartado**: su plan B usa los clips HD que baja ingest; adelantarlo cambiaría el resultado | — |
| 5.2 factcheck en paralelo | hecho: al lado de align y planner, esperado antes de la primera etapa de pago (`speed.parallel_stages`) | `tests/test_parallel_stages.py` |
| 5.3 package a la vez que el render | hecho (la parte que no necesita el vídeo): package usa el vídeo terminado (fotogramas de las miniaturas de los vídeos dibujados, vista previa, el aviso con los Shorts), así que sigue tras render y shorts; lo que pide fuera, la llamada al LLM de títulos y las imágenes conceptuales, se lanza al empezar el render con las mismas palabras y package lo encuentra en caché. Mismo resultado | `tests/test_parallel_stages.py` |
| 5.4 voces en paralelo | hecho: hasta `parallel` trozos a la vez (voices.json por voz, 3 por defecto), unidos en el orden del guion; los trozos se conservan en `.voz-trozos/` tras el éxito (un guion corregido en un párrafo paga solo ese párrafo; para otra toma del mismo texto, borrar también `.voz-trozos/`) | `tests/test_tts.py` |
| 5.5 align con su propio hueco | hecho: turno «align» propio (`queue.slots.align`, 1) y `align.cpu_threads` (mitad de los núcleos por defecto; clave de velocidad). **No hecho**: el filtro VAD (hay que comprobar con voces reales que la alineación da lo mismo) | `tests/test_locks.py` |

**Cómo medirlo en el servidor**: `python main.py --tiempos 7` antes y después (columna «render» y «Shorts»), y en el
registro de un render: «Remotion: N fotogramas en X s» y «ffmpeg: N segmentos en Y s» ahora se solapan.

## HLS con pistas separadas (19-11)

| Qué | Estado | Test |
|---|---|---|
| Clips con sonido por HLS | hecho: YouTube ya casi no da HLS con audio dentro (389 de 398 extracciones del servidor solo tenían vídeo 230/232/… y audio 233/234 aparte), así que todo clip con sonido se bajaba entero. Ahora, si no hay HLS mezclado, se bajan los segmentos de la pista de vídeo y los de la de audio (los mismos segundos) y un ffmpeg local los junta, cada uno desde su propio primer segmento. Audio solo: `wa[protocol^=m3u8]` si no hay mezclado | `tests/test_hls_local.py`, `tests/test_hls_ranges.py` (selección real de yt-dlp) |
| «Ningún formato HLS encaja» (594 en 360p, 255 en HD) | diagnóstico: `python -m pipeline.diag_hls 2` agrupa esas filas por vídeo y dice cuántos tienen HLS «por probar» (la prueba de formatos de yt-dlp) y si la selección sin red sí encuentra HLS | `tests/test_hls_route.py` |

**Cómo medirlo**: `python -m pipeline.diag_hls 1` al día siguiente: «Vía de cada tramo» con más `hls-local` y menos
`entero`; `python main.py --youtube-stats 1`: menos GB por descargas enteras.

## Estadísticas de fallos (19-11)

| Qué | Estado | Test |
|---|---|---|
| Fallos poco claros | `python main.py --youtube-stats 1` añade «De dónde salen los fallos poco claros»: para other, sin-texto, 429, bot y proxy-túnel, qué petición falló, en qué vídeo, a qué horas y los textos más repetidos | `tests/test_error_causes.py` |
| Filas «descartado» antiguas | ya no cuentan como peticiones ni errores del proxy | `tests/test_error_causes.py` |

## Motor: revisor automático (20-11)

| Qué | Estado | Test |
|---|---|---|
| Revisor, modo informe | hecho: `python -m pipeline.revisor <vídeo> [--telegram] [--modelo M] [--max-usd 1]`. Solo fallos objetivos: roto y repetido medidos (sin modelo); no tiene que ver, otra persona, dibujos/videojuego y marca de agua por un modelo de visión que ve dos fotogramas del momento exacto, la frase, su contexto y la foto del protagonista. Cada marca lleva su prueba y su seguridad. Escribe `out/<vídeo>/revisor/` (informe.md, revisor.json, hojas). No cambia nada | `tests/test_revisor.py` |
| Revisor: arreglos tras newgym3 | hecho: fotogramas del vídeo final si no puede leer el clip (los 5 «roto» de newgym3 eran eso), un plano ilegible ya no se da por roto (sale como «no revisado»), la foto del protagonista desde work/<vídeo>/people/, progreso en pantalla, y los huecos tapados con el clip de otro plano dicen cuál | `tests/test_revisor.py` |
| Revisor en la cola (cambia planos antes del render) | pendiente: newgym3 acertó en casi todo lo marcado; falta decidir el umbral de seguridad |  — |

## Motor: puntería (20-11, tras newgym3)

| Qué | Estado | Test |
|---|---|---|
| Mismos segundos de una fuente en varios planos | hecho: `fallback.same_stretch` en todas las vías del relleno y otra vez al reservar (varios hilos elegían el mismo tramo a la vez): newgym3 tenía 58-60 s de un entrenamiento en siete planos | `tests/test_fallback_methods.py` |
| Huecos tapados con clips de otra parte del vídeo | hecho: `fill_empty_shots` presta el clip más cercano dentro de `timeline.borrow_window_seconds` (40 s), no el más lejano; sin ninguno cerca, pizarra de palabras clave (newgym3: la boda en 0:58 con «seis títulos mundiales») | `tests/test_qash_style.py` |
| Informe para una segunda opinión | `prompts/motor-informe-para-fable.md` | — |

## Puntería · bloque 0: medir bien (plan `prompts/motor-punteria-prompt.md`, rama claude/quirky-johnson-6m1428)

| Punto | Estado | Test |
|---|---|---|
| 0.1 a quién culpa en los repetidos | hecho: el dueño de un clip es el plano que lo eligió (aunque salga después); los planos tapados en el montaje son «hueco tapado» (motivo propio); cada pareja de repetidos cuenta una vez y se culpa al lado más débil (préstamo < relleno < protagonista < juez < a mano) | `tests/test_revisor.py` |
| 0.2 «no tiene que ver» en planos de ambiente | hecho por instrucción al modelo: frase sin imagen posible + metraje de la persona del vídeo = válido, salvo que lo contradiga (la boda en una frase de competición). Con la etiqueta del bloque 1 se hará por plano | — (instrucción; se mide en la línea base) |
| 0.3 línea base | hecho: `.venv/bin/python -m pipeline.revisor newgym3 tedbundy guiadelmapa elcrimendepazos --base --max-usd 0.3` → `out/_revisor_base.md` (marcados por 100, por motivo, repetidos por parejas, no revisados) | `tests/test_revisor.py` |
| 0.4 el juez barato | herramienta lista: `.venv/bin/python -m pipeline.rejuzgar newgym3 gpt-5-mini s065,s074,s097,s127` → `out/newgym3/rejuzgar-gpt-5-mini.md`. Mirar si el modelo fuerte rechaza esas hojas (columna «Ahora» vacía) y su motivo. s074 vino del relleno: probablemente sin hoja del juez (lo dice el informe). **Lo lanza el usuario** | `tests/test_judge_sheets.py` |

## Puntería · bloque 1: planificar por ideas (`planner.ideas`, apagado)

| Punto | Estado | Test |
|---|---|---|
| 1.1 ideas con etiqueta | hecho: `pipeline/agrupar.py`, una pasada más del modelo tras el planner; literal / ambiente / rótulo, quién debe y quién no puede salir, época, línea de pantalla, datos rotulables (`Shot.idea`). La respuesta se comprueba (planos seguidos, sin cruzar capítulos, ≤ 14 s) y lo que falte se etiqueta por reglas | `tests/test_agrupar.py` |
| 1.2 una búsqueda por idea | hecho: la búsqueda por escenas usa las ideas como escenas y da a todos sus planos las mismas fuentes. **No hecho**: un solo análisis y una sola llamada al juez por idea (sigue siendo por plano: misma calidad, sin el ahorro de llamadas) | `tests/test_agrupar.py`, e2e «ideas» |
| 1.3 cortes de una idea de la misma fuente | hecho en parte: el vídeo maestro y la continuación del juez se agrupan por idea. **Choque con el tope de 5 s**: dos cortes CONTIGUOS de un vídeo son, a efectos de Content ID, un solo fragmento; la continuación ya limita la tanda seguida a 5 s y lo mantengo. Pasados 5 s, el siguiente plano de la idea toma otro tramo aceptado del mismo maestro (no contiguo) u otra fuente. Pedir el tramo con margen: pendiente | e2e «ideas» |
| 1.4 quién / época / línea / datos | hecho en el esquema y el prompt; el juez ya los lee (3.2); la línea de pantalla y los rótulos se usarán en el bloque 2 | `tests/test_agrupar.py` |
| 1.5 los demás leen la etiqueta | hecho: un rótulo no se busca ni se tapa con un clip; una idea literal nunca recibe relleno del protagonista ni un clip prestado; el revisor pasa la etiqueta al modelo y la línea base separa «no tiene que ver» en literales | `tests/test_revisor.py`, e2e «ideas» |
| 3.1 modelo fuerte en lo literal | hecho, apagado: `judge.model_literal` (+ `usd_per_mtok_literal`). Dato: `rejuzgar` con gpt-5-mini rechazó 3 de los 4 fallos sueltos de newgym3 que el barato aceptó | `tests/test_agrupar.py` |
| 3.2 el juez recibe la etiqueta | hecho: literal / ambiente, quién debe y quién no puede salir, época | `tests/test_agrupar.py` |

**Cómo probarlo**: en `canales/gimnasia.yaml` (o el perfil del canal) → `planner: {ideas: true}` y `judge: {model_literal: gpt-5-mini}`;
copiar el guion y la voz de newgym3 a una carpeta nueva (p. ej. `newgym3-ideas`), dejar que la cola lo haga y pasar
`.venv/bin/python -m pipeline.revisor newgym3 newgym3-ideas --base --max-usd 0.3`. Comparar «marcados por 100» y
«huecos tapados». **No comprobado aquí**: la calidad real de las ideas que escribe el modelo (en las pruebas responde
uno simulado).

## Puntería · bloque 2: una salida digna cuando no hay vídeo (con `planner.ideas`)

| Punto | Estado | Test |
|---|---|---|
| 2.1 línea de pantalla por idea | hecho: `timeline.idea_lines` (ambiente por defecto · siempre · no), palabra clave entre asteriscos (la resalta el componente kinetic), nunca sobre otro gráfico, una cada 12 s como mucho (`idea_line_gap_seconds`) | `tests/test_agrupar.py` |
| 2.2 rótulo de dato | hecho: el primer dato de cada idea como rótulo abajo a la izquierda (año → fecha, cifra → nota, palabra → lugar); `timeline.idea_facts` | `tests/test_agrupar.py` |
| 2.3 orden del relleno en ambiente | hecho: primero el clip del plano de al lado en la misma idea (sus segundos siguientes, tras un salto de 1,5 s: nunca un fragmento contiguo de más de 5 s), luego lo de siempre (otro clip del protagonista, el mismo suceso, fotos); sin segunda búsqueda en YouTube (nada que buscar). El clip prestado del montaje sigue siendo de la misma ventana de 40 s | `tests/test_fallback_methods.py`, e2e «ideas» |
| 2.4 stock de concepto sin caras | hecho, apagado: `fallback.concept_stock`; el planner escribe la búsqueda (`concept`) solo en ideas de ambiente; siempre pasa por el juez | `tests/test_agrupar.py` |
| 2.5 orden en una idea literal | hecho (bloque 1.5): nunca relleno del protagonista ni clip prestado; foto o pizarra | e2e «ideas» |
| 2.6 citas en tarjeta | ya existía: el gráfico `cita` (graphics.py) cuando el guion reproduce lo que alguien dijo. `quotes.count` sigue en 2: subirlo son más búsquedas y extracciones en YouTube (por canal, midiendo) | — |
| 2.7 el gancho solo con juez | hecho: en los primeros `judge.hook_seconds` de un vídeo con ideas, todo lo del relleno pasa por el juez (fotos incluidas), el stock sin juez no entra y el montaje no presta clips | e2e «ideas» |

## Puntería · bloque 3.3: el revisor en la cola (`revisor.enabled`, apagado)

| Qué | Estado | Test |
|---|---|---|
| Etapa `revisor` entre el montaje y la QA | hecho: revisa el montaje antes del render; lo que `revisor.to_fix` elige vuelve UNA vez al relleno en `work/<vídeo>/revision.auto.json` (archivo propio: tus etiquetas reescriben `revision.json` entero), se rehacen relleno, apertura y montaje (con sus marcadores al día: `runner.mark_done`) y se revisa otra vez; lo que siga marcado queda en `out/<vídeo>/revisor/` | `tests/test_revisor.py`, e2e «ideas» |
| Qué se devuelve | repetidos y rotos siempre; literales con seguridad ≥ `min_confidence` (0.85); ambiente solo otra persona / dibujos / marca de agua; sin ideas, eso con ≥ `min_confidence_sin_ideas` (0.95); los huecos tapados pasan a texto (el montaje no les presta clip) | `tests/test_revisor.py` |
| El relleno no repite lo marcado | hecho: ningún tramo marcado (tuyo o del revisor) vuelve a elegirse para ningún plano del vídeo | — |
| Encenderlo no rehace nada | la sección `revisor` no está en la huella de la etapa: solo los vídeos que lleguen a ella desde entonces | — |
| Pendiente | el aviso al móvil con las hojas de lo que siga marcado (hoy: `--telegram` a mano) | — |

**Cómo probarlo**: `revisor: {enabled: true}` en el config.yaml de un vídeo (como `newgym3-ideas`) o del canal; en el registro
sale «Revisor: N planos vuelven al relleno…» y «N marcados antes, M después».

## Prueba newgym3-ideas (21-11): peor, y por qué

| | newgym3 | newgym3-ideas |
|---|---|---|
| planos sin imagen en el montaje | 10 de 231 | 92 de 231 |
| pantallas de texto (kinetic) | 4 | 47 |
| sin resolver en el relleno | 51 | 86 |
| ideas | — | 97 (120 planos literales, 88 ambiente, 21 rótulo) |

Causas: el modelo marcó literal la mitad del vídeo (y una idea literal sin su clip va a texto); compartir fuentes por
idea agotaba el tope por fuente. Arreglado: literal solo donde el planner oyó una acción que tiene que verse
(`broll.moment`), el prompt lo pide como excepción; dentro de una idea sus propios usos de una fuente no cuentan para
el tope y el juez no fuerza variedad entre sus cortes. Ojo: newgym3 tenía solo 10 vacíos porque tapaba 40 huecos con
clips de otras partes (antes del arreglo de los préstamos); un vídeo nuevo sin ideas también mostrará ahora más texto
donde antes había un clip sin sentido.

## Puntería · bloque 4 (primera tanda): material de partida

| Qué | Estado | Test |
|---|---|---|
| Guardar el material | hecho: `materiales/<vídeo>/material.json` (vídeos, canales, etiquetas de tus clips) y clips en `materiales/<vídeo>/material/`; para todo el canal, `materiales/<canal>/material.json` | `tests/test_material.py` |
| La búsqueda empieza por él | hecho: tus clips (por etiquetas), los vídeos pegados y los de los canales con título parecido (API, sin proxy) delante de cada plano; el filtro de títulos no los quita; `material.youtube_search: false` quita la búsqueda a ciegas; añadir material vuelve a buscar ese vídeo (huella) | `tests/test_material.py` |
| El juez los ve primero | hecho: hasta `judge.material_first` (2) opciones del material en la primera hoja, con la mejor de fuera al lado; esos planos siempre pasan por el juez; si acepta tu material, gana al vídeo maestro | e2e «ideas» (un clip propio llega a pantalla) |
| Clips propios | hecho: fuente `propio`; sin «Fuente:» en pantalla ni en los créditos; la QA y el montaje no lo exigen. Los planos siguen siendo de ≤ 4 s, así que el tope de 5 s no se notaba | `tests/test_material.py`, e2e |
| Estudio | hecho: apartado «Material de partida» al crear un vídeo (enlaces, canales con «guardar para todo el canal», clips con «qué se ve»), el vídeo espera en la cola mientras suben los clips (`hold`), subida por trozos hasta 4 GB; zonas de arrastrar y soltar para guion, voz, vídeo de apertura y clips | capturas en escritorio y móvil |
| Índice por escenas (2ª tanda) | hecho: `pipeline/indice.py` corta cada fuente del material en escenas (CLIP sobre las miniaturas del storyboard, sin proxy), un modelo de visión barato describe cada escena (inglés + palabras clave en español) y se guarda una vez por fuente; cada plano añade la ventana de la escena que más palabras comparte con él (`hint: indice`), que no se descarta por CLIP bajo y que el juez ve primero entre el material | `tests/test_indice.py`, e2e «ideas» |
| Pendiente | material al vídeo ya creado desde su ficha; gráficos de GTA en Remotion; transcripción por escena | — |
