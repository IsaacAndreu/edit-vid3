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

Si algo falla, vuelve a lanzar el mismo comando: cada etapa terminada se salta y continúa donde
se quedó. `--force <etapa>` rehace una etapa concreta (y las siguientes).

## 6. Tiempos y coste orientativos (vídeo de 10 min)

- 1,5–2 h en un PC de 4 núcleos (menos con más núcleos): lo más largo es buscar/analizar
  metraje y el render. El PC va al máximo durante el análisis y el render.
- APIs: ~0,4–0,6 $ por vídeo (juez de visión + planner; + ~0,1 $ si usas Serper).
