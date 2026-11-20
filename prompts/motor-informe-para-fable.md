# El motor de los vídeos: qué falla y cómo mejorarlo (informe para una segunda opinión)

Fecha: 20-11-2026. Repositorio: `IsaacAndreu/edit-vid3` (rama `main`).

## 1. Qué es esto

Un programa que hace vídeos de YouTube de estilo documental casi solo. Le das un guion y una voz; él busca clips en
YouTube y otras fuentes, elige el trozo que corresponde a cada frase, monta el vídeo con Remotion y ffmpeg y lo deja
listo para subir. Corre en un servidor (cola nocturna, `python main.py --vigilar`) con un estudio web para los
dueños de los canales. Canales: gimnasia y deporte, historia, accidentes aéreos, casos «Buscando la verdad», y uno
nuevo de GTA (videojuego).

**El problema principal hoy no es la fiabilidad ni la velocidad (se trabajó en eso), sino la PUNTERÍA: que cada plano
enseñe exactamente lo que dice la frase, sin cosas sin sentido ni planos repetidos.**

## 2. Cómo se elige la imagen de cada frase (las etapas)

`pipeline/runner.py` → `STAGES`, en orden:

1. `factcheck`, `align` (Whisper: tiempo de cada palabra), `planner` (LLM: parte el guion en planos de ~2,6 s y, por
   plano, escribe `broll`: `visualIntent`, `queries` en inglés y español, `entities`, `event`, `moment`, `avoid`…;
   `pipeline/planner.py`, esquema en `pipeline/schemas.py` → `Shot`, `BrollSpec`).
2. `sourcing` (`pipeline/sourcing/__init__.py`): por plano, búsquedas en YouTube (API oficial y yt-dlp, por un proxy
   residencial de pago), biblioteca de vídeos ya usados de la misma persona, imágenes web, archivo histórico.
   Salida: `work/<vídeo>/candidates/<plano>.json`.
3. `analysis` (`pipeline/analysis/__init__.py`): CLIP sobre las miniaturas del storyboard de cada candidato → ventanas
   prometedoras → baja ventanas de 360p → puntúa. Salida: `work/<vídeo>/scores/`.
4. `judge` (`pipeline/judge.py`): un modelo de visión (OpenAI, `gpt-5-mini` por defecto) ve una hoja de contactos de
   las mejores opciones y elige o rechaza. Salida: `selection.json`.
5. `ingest`: baja en HD el trozo elegido (≤ 5 s por clip de terceros: protección de Content ID).
6. `people` (tarjetas de personas), `fallback` (`pipeline/fallback.py`): lo que el juez rechazó o no se pudo bajar
   se rellena en este orden: siguiente opción aceptada → otro clip del protagonista (`protagonist`) → metraje del
   mismo suceso de planos vecinos (`event-footage`) → segunda búsqueda escrita por un LLM (`re-search`) → foto web →
   Pexels → otro momento cualquiera del protagonista (`protagonist-filler`) → foto del protagonista → imagen generada.
7. `coldopen`, `timeline` (`pipeline/timeline.py`): monta la línea de tiempo. Los planos que siguen vacíos se tapan
   con `fill_empty_shots` (ver §4), y si no, con una «pizarra» de palabras clave.
8. `qa`, `render`, `shorts`, `package`.

Correcciones a mano: en el estudio, pantalla «Errores», se marca un plano malo con un motivo
(`pipeline/feedback.py` → `REASONS`); queda en `work/<vídeo>/revision.json` y la etapa `fallback` lo sustituye.
El juez además lee las correcciones pasadas del canal como «lecciones» (`judge._lessons`).

## 3. Lo que se midió: el revisor automático sobre `newgym3`

Nuevo: `python -m pipeline.revisor <vídeo>` (`pipeline/revisor.py`, modo informe, no cambia nada). Mide planos negros
y repetidos sin modelo, y pide a un modelo de visión solo fallos objetivos (no tiene que ver con la frase, otra
persona, dibujos/videojuego, marca de agua) con una prueba por plano. En `newgym3` (vídeo de ~10 min sobre Simone
Biles, 221 planos con imagen), coste 0,013 $:

| Motivo | Planos |
|---|---|
| Repetido | 57 |
| No tiene que ver con la frase | 15 |
| Roto (en realidad: el revisor no pudo leer el clip; fallo del revisor) | 5 |
| Sale otra persona | 2 |
| Dibujo animado (los Minions) | 1 |

Por quién eligió el plano: «?» (tapado en `timeline`, sin selección propia) 32, `judge` 29, `protagonist` 11,
`protagonist-filler` 6, `event-footage` 2.

Comprobado mirando las hojas con las imágenes: casi todo lo marcado es real.

## 4. Causas encontradas

**A. Huecos tapados con clips de cualquier parte del vídeo** (`pipeline/timeline.py`, `fill_empty_shots`, ~línea 1064;
se llama 2-3 veces desde la función de montaje, ~línea 803, con `max_uses` 2, 5 y 6). Un plano sin clip recibe el clip
de otro plano: el **más lejano en el tiempo** (`max(fitting, key=lambda d: abs(d.from_ - start) - 600 * uses)`), con
un zoom «para que no parezca repetido». No mira de qué habla la frase. Resultado en `newgym3`: el vídeo de la boda de
Simone (que corresponde a 9:57) aparece en 0:58 con «tiene seis títulos mundiales», en 1:20 con «salto, barras, viga
y suelo», en 1:48 con «fue la más bajita del equipo»; un jugador de fútbol americano con «con veintisiete años». La
mayoría de los «Repetido · fotogramas casi idénticos» son estos préstamos.

**B. Los mismos segundos de una fuente en varios planos** (`pipeline/fallback.py`). El relleno del protagonista puso
58-60 s del mismo vídeo de entrenamiento en siete planos (0:07, 0:09, 0:10, 0:14, 0:41, 6:53…); `protagonist` usó
un tramo 3-4 veces seguidas (7:41-7:54). Causa: el filtro de tramos solo existía en el relleno y se miraba antes de
reservar, mientras varios planos se resuelven a la vez en hilos. **Arreglado** (commit «Relleno: nunca los mismos
segundos de una fuente en dos planos»): `same_stretch()` en todas las vías y otra vez al reservar.

**C. Por qué hay tantos huecos**: 32 de 221 planos sin clip propio. La búsqueda es por frase y el juez rechaza mucho;
en frases abstractas («la noche antes de la final», «sus padres son sus abuelos») no hay qué buscar.

**D. Fallos sueltos del juez**: un gimnasta hombre para una frase sobre Simone; Simone cuando la frase dice «Jordan
Chiles»; los Minions; un acto con un político para «en él cuenta su infancia».

## 5. Lo que ya está decidido y en curso

1. (hecho) No repetir tramos (B).
2. (en curso) Huecos con sentido (A): prestar solo clips que hablen de lo mismo (misma persona, mismo suceso, o
   metraje genérico del protagonista compitiendo), nunca uno atado a otra escena concreta; si nada encaja, palabras
   clave o una foto, no un clip sin sentido.
3. Revisor: leer del vídeo final cuando no puede leer el clip; foto del protagonista (estaba en `work/<vídeo>/people/`
   y se buscaba en la raíz); progreso en pantalla; luego, meterlo en la cola para que cambie lo que marque antes del
   render.
4. «Material de partida» por vídeo: pegar enlaces de vídeos de YouTube y de canales (también en el perfil del canal),
   y subir clips propios (p. ej. partidas grabadas de GTA); la búsqueda saca de ahí primero. Pensado sobre todo para
   GTA, donde la búsqueda a ciegas frase a frase no encuentra casi nada.

## 6. Reglas que no se pueden saltar

- No subir el ritmo de peticiones a YouTube (bloqueos «no eres un bot», 429). Proxy residencial pagado por GB: todo
  un vídeo por la misma sesión.
- Clips de terceros ≤ 5 s cada uno (Content ID).
- Lo que gaste dinero, toque las peticiones a YouTube o cambie la calidad de imagen: apagado por defecto, documentado,
  con un comando para medirlo. Lo local y seguro: encendido.
- Un commit por mejora, con test; `npm run typecheck` y `python -m pytest tests -q` en verde. Producción baja `main`
  cada 2 min; se trabaja en una rama y el dueño fusiona.

## 7. Qué preguntamos

1. ¿Ves otras causas de planos «sin sentido» o repetidos además de A-D? ¿Algo en `planner` (cómo parte y describe
   los planos), en `analysis` (CLIP) o en el juez que explique fallos de puntería?
2. Para los huecos (A y C): ¿qué estrategia propones? Opciones pensadas: elegir el clip prestado por parecido de texto
   o de CLIP con la frase; agrupar frases abstractas en planos más largos de un mismo clip del suceso; buscar por
   «escena» (varios planos seguidos) en vez de por frase; usar más fotos/tarjetas.
3. ¿El juez debería ver más contexto (la frase anterior y siguiente ya la ve; el vídeo entero no)? ¿Un segundo modelo
   distinto que confirme los casos dudosos?
4. Para GTA y temas sin «personas reales»: ¿cómo debería funcionar la búsqueda con material de partida?
5. Prioridades: si tuvieras que elegir tres cambios con más impacto en la puntería, ¿cuáles?

Archivos para mirar: `pipeline/planner.py`, `pipeline/sourcing/__init__.py`, `pipeline/sourcing/youtube.py`
(`candidates`, `relevance_bonus`), `pipeline/analysis/__init__.py`, `pipeline/judge.py` (`JUDGE_INSTRUCTIONS`,
`shot_brief`, `prefer_variety`, `continuation`), `pipeline/fallback.py` (`resolve`), `pipeline/timeline.py`
(`fill_empty_shots`, `chalkboards`), `pipeline/revisor.py`. Progreso del trabajo: `prompts/pipeline-progress.md`.
