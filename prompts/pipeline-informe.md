# Informe: fiabilidad, puntería y velocidad del pipeline (18-11-2026)

Rama: `claude/jolly-clarke-zttbs8` · 40 commits · suite: 1028 tests en verde (antes: 922 y 1 fallo del propio test).
Nada está fusionado en `main`. El detalle punto por punto está en `prompts/pipeline-progress.md`.

---

## 1. Cómo ponerlo en el servidor ya

El servidor hace `git pull` de `main` cada 2 minutos, así que desplegar = fusionar la rama en `main`.

1. **Fusionar** en GitHub: abre un PR de `claude/jolly-clarke-zttbs8` a `main` y fusiónalo (o pídeme que lo abra).
   La CI nueva (`.github/workflows/tests.yml`) correrá typecheck + comprobación rápida + tests en el PR (~10 min).
2. **En 2 minutos el servidor lo baja solo.** El vigilante (`--vigilar`) se reinicia con el código nuevo entre un
   vídeo y el siguiente; el estudio también. Los vídeos a medias **no** se rehacen: todas las claves nuevas tienen su
   valor por defecto en el código y las que solo afectan a velocidad están en `SPEED_KEYS`.
3. **Instala la dependencia nueva** (`pyflakes`, para la puerta) por SSH:

   ```bash
   cd ~/edit-vid3 && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt
   ```

   Si no lo haces no pasa nada grave: la puerta avisa y sigue comprobando que todo el código importa.
4. **Comprueba** que arrancó bien:

   ```bash
   journalctl -u edit-vid3 -n 50 --no-pager
   ```

   ```bash
   .venv/bin/python -m pipeline.puerta
   ```

   La segunda debe terminar en «Comprobación rápida: bien».

Desde ese momento, **ningún commit con un error de nombre o de importación vuelve a llegar al servidor**: el estudio,
la cola y `--actualizar` comprueban el commit nuevo en una carpeta aparte antes de ponerlo en disco, y si falla te
llega un Telegram «⛔ Código nuevo rechazado» y el servidor sigue con el anterior.

---

## 2. Qué cambia ya (encendido por defecto)

### Que no se pierdan noches
- **Puerta antes del despliegue** y **CI** en GitHub (ver arriba).
- **Prueba de extremo a extremo** (`tests/test_e2e_stages.py`): recorre las 15 etapas reales con YouTube, LLM,
  Remotion y CLIP simulados, en 5 escenarios (juez acepta / rechaza todo / descargas fallidas / sin material /
  mínimo). Habría pillado el `NameError` del 17-11, y encontró otro fallo real: la foto del protagonista para un
  momento sin metraje no podía guardarse nunca (arreglado).
- **Tramos que no envenenan la caché**: todo se escribe con nombre temporal, se valida con ffprobe y se renombra.
  Los tramos rotos que ya hay en la caché se detectan la primera vez que se usan y se vuelven a bajar.
- **Estado compartido entre procesos** con cerrojo de archivo (rechazos, cuarentenas, cookies, sesiones): dos
  vídeos a la vez ya no se pisan.
- **Plazos** en todo ffmpeg/ffprobe, los clientes de OpenAI, DuckDuckGo y las descargas enteras.
- **Un vídeo a medias ya no figura como terminado**: el render escribe a un nombre temporal y solo lo renombra tras
  sus comprobaciones; si Shorts o el paquete fallan, la cola lo reintenta.
- **Cortacircuitos en los dos modos de cola**: el mismo bug (tipo + archivo:línea) en dos vídeos, o 3 fallos seguidos
  en la misma etapa, pausan la cola (`out/_pausa`, «Reanudar» en el estudio). En paralelo, una API sin saldo o el
  tope de gasto paran los arranques en vez de marcar error todos los vídeos.
- **Los fallos de la tabla del 17-11**: el planner sobrevive a un JSON inválido; los Atlas de la cola ya tienen
  transcriptor (era un fallo: la vía de la cola no lo pasaba); los doblajes ya no dan «validation errors for
  Timeline» (causa probable, ver §4).

### Menos peticiones perdidas a YouTube
- Cada fila fallida de `youtube_downloads.jsonl` dice **por qué** (`cause`: túnel del proxy, proxy sin respuesta,
  formato no disponible, ffmpeg, conexión cortada, 5xx…). Los vídeos ya descartados no cuentan como fallo.
- Un túnel del proxy que no abre (4 442 casos) se reintenta con otra sesión antes de perder el vídeo.
- Subtítulos de YouTube con su propio ritmo (1 cada 3 s) y caché negativa: eran la mayoría de los 429.
- Un vídeo borrado/privado no se vuelve a pedir en ninguna etapa (la apertura lo pedía 1 070 veces).
- Segmentos HLS: 3 a la vez por la misma sesión, con reintento por segmento, y si la sesión rotó de IP se
  re-extrae antes (antes era un 403 de pago seguro).
- Las esperas largas (presupuesto horario, enfriamiento tras un 429) ya no bloquean un hueco de conexión.
- El aviso de proxy caído ya no habla de Tailscale cuando es el proxy de pago.

### Clips más de lo que se cuenta
- **Búsqueda**: con la API, el suceso + la búsqueda más concreta del plano (la del momento primero), 30 resultados
  por búsqueda (mismo coste de cuota) ordenados por nombre completo, suceso y año en título y descripción.
- **Planner**: instrucciones de búsqueda para cualquier tema (crimen, negocios, megaproyectos, historia,
  videojuegos), no solo deporte.
- **Análisis**: hasta 120 miniaturas por vídeo (antes 40: una cada 30 s en un vídeo de 20 min); CLIP puntúa con lo
  que se ve (momento + intención visual), no con nombres y años.
- **Juez**: nunca tres copias de la misma miniatura; un error de la API se reintenta y luego va al relleno (antes, en
  silencio, al orden de CLIP); la continuación de la acción solo usa segundos que el juez vio y aceptó.
- **Relleno**: si falla la descarga del clip elegido, usa primero las otras opciones que el juez ya aceptó.

### Medir
- `diagnostico.md` de cada vídeo trae dos tablas nuevas: **«De dónde salió cada plano»** (primera elección del
  juez, otra opción juzgada, relleno juzgado / sin juzgar, foto, rótulo, heredado…) y **«Material descartado»**
  (por motivo: candidatos perdidos y planos que se quedaron sin vídeo por él).
- `python main.py --informe-analisis` da la primera tabla por canal.
- `python main.py --tiempos` separa trabajo, espera de turno e intentos fallidos.

---

## 3. Qué mirar los próximos días

**Día 1 (tras los primeros vídeos):**
- `journalctl -u edit-vid3 -f`: que no aparezca «Cola en pausa». Si aparece, el mensaje dice el error y el archivo:
  copia el informe del vídeo y pásamelo.
- Si un vídeo se queda en «haciendo» sin avanzar, mira `out/_cola/<vídeo>.log` (ahora conserva los intentos
  anteriores).
- `out/<vídeo>/diagnostico.md` del primer vídeo terminado: las dos tablas nuevas.

**Sin red, con lo que ya hay en el servidor:**

```bash
.venv/bin/python -m pipeline.diag_hls 7
```

Dice si las extracciones en caché traen HLS y por qué los tramos se bajaban enteros (63 % de los GB del proxy).
Pásame `out/_diag_hls.md`: es lo que falta para arreglar la causa.

**Al cabo de 2-3 días:**

```bash
.venv/bin/python main.py --youtube-stats 3
```

Mira: las **causas** de los fallos (debe bajar «sin-texto» a casi nada), los **429** (deberían caer con el ritmo de
subtítulos), y «Vídeos ya descartados, no pedidos».

```bash
.venv/bin/python main.py --tiempos 3
```

Mira la columna de **espera de turno** y la de **intentos fallidos**: dicen cuánto se pierde esperando y cuánto en
vídeos que murieron.

```bash
.venv/bin/python main.py --informe-analisis
```

La columna «primera elección del juez» por canal es la cifra de puntería: guárdala para comparar con cada cambio.

**Ojo con estos cambios encendidos** (si algo empeora, cómo volver atrás, en `config.local.yaml`):

| Si ves… | Vuelve atrás con |
|---|---|
| el análisis bastante más lento (más miniaturas por vídeo) | `analysis: {max_frames_cap: 40}` |
| peor puntería con el texto nuevo de CLIP | `analysis: {clip_queries: true}` |
| más fallos en descargas HLS (3 segmentos a la vez) | `sourcing: {youtube: {hls_segment_workers: 1}}` |
| más planos a relleno por errores del juez | `judge: {on_error: puntuacion}` |
| la cola pausada por 3 fallos seguidos en una etapa sin ser un bug | `queue: {breaker_same_stage: 0}` |

---

## 4. Opciones apagadas, para probar una a una

Ponlas en `config.local.yaml`, haz un vídeo y compara con los comandos de la tabla. Todas están documentadas en
`docs/VPS.md`, apartado 3h.

| Opción | Qué hace | Cómo saber si sirve |
|---|---|---|
| `sourcing.youtube.byte_ranges: true` | vídeos sin HLS por rangos de bytes en vez de enteros o descartados | `--youtube-stats`: «download (rango)», GB por vídeo; «Material descartado» (sin HLS) |
| `sourcing.youtube.pace_per_session: true` | ritmo por sesión (IP) del proxy, no uno para todo | `--youtube-stats 2` antes/después: % fallidas, bot, 429; `--tiempos`: espera |
| `sourcing.youtube.player_skip: [configs]` | quita ~0,9 MB por extracción (8 GB/semana) | **antes**: `python -m pipeline.sonda_ytcfg`; solo si dice «se puede encender» |
| `sourcing.youtube.api_overflow: mixto` | sin cuota de la API busca por yt-dlp con tope (60/h) en vez de esperar al día siguiente | vídeos en «espera cuota»; bot/429 en `--youtube-stats` |
| `sourcing.youtube.api_local_query: true` | una búsqueda más por plano en el idioma del guion (+100 unidades) | «primera elección del juez» |
| `analysis.hd_windows_top: 1` | la mejor ventana de cada plano se baja ya en HD | GB y minutos de archivo a360 + hd; `--tiempos` |
| `analysis.chapter_windows: true` | ventana donde un capítulo del vídeo fuente nombra el momento | «De dónde salió cada plano» |
| `judge.model_hook: <modelo fuerte>` | modelo bueno solo en el gancho (judge.model se dejó en el barato) | `python -m pipeline.rejuzgar <vídeo> <modelo>` |
| `judge.frames_per_candidate: 4`, `judge.tile_width: 400` | hojas del juez más ricas (más tokens) | gasto del juez y «primera elección» |
| `fallback.judge_pexels: true`, `fallback.judge_filler: true` | el stock y el relleno del protagonista pasan por el juez | «relleno sin juzgar» en la tabla |

Mi orden recomendado: `sonda_ytcfg` → `player_skip`; luego `byte_ranges`; luego `pace_per_session` (la que más
tiempo puede ahorrar, y la más delicada con YouTube); y `judge_pexels` en un canal con mucho stock (GTA).

---

## 5. Lo que no está hecho (siguiente sesión)

- **Fase 1** restante: 1.5 (reintentos de errores pasajeros en casa/directo), 1.7 (registrar los `except`
  silenciosos), 1.8 (imágenes: un ritmo por host, en paralelo), 1.9 (yt-dlp con vuelta atrás si la sonda falla),
  1.10 (retirar la ruta antigua `fetch_media.py`).
- **Fase 2** restante: perro guardián que mata un proceso colgado, estado de la cola guardado tras cada vídeo y
  `KillMode=mixed`, preflight completo, topes de gasto dentro del juez y el relleno.
- **Fases 3, 4 y 5**: menos bytes y recodificaciones en descargas, render más rápido sin cambiar un píxel (empaquetar
  Remotion una vez, segmentos en paralelo, tramos…), etapas en paralelo. Esto es «mejorar el motor»: lo vemos después.
- **Puntería**: localizar el momento por subtítulos en todos los planos (traducir la narración: tiene coste);
  `playlistItems` para canales de confianza.
- **Límite de 5 s por clip de terceros**: sigue fijo en el código (lo validan 29 sitios). Es tu protección frente a
  Content ID; hacerlo configurable es un cambio delicado para otra sesión.
- **Doblajes**: el arreglo de «validation errors for Timeline» se basa en la causa más probable que se ve en el
  código; si vuelve a pasar, pásame el log del doblaje.
