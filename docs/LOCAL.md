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

## 4. YouTube

Desde una conexión de casa normalmente no hace falta nada. Si aparece
«Sign in to confirm you're not a bot», exporta las cookies de YouTube (extensión
"Get cookies.txt LOCALLY", mejor con una cuenta secundaria) a:

- Windows: `C:\Users\<tu usuario>\.config\edit-vid3\youtube-cookies.txt`
- Mac/Linux: `~/.config/edit-vid3/youtube-cookies.txt`

## 5. Hacer un vídeo

1. Crea `materiales/<nombre>/` con `guion.txt`, `voz.mp3` y `titulo.txt`.
2. Opcional, `materiales/<nombre>/config.yaml` con ajustes solo para ese vídeo, por ejemplo:
   ```yaml
   timeline:
     cold_open_seconds: 10   # 10 s de los mejores momentos del protagonista con su sonido original
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
- `miniaturas/miniatura-1..3.jpg` — 3 miniaturas (recorte del atleta + frame de su gran momento + frase corta)
- `youtube.txt` — para YouTube Studio: 3 títulos a elegir, descripción, capítulos con minutos, fuentes y etiquetas (copiar y pegar)

Si algo falla, vuelve a lanzar el mismo comando: cada etapa terminada se salta y continúa donde
se quedó. `--force <etapa>` rehace una etapa concreta (y las siguientes).

## 6. Cola nocturna (varios vídeos seguidos)

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

## 8. Tiempos y coste orientativos (vídeo de 10 min)

- 1,5–2 h en un PC de 4 núcleos (menos con más núcleos): lo más largo es buscar/analizar
  metraje y el render. El PC va al máximo durante el análisis y el render.
- APIs: ~0,4–0,6 $ por vídeo (juez de visión + planner; + ~0,1 $ si usas Serper).
