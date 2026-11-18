# Prompt: fiabilidad, puntería y velocidad del pipeline de vídeos

Pega todo lo que hay debajo de la línea en una sesión nueva sobre este repositorio.

---

Vas a mejorar el pipeline de vídeos de este repositorio (`edit-vid3`) en tres frentes, por este orden de
importancia: que **ninguna noche se pierda** por un error de código, una descarga, un proxy o un proceso colgado;
que **cada plano muestre lo que la voz está contando**; y que **cada vídeo tarde lo menos posible** de guion a
`video-final.mp4`. Fuera de qué clip se elige para cada plano, el aspecto y el sonido de los vídeos no deben cambiar.

El trabajo es grande y no cabe en una sesión. Avanza en orden, deja el estado en el archivo de progreso (ver
«Forma de trabajar») y para en un punto limpio cuando haga falta: otra sesión seguirá desde ahí con este mismo
documento.

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
  Única excepción prevista: el ritmo por sesión en la vía residencial (punto 4 de «Lo que dicen estos datos»),
  que entra apagado y lo decide el usuario con sus estadísticas.
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

- Los únicos tiempos reales son los de la sección «Datos del servidor» de más abajo. No inventes cifras de mejora:
  describe el cambio y cómo medirlo en el servidor con `python main.py --tiempos` y `--youtube-stats`.
- Todo cambio de descargas se demuestra con tests que usan dobles (como hacen `tests/test_residential_*.py` y
  `tests/test_cookie_rotation.py`), nunca contra YouTube.
- Lo que solo puede confirmarse en el servidor (velocidad real, tasa de bloqueos, GB de proxy) queda detrás de una
  opción apagada por defecto, con el comando exacto para que el usuario lo pruebe y lo compare.
- Para el render sí puedes medir aquí: hay storyboards y materiales de ejemplo (`storyboards/`, `materiales/`) y
  Chromium instalado. Antes de dar por buena una optimización de render, renderiza el mismo tramo antes y después y
  compara fotogramas (por ejemplo con el filtro `ssim` de ffmpeg); si no es idéntico o casi (SSIM ≥ 0,99 donde el
  cambio implique recodificar), no entra.

## Datos del servidor (18-11-2026)

Máquina: 16 núcleos, 62 GB de RAM, sin gráfica. Una sola salida a YouTube: proxy residencial de pago (Rainproxy),
`concurrency: 2`, `min_interval: 2.0`, PO Token forzado, clientes `default, web_safari`. Cola: 4 vídeos a la vez,
3 de metraje, `slots: {red: 1, cpu: 3}`. Alineación por OpenAI, `render.concurrency: 6`.

**Tiempo por vídeo de metraje** (50 vídeos, 30 días): mediana 4 h 15 min. Analizar clips 1 h 14 min (30 %), render
36 min (19 %), buscar material 31 min (17 %), planos alternativos 33 min (16 %), descargar clips 14 min (8 %),
Shorts 8 min. Todo lo demás, menos de 5 min por etapa. Los máximos llegan a 4-5 h por etapa. Vídeos dibujados (91):
mediana 9 min, el 91 % es render, con máximos de 1 h 30 min en los Atlas.

**Tiempo en peticiones a YouTube** (suma de todos los vídeos): esperas 484 h, tramo HD 290 h, tramo de análisis a
360p 161 h, metadatos 117 h, descarga HLS 111 h, descarga completa 32 h. Es decir: la mayor partida es esperar turno.

**YouTube en 7 días** (24 vídeos empezados, solo **8 terminados**): 14.632 peticiones, 16,8 % fallidas. Tramos
conseguidos 5.492 de 8.950 (61 %), 87 s de media por tramo, unos 1,6 MB cada uno. Errores: «otros» 1.127, 429 930,
timeout 181, «no eres un bot» 139, no disponible 56, 403 21.

**GB por el proxy en 7 días**: 69 GB, 8,6 GB por vídeo terminado. Descargas completas 43,8 GB (63 %, 2.169 veces,
unos 20 MB cada una), metadatos 19,3 GB (28 %, 9.092 extracciones, 2,1 MB cada una, 13 % fallidas), HLS 5,8 GB
(8 %, 1.220 veces). Dentro de los metadatos: `youtube.com/watch` 12,1 GB y `youtube.com/` 8,3 GB.

**Errores acumulados por etapa y acción** (270.249 peticiones en `work/*/youtube_downloads.jsonl`): metadatos en
sourcing «otros» 18.363 y «bot» 7.426; tramo a360 en análisis «otros» 8.264; metadatos en análisis «otros» 4.606;
tramo HD en fallback «otros» 3.514 y en ingest 2.540; `get` en análisis 429 1.108; HLS en coldopen «no disponible»
1.070. Los 429 salen casi todos de `get`, que no pasa por el proxy.

**Descartes más repetidos**: «sin HLS y entero supera el tope del proxy residencial», el mismo vídeo hasta 43 veces.

**HLS**: de los `cache/videos/*/info.json` con el campo `hls`, 4.980 dicen `true` y solo 10 `false` (otros 16.150 no
lo tienen todavía). Casi todos los vídeos extraídos tienen HLS, y aun así las descargas completas doblan a las de
HLS (2.169 frente a 1.220 en 7 días) y se llevan el 63 % de los GB.

**Qué hay dentro de «otros»** (acumulado): metadatos sin ningún detalle 20.524; metadatos «Unable to connect to
proxy … Tunnel» 4.442; tramo HD sin detalle 3.952; tramo a360 «el proxy no responde» 2.747 y sin detalle 2.308;
HLS sin detalle 1.653; y unas 4.800 filas que no son peticiones sino el aviso «descartado (sin HLS…)» repetido.

**Por qué no terminan los vídeos** (`out/_cola.md`, 22 filas): 11 murieron con `NameError: name 'official' is not
defined` (ya arreglado en `eaa0c7d`) **después de 3,5 a 7 horas de trabajo cada uno**, casi todo en análisis; 4 en
«espera cuota» tras 48-77 min de búsqueda; 4 doblajes con «2 validation errors for Timeline»; 2 con «Hay voz pero no
hay transcriptor (OPENAI_API_KEY para Whisper)» aunque `--doctor` da la clave por buena; 1 porque el planner
devolvió JSON inválido en todos sus intentos; 1 retenido por la verificación de datos.

### Lo que dicen estos datos, por orden de impacto

Haz estos puntos justo después de la fase 0 y de los puntos 1-3 de la fase 1, antes que el resto. Los que cambian
qué se pide a YouTube entran con una opción apagada por defecto y el comando para comparar; el usuario los
activará en un vídeo y mirará `--youtube-stats`.

1. **Un error de código tiró 11 vídeos tras 3,5-7 horas cada uno.** Es la razón principal de que solo terminaran 8
   de 24, y confirma que la fase 0 va primero. Además de la puerta antes del despliegue, haz que un error de
   programación (`NameError`, `AttributeError`, `TypeError`, `KeyError`…) en una etapa tardía no se descubra tan
   tarde: la prueba de extremo a extremo con dobles debe recorrer todas las ramas de `apertura`, `coldopen`,
   `fallback` y `shorts`, que es donde se esconden. De paso, mira los otros fallos de la tabla: el planner debe
   sobrevivir a un JSON inválido (pedir salida JSON estricta al modelo o reparar antes de dar el intento por
   perdido); el aviso «no hay transcriptor» con la clave presente (puede ser la clave por socio de
   `pipeline/usuarios.py`); y los «validation errors for Timeline» de los doblajes.
2. **«Otros» es el error más frecuente y la mayoría de sus filas no llevan detalle.** Haz que toda fila fallida de
   `_metric` lleve el texto del error, y amplía la clasificación hasta que «otros» sea residual: túnel del proxy
   caído, proxy sin respuesta, formato no disponible, ffmpeg, fragmento vacío, etc. Los avisos «descartado … no se
   vuelve a pedir» no son peticiones: que no cuenten como fallos ni se repitan miles de veces; un vídeo
   descartado sale de los candidatos de todos los planos de una vez. Los fallos de túnel del proxy (4.442) son
   transitorios: reintento con otra sesión antes de dar el vídeo por perdido.
3. **Casi todos los vídeos tienen HLS y aun así dos de cada tres descargas son del vídeo entero.** Es la mayor
   partida de GB y no debería existir. Averigua por qué `_download_range` no entra por HLS o sale de él: si
   `_has_hls` da falso sobre el `ytdlp-info.json` recién extraído aunque `info.json` diga que sí (por ejemplo,
   porque `web_safari` no devuelve formatos en esa extracción, o porque yt-dlp descarta los que piden PO Token),
   si `hls_format` devuelve vacío para algún prefijo, o si es `_fetch_hls_locally` quien falla con «format is not
   available» y cae a la descarga entera. Registra en cada tramo por qué vía bajó y por qué no fue HLS, y arregla
   la causa. Si hace falta un dato del servidor para saberlo, pídelo con el comando exacto.
   **Además, tramos por rango de bytes para los que de verdad no tienen HLS.** Hoy esos se bajan enteros o se
   descartan si pasan de 10 min / 80 MB, que es lo que el usuario vive como «no me
   deja bajar lo que quiero». Los formatos DASH en mp4 llevan un índice (`sidx`) al principio: bajando los
   primeros KB con una petición `Range` se sabe qué bytes cubren los segundos pedidos, y se piden solo esos (más
   la cabecera) por la misma sesión del vídeo, en trozos de menos de 10 MB como ya hace `http_chunk_size`. ffmpeg
   corta en local, igual que con HLS. Prefiere formatos `avc1` en mp4; para webm (índice `Cues`) o si el índice no
   aparece, se queda el comportamiento actual. Pruébalo con un servidor HTTP local y un mp4 fragmentado generado
   con ffmpeg. Con esto, el tope de `whole_max_*_residential` deja de descartar vídeos largos.
4. **El ritmo se mide por proxy, pero cada sesión del proxy residencial es una IP distinta.** `SharedPacer` es uno
   por salida y para todos los procesos: con `min_interval: 2.0`, los tres vídeos de metraje comparten una
   petición cada 2 s, y de ahí las 484 h de espera. Para la vía residencial, añade la opción de medir el ritmo y
   la concurrencia por sesión (por vídeo de YouTube), con un tope global de conexiones abiertas al proxy. La
   regla «no subas el ritmo» nació con proxies de casa, que son una sola IP; aquí hay que comprobarla con datos,
   no darla por buena ni por mala.
5. **Los 429 vienen de `get`, que sale directo desde la IP del servidor**, y falla más de la mitad de las veces
   (1.186 de 2.113). Mira qué host es (miniaturas del storyboard o subtítulos), aplícale su propio ritmo y caché
   negativa, y si es el de subtítulos pásalo por la sesión del vídeo.
6. **Metadatos: 379 extracciones y 0,8 GB por vídeo.** Averigua qué es la partida `youtube.com/` (8,3 GB) y si se
   puede evitar; revisa cuándo se aplica ya `player_skip: webpage` y si puede aplicarse más sin perder formatos
   (opción apagada, con sonda). Filtra antes con lo que la API de datos ya devuelve gratis (duración, definición,
   bloqueo regional, edad: `pipeline/ytapi.py`) para no gastar una extracción en un vídeo que se va a descartar,
   y baja el número de candidatos con detalles por plano si los datos muestran que los últimos casi nunca ganan.
7. **El análisis es la etapa más lenta (30 %) y baja dos veces los mismos segundos**: a 360p para puntuar y en HD
   para montar, cada tramo con sus 87 s de media. Como un tramo más rico ya sirve a una petición más pobre
   (`RANGE_FAMILY`), prueba a bajar la ventana de análisis directamente en la calidad final para los mejores
   candidatos, de modo que ingest la encuentre hecha. Cambia bytes por peticiones: opción apagada, y que el
   informe diga GB y minutos de las dos formas. Mira también `analysis.adaptive`, que existe y está apagado.
8. **Coldopen pide 1.070 veces HLS de vídeos «no disponibles».** Caché negativa: un vídeo no disponible no se
   vuelve a pedir en esa etapa ni en las siguientes.
9. **El aviso de proxy caído habla de Tailscale y de «ese PC» también con un proxy de pago** (2.722 notas con
   `gw.dataimpulse.com`). Texto distinto para la vía residencial, y comprueba que esas notas no se guardan como
   resultado definitivo del plano.
10. **Render: 36 min de mediana con 16 núcleos y 62 GB.** La fase 4 se mide aquí contra ese número. Con esta
    máquina, `render.concurrency: 6` y tres turnos de `cpu` dejan núcleos libres cuando solo hay un render.

### Contenido sin topes fijos

El usuario quiere poder usar cualquier vídeo que encuentre. Los límites que hoy descartan material son de tres
clases, y solo la primera no depende de él:

- Lo que YouTube niega (bot, geo, edad, privado). No se puede saltar; sí se puede dejar de perder tiempo en ello.
- Topes para ahorrar GB de proxy: `whole_max_minutes_residential`, `whole_max_mb_residential`, `max_height`,
  `max_fps`, `max_details_per_shot`, `min_height`, `min_duration`, `max_duration`. Con el punto 3 los dos
  primeros dejan de hacer falta para tramos.
- Filtros editoriales: `content.title_blocklist`, el bloqueo de QA a clips de terceros de más de 5 s, 
  `judge.avoid_other_videos`, las comprobaciones de cara, género y texto en pantalla de `fallback` y `analysis`.

Haz que todos los de la segunda y tercera clase se puedan cambiar por canal y por vídeo desde la configuración
(algunos ya se puede; comprueba cuáles tienen el valor escrito en el código) sin rehacer los vídeos a medias, y
añade a `out/<slug>/diagnostico.md` una tabla «Material descartado»: por cada motivo, cuántos candidatos y cuántos
planos se quedaron sin vídeo por él. No cambies ningún valor por defecto: el usuario decidirá con esa tabla. El
límite de 5 s es su protección frente a reclamaciones de Content ID; déjalo configurable y dilo en la documentación.

### Que el clip sea de lo que se está contando

La queja principal del usuario sobre el resultado: a menudo el clip no tiene que ver con lo que dice la voz en ese
momento, incluso en temas con mucho material en YouTube. La auditoría del camino completo (planner → búsqueda →
análisis → juez → relleno) encontró estas causas, todas comprobadas en el código salvo donde se dice:

- **Solo se lanzan dos búsquedas por plano y una es la del suceso, igual para todos sus planos.**
  `queries_for` (`pipeline/sourcing/youtube.py`) corta a `api_queries_per_shot: 2` cuando hay API: quedan la
  etiqueta del suceso y la primera búsqueda del LLM. La búsqueda en el idioma del guion, `placeQuery` y las
  búsquedas 2-5 del planner no se ejecutan nunca. Una búsqueda de la API cuesta 100 unidades pida 8 resultados o
  50, y se piden 8.
- **Se miran 3 vídeos por plano**, ordenados por la posición en la búsqueda más un bono si *cualquier* palabra de
  una entidad sale en el título o el canal (`candidates`). La descripción que devuelve la API no se usa; no se
  exige que el título nombre el suceso ni el año. Con un 13 % de extracciones fallidas, muchos planos se quedan
  con uno o dos vídeos.
- **Dentro de un vídeo, el momento se busca en 40 miniaturas como mucho** (`storyboard_frames`,
  `analysis.max_frames_per_video`): en un vídeo de 20 minutos, una cada 27 s para un plano de 2-4 s. Los subtítulos
  de la fuente solo se usan cuando el plano tiene `moment`; no se usan capítulos ni descripción.
- **El texto con el que CLIP puntúa es la media de `visualIntent` y de todas las búsquedas** (`prompts_for`,
  `pipeline/analysis/__init__.py`), llenas de nombres propios y años que ViT-B-32 no sabe ver. Ese orden decide
  qué tres opciones llega a ver el juez.
- **El juez sí lee la narración** (`shot_brief`, `pipeline/judge.py`), pero ve tres fotogramas de 320×180 por
  candidato, y cuando la ventana a 360p no se pudo bajar ve la misma miniatura del storyboard tres veces. Fuera
  del gancho solo hay una ronda (`rounds_rest: 1`). Un error de la API del juez cae en silencio al orden de CLIP.
  En producción `judge.model` se cambió entero a un modelo más barato, también para el gancho y para la revisión
  final (`pipeline/revision.py`); la opción pensada para eso era `model_rest`.
- **El código puede pasar por encima del juez** después del veredicto: fragmento del vídeo maestro, continuación
  de la acción (segundos que el juez no vio), variedad de fuentes, repetidos.
- **Cuando la descarga del clip elegido falla (39 % de los tramos), entra el relleno** (`pipeline/fallback.py`,
  `resolve`). Las siguientes opciones se vuelven a juzgar, pero Pexels y el relleno con otros planos del
  protagonista entran sin juez. Nada registra si el clip final era la primera elección del juez.
- **Fallo:** el método `"protagonist-photo"` no está en el `Literal` de `FallbackItem.method`
  (`pipeline/schemas.py`); salta un error de validación que se traga y el plano acaba en rótulo. Ese paso no
  puede funcionar nunca.
- Las instrucciones y ejemplos del planner (`LABEL_SYSTEM`, `pipeline/planner.py`) son de deporte y piden
  búsquedas de «2-6 palabras» a la vez que «persona + competición + año + acción». En vídeos de tema sin
  protagonista (negocios, megaproyectos, crímenes) las búsquedas salen genéricas. (Inferencia: confírmalo con
  `shots.json` de un vídeo de cada canal si el usuario te lo pasa.)

Datos de cuatro vídeos terminados (`selection.json` → `stats`, y `decidedBy` de `out/<slug>/manifest.json`):

| Vídeo | Planos | El juez aceptó algo | Acaban con la elección del juez | Resto |
|---|---|---|---|---|
| tedbundy (crimen) | 137 | 113 (82 %) | 95 | 26 de relleno, 3 sin dato |
| elcrimendepazos (crimen) | 303 | 133 (44 %) | 121 | 49 de relleno, 119 sin dato |
| atleta1 (deporte) | 221 | 95 (43 %) | 56 | 59 de relleno, 92 sin dato |
| guiadelmapa (GTA) | 155 | 85 (55 %; solo 115 llegaron al juez) | 79 | 51 vídeos de Pexels sin juez, 25 de otro relleno |

`judgeErrors` y `byScore` son 0 en los cuatro: el juez no falla ni se le salta por error. Lo que pasa es que en la
mitad de los planos **rechaza todo lo que se le enseña**, o no se le enseña nada (40 planos de guiadelmapa sin
candidatos). El problema está antes del juez: la búsqueda y la elección del momento no le traen material bueno, y
el relleno tapa el hueco con algo peor. En atleta1 además se pierden 39 elecciones del juez entre el veredicto y el
montaje (descargas fallidas). En guiadelmapa un tercio del vídeo es stock de Pexels elegido por CLIP sin juez.
«Sin dato» son planos con medio pero con `decidedBy` nulo en el manifiesto (`pipeline/qa.py`): averigua qué son
(¿planos que heredan el medio del anterior?) y haz que el manifiesto lo diga.

Qué hacer, por orden. Lo que no cuesta proxy ni llamadas entra encendido; lo que sube gasto, con opción y medida.

1. Arregla el `Literal` de `protagonist-photo`, con su test.
2. **Mide antes de tocar.** Añade a `Selection` qué puesto dio el juez a la opción usada y quién decidió al final
   (juez, maestro, continuación, variedad, nota de CLIP por error del juez), y a `out/<slug>/diagnostico.md` una
   tabla «De dónde salió cada plano»: primera elección del juez, otra opción juzgada, relleno juzgado, relleno sin
   juzgar, foto, generado, rótulo; y cuántos planos se juzgaron solo con miniaturas. Amplía
   `python main.py --informe-analisis` para dar esa tabla por canal. Sin esto no se sabrá si lo siguiente mejora.
3. **Búsqueda.** Con la API: suceso + la búsqueda más concreta del plano + la del idioma del guion, con las de
   `moment` primero, y 25-50 resultados por búsqueda (mismo coste de cuota). Ordena los candidatos antes de gastar
   extracciones usando título y descripción: nombre completo de la entidad, palabras del suceso, año; no des el
   bono por una sola palabra suelta.
4. **Momento dentro del vídeo.** Sube las miniaturas analizadas por vídeo (salen directas de `i.ytimg.com`, solo
   cuestan CPU) y localiza por subtítulos en todos los planos, no solo los que tienen `moment`: lo que dice la
   narración de ese plano, traducido, contra lo que se dice en la fuente. Usa también los capítulos del vídeo.
5. **Texto de CLIP**: `visualIntent` y `moment`, sin la lista de búsquedas con nombres y años. Prueba un modelo
   CLIP mejor o multilingüe midiendo cuántos planos acepta el juez a la primera con uno y otro.
6. **Juez.** Nunca tres copias de la misma miniatura; más fotogramas y más grandes por candidato; un error de la
   API manda el plano al relleno o lo reintenta, no al orden de CLIP; modelo fuerte en el gancho y el barato
   solo en `model_rest`. Deja una herramienta que repita el juez con otro modelo sobre las hojas ya guardadas
   (`work/*/judge/*.jpg`) y compare veredictos, para decidir el modelo con datos. Revisa cada regla que cambia la
   elección del juez tras el veredicto: que solo se aplique entre opciones que el juez aceptó.
7. **Relleno.** Antes de reordenar por CLIP, usa las opciones 2 y 3 que el juez ya aceptó. Pexels y el relleno
   del protagonista pasan por el juez. Sube `rounds_rest` a 2 solo si la tabla del punto 2 lo justifica.
8. **Planner.** Reescribe las instrucciones de búsquedas para que sirvan a cualquier tema: explica al modelo para
   qué son (encontrar en YouTube el vídeo donde se ve exactamente eso), que nombre siempre de quién, qué y cuándo
   se habla aunque no haya protagonista, y da ejemplos de varios tipos de canal, no solo de deporte. Cambiar
   estas instrucciones no debe rehacer los vídeos ya planificados.

9. **Que la cuota de la API no pare vídeos.** Hoy, con claves pero sin cuota, el vídeo espera
   (`api_overflow: esperar`; 4 vídeos en «espera cuota» en la cola), y cada vídeo gasta unas 30.000 unidades de
   las 10.000-50.000 diarias. La búsqueda por yt-dlp a través del proxy ya existe (`search`, rama `ytsearch`) pero
   solo entra sin claves. Reduce el gasto de cuota sin perder puntería: una búsqueda por suceso y no por plano
   donde los planos comparten suceso (es lo que hace `scene_search`, apagado: mide con `--comparar-escenas`),
   caché de búsquedas compartida entre vídeos del mismo tema, y `playlistItems` (1 unidad) para recorrer los
   canales de confianza en vez de `search` (100). Y añade un modo mixto: cuando la cuota se acaba, las búsquedas
   que faltan salen por yt-dlp con la sesión de búsqueda del proxy, con su propio tope por hora, en lugar de
   esperar al día siguiente. Los detalles de vídeo (`videos.list`, 1 unidad por 50 vídeos) siguen por la API.

La fiabilidad de las descargas es también calidad: cada tramo que falla empuja el plano a una opción peor, y cada
ventana de análisis que falla hace que el juez decida sobre miniaturas. Los puntos de descargas de arriba cuentan
para esto tanto como estos ocho.

## Forma de trabajar

- Rama: la que te indique la sesión. Un commit por mejora, con mensaje que diga qué problema resuelve.
- Cada mejora lleva su test. `python -m pytest tests -q` y `npm run typecheck` pasan antes de cada commit; si la
  suite ya tenía fallos antes de empezar, apúntalos al principio y no los mezcles con los tuyos.
- Lleva el progreso en `prompts/pipeline-progress.md`: por cada punto, hecho / descartado (por qué) / pendiente de
  probar en el servidor (con el comando). Si la sesión se corta, la siguiente continúa desde ahí.
- **El servidor de producción hace `git pull` de `main` cada 2 minutos.** Trabaja solo en tu rama y no fusiones
  nada en `main`: el usuario fusionará por partes, y cada parte debe poder desplegarse sola sin romper los vídeos
  a medias. Por eso los commits van agrupados por bloque, cada bloque con la suite en verde.
- Orden de trabajo:
  1. Fase 0 entera.
  2. Fase 1, puntos 1 a 3 (cachés que no se envenenan, cerrojos entre procesos, plazos).
  3. «Lo que dicen estos datos», puntos 1 a 10.
  4. «Que el clip sea de lo que se está contando», puntos 1 a 9, y «Contenido sin topes fijos».
  5. El resto de la fase 1 y la fase 2.
  6. Fases 3, 4 y 5.
  Donde un punto de una fase repite uno de las secciones de datos, vale la versión de la sección de datos.
  No adelantes trabajo de velocidad de render o de paralelismo hasta tener los bloques 1 a 4.
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
