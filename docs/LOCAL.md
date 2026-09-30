# Generar vídeos en tu PC

Guía para ejecutar el pipeline completo en local (Windows, Mac o Linux).

## 1. Programas necesarios (una sola vez)

| Programa | Versión | Windows | Mac |
|---|---|---|---|
| Python | 3.11 o 3.12 | python.org → marcar "Add to PATH" | `brew install python@3.11` |
| Node.js | 20 o superior | nodejs.org (LTS) | `brew install node` |
| ffmpeg | 6 o superior | `winget install Gyan.FFmpeg` | `brew install ffmpeg` |
| Git | cualquiera | git-scm.com | `brew install git` |

Comprueba en una terminal nueva: `python --version`, `node --version`, `ffmpeg -version`.

## 2. Descargar el proyecto

```bash
git clone https://github.com/IsaacAndreu/edit-vid3.git
cd edit-vid3
git checkout claude/pensive-bell-5pi66r
python -m pip install -r requirements.txt
npm install
```

La primera ejecución descarga además el modelo de transcripción (Whisper medium, ~1,5 GB) y el de
imágenes (CLIP, ~600 MB). Remotion descarga su propio Chrome si no encuentra uno.

## 3. Claves (`.env` en la carpeta del proyecto)

Copia `.env.example` a `.env` y rellena las mismas claves que tienes en la nube:

```
LLM_PROVIDER=...        # planner (DeepSeek)
LLM_MODEL=...
LLM_API_KEY=...
OPENAI_API_KEY=...      # juez de visión (gpt-5-mini)
PEXELS_API_KEY=...      # último recurso de metraje
SERPER_API_KEY=...      # opcional: fotos de Google Imágenes. Sin ella usa DuckDuckGo (gratis, funciona desde casa)
```

`.env` nunca se sube a GitHub.

## 4. YouTube (cookies de varias cuentas)

Si aparece «YouTube bloquea este equipo (Sign in to confirm you're not a bot)», YouTube está
frenando las búsquedas automáticas desde tu conexión. Se soluciona con cookies de cuentas de
YouTube (mejor secundarias, nunca la del canal); con varias, las peticiones se reparten entre ellas
y si YouTube bloquea una se aparta y siguen las demás.

1. Con cada cuenta secundaria abierta en el navegador (una ventana/perfil por cuenta), entra en
   youtube.com y exporta las cookies con la extensión «Get cookies.txt LOCALLY» → Export.
2. Guarda cada archivo (formato Netscape .txt o JSON, da igual), con el nombre que quieras, en la
   carpeta `cookies` del proyecto: `edit-vid3\cookies\cuenta1.txt`, `cuenta2.txt`… (no se sube a
   GitHub). También vale `~/.config/edit-vid3/cookies/`.
3. Al lanzar verás «YouTube: 4 cuenta(s) de cookies, por turnos».

**Cookies que no caducan (Firefox con contenedores).** En vez de exportar a mano, el programa puede
leer las cookies de Firefox en cada ejecución, siempre frescas:

1. Instala Firefox y la extensión oficial **Firefox Multi-Account Containers**.
2. Crea un contenedor por cuenta (p. ej. `Cuenta1`, `Cuenta2`, `Cuenta3`) y, dentro de cada uno,
   entra en youtube.com con esa cuenta secundaria.
3. En `config.yaml` → `sourcing: youtube:` pon:
   `browser_accounts: ["firefox::Cuenta1", "firefox::Cuenta2", "firefox::Cuenta3"]`
4. Abre Firefox de vez en cuando (y mira algún vídeo con cada cuenta) para que las sesiones sigan vivas.

Solo se leen las cookies de YouTube/Google, nada más del navegador. Con Chrome no funciona
(desde 2024 cifra las cookies para que otros programas no puedan leerlas).

**Búsquedas con tus claves de la API.** Con `YOUTUBE_API_KEYS` en `.env`, las búsquedas van por la
API oficial (sin bloqueos). Cada vídeo gasta ~45.000 unidades; con ~100.000 al día cubre unos 2
vídeos, y cuando se acaba la cuota sigue buscando con yt-dlp y tus cookies.

Las cookies duran semanas o meses; cuando una caduca verás «YouTube bloqueó cuenta2.txt» y basta
con volver a exportarla. Mantén yt-dlp al día: `pip install -U yt-dlp`.

## 5. Hacer un vídeo

1. Crea `materiales/<nombre>/` con `guion.txt`, `voz.mp3` y `titulo.txt`.
2. Opcional, `materiales/<nombre>/config.yaml` con ajustes solo para ese vídeo, por ejemplo:
   ```yaml
   timeline:
     cold_open_seconds: 10   # 10 s de los mejores momentos del protagonista con su sonido original
     moments: 2              # 2 pausas en el clímax con el sonido original de la competición (0 = ninguna)
   ```
3. Ejecuta:
   ```bash
   python main.py --slug <nombre>
   ```
   Con `--review` se para tras la QA para revisar antes de renderizar.

Resultado en `out/<nombre>/`:

- `video-final.mp4` — el vídeo (1080p, audio a −16 LUFS)
- `creditos.txt` — fuentes para la descripción de YouTube
- `qa/report.md` y `qa/contact-sheet.jpg` — revisión: planos flojos, reparto por fuente, coste
- `manifest.json` — de dónde sale cada plano
- `verificacion.md` — datos del guion comprobados (❌ a corregir, ⚠️ sin confirmar, ✅ confirmados)
- `miniaturas/miniatura-1..3.jpg` — 3 miniaturas (recorte del atleta + frame de su gran momento + frase corta)
- `subtitulos.es.srt` — subtítulos para subir en YouTube Studio → Subtítulos
- `youtube.txt` — para YouTube Studio: 3 títulos a elegir, comentario para fijar, post de comunidad, descripción, capítulos con minutos, fuentes y etiquetas (copiar y pegar)

Si algo falla, vuelve a lanzar el mismo comando: cada etapa terminada se salta y continúa donde
se quedó. `--force <etapa>` rehace una etapa concreta (y las siguientes).

## 6. Cola nocturna (varios vídeos seguidos)

**Registro y diagnóstico de cada vídeo.** Todo lo que sale por pantalla se guarda con la hora en
`out/<vídeo>/log.txt`. Al terminar, o si falla, se escribe `out/<vídeo>/diagnostico.md` con:
- **Qué mejorar:** consejos concretos según lo que pasó (descargas lentas y su causa, cuentas bloqueadas,
  descargas fallidas agrupadas por motivo, demasiado stock, datos del guion incorrectos, render lento, poco
  disco…).
- **Detalles:** tiempo por etapa, tiempos de YouTube, de dónde salió el relleno, qué hay en pantalla, coste y
  versiones del entorno.

Si falla, también está el error completo. En `out/_cola.md` sale lo primero a mejorar de cada vídeo.
Cuando algo vaya mal, pásame ese `diagnostico.md`: es lo más rápido para arreglarlo.

**Dos vídeos a la vez.** Con `queue: {parallel_videos: 2}` en `config.yaml` (viene así por defecto),
la cola trabaja con dos vídeos a la vez por turnos: mientras uno busca o descarga de YouTube, el otro
analiza o renderiza, así que el PC no se queda parado esperando a YouTube. Cada línea lleva delante el
nombre de su vídeo y el registro completo queda en `out/_cola/<vídeo>.log`. Con `parallel_videos: 1`
vuelve a ir de uno en uno.

**Si la descarga en HD va lenta** (la etapa `ingest` tarda más de 20-30 min), casi siempre es que
yt-dlp no puede resolver los «retos» de YouTube y este sirve los vídeos a paso de tortuga. La cola ya
actualiza todo lo necesario al empezar y lo muestra en la primera línea
(`yt-dlp … · retos (yt-dlp-ejs) … · JavaScript: deno`). Si sale `FALTA` o `NINGUNO`:

```powershell
pip install -U "yt-dlp[default]" deno
```

Al final de la descarga aparece `Tiempos YouTube: download N× X s …`: menos de 10 s por tramo es normal.

Deja por la tarde cada vídeo en su carpeta (`materiales/<nombre>/` con `guion.txt`, `voz.mp3`,
`titulo.txt`) y lanza:

```bash
python main.py --all            # todos los pendientes, uno detrás de otro
python main.py --all --limit 3  # como mucho 3 esta noche
```

- Pendiente = tiene guion y voz pero aún no tiene `out/<nombre>/video-final.mp4`. Se procesan
  por orden de llegada.
- Si uno falla, se apunta y la cola **sigue con el siguiente**. Al terminar (y tras cada vídeo)
  queda un resumen en `out/_cola.md`: estado, tiempo y motivo de cada fallo. Para reintentar
  uno fallido basta con volver a lanzar la cola: retoma donde se quedó.
- No se pueden lanzar dos colas a la vez. Si el PC se apagó en mitad de una, borra
  `work/.cola.lock` antes de volver a lanzarla.

Antes de empezar, la cola comprueba claves, espacio libre (mínimo 20 GB), ffmpeg/Node y que YouTube
responda; si algo falla no arranca y lo dice (mejor saberlo a las 0:00 que a las 3:00).

**Aviso al móvil (opcional, Telegram):** al terminar (o si no puede arrancar) te llega el resumen.

1. En Telegram, habla con **@BotFather** → `/newbot` → te da un token.
2. Escribe cualquier cosa a tu bot nuevo y abre
   `https://api.telegram.org/bot<TOKEN>/getUpdates` en el navegador: el número `"chat":{"id": …}` es tu chat.
3. Añade a `.env`: `TELEGRAM_BOT_TOKEN=...` y `TELEGRAM_CHAT_ID=...`.

**Que el PC no se duerma:** si entra en suspensión, la cola se pausa.

- Windows: Configuración → Sistema → Inicio/apagado y suspensión → «Nunca» (al menos enchufado),
  o en una terminal de administrador: `powercfg /change standby-timeout-ac 0`.
- Mac: lanza la cola con `caffeinate -i python main.py --all`.

**Que empiece sola a una hora** (opcional):

- Windows (Programador de tareas), una sola vez desde la carpeta del proyecto:
  ```
  schtasks /create /tn "Videos cola" /sc daily /st 01:00 /tr "cmd /c cd /d %CD% && python main.py --all > out\cola.log 2>&1"
  ```
- Mac/Linux (`crontab -e`):
  ```
  0 1 * * * cd /ruta/a/edit-vid3 && python3 main.py --all > out/cola.log 2>&1
  ```

Con un PC de 6–8 núcleos, 2–3 vídeos de 10 min caben de sobra en una noche (1–1,5 h cada uno).

**Aviso por email (opcional):** con Gmail crea una *contraseña de aplicación* (Cuenta de Google →
Seguridad → Verificación en dos pasos → Contraseñas de aplicaciones) y añade a `.env`:

```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=tucuenta@gmail.com
SMTP_PASSWORD=la-contraseña-de-aplicación
EMAIL_TO=tucuenta@gmail.com
```

Al terminar cada vídeo te llegan las 3 miniaturas y los 3 títulos (por email y/o Telegram).

## 7. Tres ideas diarias

En `config.yaml`, sección `ideas:`, pon tu canal (`my_channel: "@tucanal"`) y los canales de la
competencia (`competitors`). Luego:

```bash
python main.py --ideas
```

Mira los últimos vídeos de cada canal (sin API de YouTube), calcula cuántas veces supera cada uno
la mediana de su canal (outliers ≥ `min_ratio`) y propone 3 ideas (título, enfoque, hook y qué
comprobar) que no repiten temas ya hechos o ya sugeridos. Resultado en `out/_ideas/<fecha>.md` y
por email/Telegram. Los títulos que mejor funcionan también sirven de patrón para los títulos y
miniaturas de cada vídeo.

Cada mañana a las 9 (Windows, una vez desde la carpeta del proyecto):

```
schtasks /create /tn "Ideas videos" /sc daily /st 08:52 /tr "cmd /c cd /d %CD% && python main.py --ideas > out\ideas.log 2>&1"
```

## 7b. Música y transiciones

- **Transiciones:** `assets/sfx/whoosh*.mp3`. Suena casi siempre la de `timeline.whoosh_main`
  (espada) y 1 de cada 4 otra, en capítulos, momentos, cold open, tarjetas y cifras.
- **Música de fondo:** `assets/music/<tono>-<nombre>.mp3`, con tono = `intriga`, `triunfo`,
  `caida`, `tension`, `remontada` o `infancia`. Cada capítulo recibe el tono que le pega (lo decide
  el LLM entre los tonos que tengan pistas) y la música cambia con un fundido de 4 s. Entre vídeos
  se alternan las pistas de cada tono (las menos usadas primero: `cache/music_usage.json`).
  Todas se nivelan solas; se repiten en bucle con fundido si el capítulo es más largo.
- Volumen: `timeline.music_volume` (en las pausas) y `timeline.duck_db` (cuánto baja bajo la voz).

**Pantalla final:** los últimos 20 s (`timeline.endscreen_seconds`) son el fondo del canal con un
recuadro «SIGUIENTE HISTORIA» y un círculo «SUSCRÍBETE»: en YouTube Studio → Pantalla final, pon
un vídeo sugerido encima del recuadro y el botón de suscribirse sobre el círculo. La música se
desvanece al final.

**Gráficos animados:** el sistema lee el guion y mete solo mapas (rutas, ciudades, zoom, globo),
comparativas A vs B, gráficas de barras/líneas/tarta, líneas de tiempo con años, fichas (EN CIFRAS
para personas, FICHA TÉCNICA para productos), tarjetas de ranking y texto cinético donde explican
mejor que un clip (~1 cada 100 s, sección `graphics:` de config.yaml). Todo dato que muestran
tiene que decirse en el guion; las ciudades se sitúan con OpenStreetMap. Muestra de todas las
plantillas: `out/plantillas-animadas.mp4`.

**Kit de marca:** los colores de todas las plantillas salen de `brand:` en config.yaml (dorado y
morado en gimnasia). Para otro canal basta con otro `brand:` (en su config.yaml).

**Efectos:** zoom o barrido con desenfoque en los cortes con transición, un «pop» por cada barra,
chincheta o dato que aparece y un golpe con temblor de cámara y destello cuando cae una cifra
grande (`assets/sfx/pop-*.mp3`, `impact-*.mp3`; cámbialos por los tuyos si quieres). Los mapas van
inclinados en perspectiva, con relieve suave y un avión que recorre la ruta.

## 8. Panel de investigación (tipo TubeLab)

Añade tus claves de la API de YouTube a `.env`, separadas por comas (si alguna tiene más cuota que
la normal de 10 000 unidades, ponla como `clave:50000`):

```
YOUTUBE_API_KEYS=clave1,clave2,clave3,clave4,clave5,clave6
```

y abre el panel:

```bash
python main.py --panel
```

Se abre en el navegador (`http://127.0.0.1:8765`, solo en tu PC). Pestañas:

- **Outliers**: busca un tema en todo YouTube y te enseña los vídeos que han hecho muchas más
  visitas que la media de su propio canal (x2, x5, x10…). Filtros: fecha, duración, ratio mínimo,
  suscriptores máximos (para encontrar canales pequeños que lo están petando) e idioma. Los botones
  rápidos son las búsquedas de `lab.queries` en `config.yaml`.
- **Canal**: suscriptores, mediana de visitas, cada cuánto sube y sus vídeos ordenados por ratio.
- **Guardados**: lo que marcas con «Guardar». Las ideas diarias también se inspiran en ellos.
- **Ideas**: las del día y un botón para generar 3 nuevas.

Cuota: cada búsqueda cuesta ~100–160 unidades (100 la búsqueda + ~1–2 por canal nuevo; lo repetido sale
de la caché). Con 100 000 unidades al día son unas 600 búsquedas. Arriba a la derecha ves lo que
queda hoy; cuando una clave se agota pasa sola a la siguiente, y se renuevan a las 9:00 (hora de España).

Con claves configuradas, `--ideas` busca además outliers en todo el nicho (las 6 primeras
búsquedas de `lab.queries`, ~1 000 unidades al día), no solo en los canales de la competencia.

## 9. Verificar el guion antes de grabar

```bash
python main.py --check <nombre>
```

Solo necesita `materiales/<nombre>/guion.txt`. Saca las afirmaciones comprobables (fechas,
resultados, edades, récords, citas…) y las contrasta con Wikipedia y búsquedas web →
`out/<nombre>/verificacion.md`. Hazlo antes de grabar la voz: corregir un dato después obliga a
regrabar. En la cola también se hace solo, pero no para el vídeo (salvo `factcheck.block_on_wrong: true`).

## 10. Shorts (solo cuando tú quieras)

```bash
python main.py --shorts <nombre>
```

Con el vídeo ya terminado, elige los 3 mejores momentos (25–58 s) y los saca en vertical con
subtítulos grandes y una frase gancho arriba → `out/<nombre>/shorts/` (+ `shorts.txt` con título y
descripción de cada uno). Si quieres que un vídeo concreto los haga solo en la cola, pon en su
`materiales/<nombre>/config.yaml`: `shorts: {enabled: true}`.

## 10b. Versiones dobladas (reutilizando el vídeo hecho)

1. Deja la narración traducida junto al original: `materiales/<nombre>/voz-en.mp3` (en, pt, fr, it, de).
   Opcional: `guion-en.txt` (el guion traducido) y `titulo-en.txt`. Sin guion, se usa la transcripción.
2. `python main.py --dub <nombre>:en` — o nada: la cola nocturna las detecta sola en cuanto el
   vídeo original está terminado.

Resultado en `out/<nombre>-en/`: mismos clips y mismo montaje, con los cortes reajustados a la
nueva voz, los textos en pantalla traducidos («CHAPTER», «Source»), y sus miniaturas y
títulos en ese idioma. No vuelve a buscar ni a juzgar metraje: ~15-25 min, casi todo render.
Si un plano queda más largo que su clip, va en cámara lenta suave.

## 10d. Editor antes del render (tipo CapCut)

Para revisar y retocar un vídeo antes de gastar el tiempo de render:

```powershell
python main.py --slug Video1 --review     # hace todo menos el render
python main.py --editor Video1            # abre http://127.0.0.1:8766 (Chrome o Edge)
```

La pantalla tiene cuatro zonas:
- **Arriba a la izquierda, la biblioteca:**
  - **Plantillas:** mapa, podio, marcador, prensa, carta de jugador, texto cinético… Arrástrala a la
    línea de tiempo o haz clic para ponerla en el cursor.
  - **Metraje:** buscar en YouTube o subir un clip o una foto tuya para el plano elegido.
  - **Audio:** cambiar la canción de un tramo y añadir efectos.
- **En el centro, la vista previa**, con los mismos gráficos, rótulos y música del render final.
  «Ver solo esta escena» reproduce solo la escena elegida.
- **A la derecha, las propiedades** de lo que hayas seleccionado: textos y cifras de un gráfico,
  otras opciones de metraje del análisis (al pasar el ratón ves el fragmento), mover el fragmento
  ±0,3 s o ±1 s, volumen de un efecto…
- **Abajo, la línea de tiempo** con las pistas Escenas, Vídeo, Gráficos, Rótulos, Voz (onda y palabras
  con zoom), Música y Efectos. Qué puedes hacer en ella:
  - **Recortar un plano:** arrastra su borde izquierdo. El corte se engancha a la palabra más cercana
    y la transición y su «whoosh» se mueven con él.
  - **Intercambiar dos planos:** arrastra uno encima del otro.
  - **Mover o estirar** gráficos, rótulos y efectos.
  - **Reordenar la historia:** arrastra una escena. La voz, la música y los subtítulos se mueven con
    ella. También puedes eliminar una escena entera.
  - **Zoom:** con la barra o con Ctrl + rueda.

Atajos: **Ctrl+Z / Ctrl+Y** deshacer y rehacer · **Supr** quitar lo seleccionado · **Espacio** reproducir.
«⚠ flojos → siguiente» salta al siguiente plano que el juez eligió con menos seguridad (o que es stock).

Casi todo se ve al momento. El metraje nuevo de YouTube (otra opción, fragmento movido o búsqueda) se
descarga al pulsar **«Aplicar cambios de planos»** (1-3 min). **«Renderizar vídeo»** hace el vídeo
final con todo. Los cambios se guardan en `work/<vídeo>/edits.json` y se respetan aunque vuelvas a lanzar
una etapa.

## 10c. Varios canales (perfiles) y vídeos de ranking

Cada canal tiene su perfil en `canales/<canal>.yaml`. Allí van los colores, la música/SFX, las
fuentes de confianza, la competencia, las búsquedas del panel y el formato. Se mezcla encima de
`config.yaml`, y la `config.yaml` de cada vídeo va encima del perfil.

- Por defecto se usa `canal: gimnasia` (en `config.yaml`).
- Para un vídeo de otro canal, crea `materiales/<vídeo>/config.yaml` con:
  ```yaml
  canal: robots
  ```
- Ideas y panel de otro canal: `python main.py --ideas --canal robots` (se guardan en
  `out/_ideas/robots/`) y `python main.py --panel --canal robots`.
- Música y efectos del canal: `assets/robots/music/` y `assets/robots/sfx/`, con los mismos nombres
  (`tension-*.mp3`, `whoosh-*.mp3`…). Si están vacías, se usan las de `assets/`.
- Un canal nuevo: copia `canales/robots.yaml` con otro nombre y cambia lo que quieras.

Con `format: ranking` (el perfil de robots ya lo trae), el vídeo es una cuenta atrás sin
protagonista:
- cada puesto que el guion presenta («en el número 7…», «puesto 3:») lleva una tarjeta **#7/10** con
  el nombre, hasta 3 cifras dichas en ese puesto y una imagen de su metraje;
- si el puesto es una ciudad o un país, justo después sale un mapa que vuela hasta él;
- el resto de gráficos (comparativas, fichas técnicas, gráficas) se reparten como siempre.

Con `format: prohibidos` (en la `config.yaml` del vídeo), el vídeo repasa cosas prohibidas de un
deporte (elementos, técnicas, trajes…). Cada elemento que presenta el guion lleva una tarjeta con su
clip, un sello rojo de **PROHIBIDO** que cae encima, quién lo hizo famoso, por qué se prohibió y
«DESDE 1977», siempre que el guion lo diga.

Animaciones que salen solas en cualquier formato, siempre sacadas del guion:
- **Congelado con foco:** la primera vez que se nombra a alguien sobre un clip suyo (el título del
  vídeo de YouTube lleva su nombre), la imagen se para con un flash, todo se oscurece salvo esa
  persona y aparece su nombre. Máximo 3 por vídeo (`timeline.spotlights`, 0 = ninguno).
- **Pantalla partida:** cuando el guion contrasta dos personas o dos momentos («Uchimura en Tokio,
  Yulo en París»), sus dos clips lado a lado.
- **Nota desglosada:** dificultad + ejecución − penalización = nota. Solo si el guion dice las
  cifras y estas cuadran.
- **Recortes de prensa:** titulares hechos con palabras del guion. El nombre del periódico solo
  sale si el guion lo nombra.
- **Reglamento:** la página del reglamento con la norma subrayada y, si prohíbe algo, un sello.

Más formatos (en la `config.yaml` del vídeo):
- `format: tecnica`: explica cómo se hace un movimiento. Busca el metraje con la cámara lo más quieta
  posible y usa mucha estroboscopia y repetición.
- `format: final`: narra una final participante a participante. Usa el marcador en directo, la nota
  desglosada y repeticiones en los momentos clave.

- `format: lista`: casos sin numerar («los fallos que sorprendieron al mundo»), con un protagonista
  distinto en cada caso. Conviene subir `people: {max: 9}` para que cada uno tenga su tarjeta.
- `format: rivalidad`: dos protagonistas (A vs B). Usa comparativas, pantalla partida, una carta de cada
  uno y los resultados de sus duelos.
- `format: records`: récords imposibles. Usa la comparación de escala, la carrera de barras, la carta de
  quien lo tiene y la cifra imposible en grande.

Gráficos de la tanda 3 (en cualquier formato, cuando el guion da los datos):
- **Podio:** los bloques de bronce, plata y oro suben por turnos y cada atleta cae sobre el suyo.
- **Carrera de barras:** una cifra de varios países o personas a lo largo de los años; las barras se
  adelantan unas a otras.
- **Carta de jugador:** estilo videojuego. Entra girando, lleva un brillo holográfico y sus cifras
  (todas dichas en el guion).
- **Escala:** una marca (altura o longitud) al lado de objetos cotidianos como una persona, una canasta
  o un autobús. Estas medidas de referencia son conocidas y el programa las pone solo.

Animaciones sacadas del propio clip (necesitan `rembg`, lo mismo que las tarjetas de atleta):
- **Estroboscopia:** todas las posiciones de un salto en una sola imagen, que aparecen una a una.
  Si la cámara se mueve, se alinean los fotogramas; si hay un corte o no se distingue al atleta, no sale.
- **Repetición con rampa:** el clip va a velocidad normal, se ralentiza en el punto más alto del salto
  y vuelve a la normal, con el rótulo «REPETICIÓN», un anillo que sigue al atleta y su trayectoria dibujada.
- **Marcador en directo:** las notas entran en el orden en que se dicen y la tabla se reordena sola.

Si cambias el formato de un vídeo que ya estaba a medias, vuelve a lanzarlo con
`--force planner --force timeline`.

## 11. Tiempos y coste orientativos (vídeo de 10 min)

- 1,5–2 h en un PC de 4 núcleos (menos con más núcleos): lo más largo es buscar/analizar
  metraje y el render. El PC va al máximo durante el análisis y el render.
- APIs: ~0,4–0,6 $ por vídeo (juez de visión + planner; + ~0,1 $ si usas Serper).
