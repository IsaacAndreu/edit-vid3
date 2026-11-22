# Prompt: qué canales empezar, cuáles doblar, y montar un canal a partir de 5-6 vídeos de referencia

Para la sesión que lleva el motor. Pega todo lo que hay debajo de la línea.

---

El dueño quiere que el programa le diga **qué canales nuevos le conviene empezar** y **qué canales le conviene
doblar a qué idiomas** (hay búsquedas y poca competencia), y que a partir de **5 o 6 vídeos de referencia de un
nicho** el programa saque qué es lo que funciona ahí y deje un canal nuevo listo para producir con esa fórmula.

Buena parte ya existe. No la rehagas: léela, úsala y complétala.

## Lo que ya hay (léelo antes de escribir nada)

- `pipeline/radar.py`: outliers de la competencia por canal, nichos nuevos medidos (`measure`, `niche_score`),
  canales revelación.
- `pipeline/huecos.py`: «Huecos»: demanda y competencia de un tema **en español**, canales pequeños que ganan, y el
  hueco frente al **inglés**; sugerencias del autocompletado; historial por tema. Unas 400 unidades de API por tema.
- `pipeline/niche_ideas.py`: ideas para un nicho y `make_profile`, que convierte un nicho en `canales/<nombre>.yaml`.
- `pipeline/autopilot.py`, `pipeline/organizar.py` (borradores de guion), `guion.estructura` por canal,
  `formatos/*.yaml`, `pipeline/mychannel.py`, `pipeline/experimentos.py`, `pipeline/lab.py`, `pipeline/ytapi.py`.
- Doblajes: `pipeline/dub.py`, `pipeline/doblaje.py`, y canales ya doblados (`atlas-de/fr/it/pt`, `gimnasia-br`).
- Del trabajo de puntería: material de partida por canal (`materiales/<canal>/material.json`), el índice por
  escenas (`pipeline/indice.py`) y, si ya está hecho, las recetas de montaje y la herramienta que mide cualquier
  mp4 (`prompts/objetivo-videos-referencia.md`). Si eso último no está, la parte 3 de este plan depende de ello:
  dilo y hazlo primero.

## Lo que falta

### 1. Huecos en cualquier idioma, no solo español frente a inglés

`huecos.measure` tiene el español y el inglés escritos a mano. Generalízalo a una lista de idiomas
(`radar.idiomas`, por defecto es, en, pt, de, fr, it) con la búsqueda traducida por el modelo y comprobada (que
los resultados estén de verdad en ese idioma: el parámetro `relevanceLanguage` de la API es una preferencia, no un
filtro; mira el idioma del título y del audio que devuelve `videos.list`).

Por cada tema e idioma: demanda, competencia reciente, peso de los canales grandes, canales pequeños que ganan,
sugerencias. El resultado es una tabla tema × idioma, y de ella salen dos lecturas:

- **dónde hay público y nadie lo atiende** (para empezar un canal en ese idioma);
- **qué idioma tiene el hueco más grande frente al idioma donde el tema ya funciona** (para doblar).

La cuota manda: cinco idiomas son cinco veces las búsquedas. Mide primero el idioma de origen y el español; los
demás solo para los temas que pasen un mínimo, y nunca más de `radar.gaps_units_per_day`. Di en la página cuántos
temas caben al día con la cuota que hay.

### 2. Qué doblar de lo que ya tiene

Para cada canal propio (`canales/*.yaml` con vídeos hechos) y cada idioma al que aún no está doblado: el hueco de
su nicho en ese idioma (parte 1), con las búsquedas del propio canal (`lab.queries`) traducidas. Añade lo que ya
se sabe de casa: cómo van sus vídeos (`mychannel`, `agenda`), cuántos hay hechos que se podrían doblar ya, y si el
material del canal depende del idioma (un canal de mapas se dobla entero; uno hecho con declaraciones en español,
peor). Resultado: una lista ordenada «dobla *este canal* a *este idioma*», con el número de vídeos listos para
doblar y lo que costaría (voz y render, que el programa ya sabe calcular).

Si las recomendaciones de los canales ya doblados existen como dato (`atlas-pt` frente a `atlas-es`), úsalas para
comprobar la nota: un idioma que el programa recomienda y donde el canal doblado va mal es una nota mal hecha.

### 3. De 5-6 vídeos de referencia a un canal listo

Entrada: de cinco a ocho enlaces de YouTube de un mismo nicho o formato, pegados en el estudio. Salida: un
**informe de fórmula** y, con un botón, el canal creado.

Qué se saca de las referencias, y de dónde:

| Qué | De dónde | Coste |
|---|---|---|
| Cómo les va: visitas frente a lo normal de su canal, tamaño y edad del canal | API (`videos`, `channels`, `baseline`) | pocas unidades |
| Títulos y miniaturas: patrones comunes | API + las miniaturas (directas) | un modelo de visión barato |
| El guion: estructura, duración, palabras por minuto, cómo abre, cada cuánto promete algo, cómo cierra, qué tipo de frases usa (hechos con fecha, citas, afirmación y prueba) | subtítulos de la fuente (ya se leen) | una llamada al modelo por vídeo |
| El montaje: ritmo de corte, segundos hasta la primera imagen, parte en metraje, foto, tarjeta y texto, rótulos por minuto, si usa sonido original | la herramienta que mide cualquier mp4; necesita el vídeo a 360p | **descarga por el proxy: avisar de los MB y pedir confirmación** |
| De dónde sacan el material: canales que acreditan, fuentes visibles | descripción, texto en pantalla (OCR que ya hay) | — |

Lo que comparten cinco de seis referencias es la fórmula; lo que solo hace una, no. El informe lo dice así, con
el dato de cada vídeo al lado, y separa lo medido de lo interpretado por el modelo.

Con «Crear canal», a partir del informe:

- `canales/<nombre>.yaml` (reutiliza `make_profile`): búsquedas del nicho, los canales de referencia como
  competidores para el radar, idioma, y la **receta de montaje** más parecida con sus números ajustados a lo medido;
- la estructura de guion del canal (`guion.estructura` con texto propio) y, si hace falta, un `formatos/<nombre>.yaml`;
- los canales de donde las referencias sacan material, como material de partida del canal;
- cinco primeras ideas de vídeo que **no** sean las de las referencias.

Y lo que cierra el círculo: un **vídeo piloto** hecho con esa fórmula, medido con la misma herramienta y puesto al
lado de las referencias en una tabla. Hasta que el dueño ve ese piloto y esa tabla, el canal no entra en el
piloto automático.

Replicar es replicar la fórmula: estructura, ritmo, tipo de imagen para cada tipo de frase. Nunca el guion, los
títulos ni la selección de clips de un vídeo concreto; el autopiloto ya trabaja así («nunca una copia»).

### 4. Una página de recomendaciones

Hoy las señales están repartidas (Competencia, Huecos, Mi canal, Experimentos). Una página «Qué hacer ahora» con
tres listas cortas, cada entrada con su prueba y un botón:

- **Empezar**: nichos con hueco, en qué idioma, con qué fórmula (si hay referencias medidas) y por qué.
- **Doblar**: canal propio → idioma (parte 2).
- **Dejar o cambiar**: canales propios cuyo nicho se ha llenado o que llevan N vídeos por debajo de su mediana.

Cada recomendación enseña sus números y lo que **no** sabe. La nota no es una caja negra: demanda, competencia,
entrada de canales pequeños y hueco entre idiomas ya están; añade

- **si el programa lo puede hacer bien** (`fit` ya existe en Huecos: que dependa también de si hay material: un
  nicho sin metraje descargable ni fotos no es para esta herramienta);
- **cuánto se gana por visita**, que cambia mucho con el idioma y el tema. No hay dato público: una tabla
  editable por idioma y categoría (`radar.rpm`), vacía por defecto, que el dueño rellena con lo que ve en sus
  canales; sin ella, la nota no inventa ingresos;
- **el esfuerzo**: vídeos por semana que haría falta y coste por vídeo, que el programa ya mide.

### 5. Que las recomendaciones aprendan

Guarda cada recomendación con su fecha y su nota. Cuando un canal empezado o doblado tenga 30 días y diez vídeos,
compara cómo le fue con lo que se predijo, y enséñalo en la página. Sin esto no se sabrá nunca si la nota sirve.

## Reglas

- Cuota de la API: todo lo nuevo pasa por el libro de cuota de `ytapi.py`, con tope diario propio, y deja siempre
  sitio a la búsqueda de los vídeos en cola. Si no cabe, espera al día siguiente y lo dice.
- Nada nuevo descarga por el proxy sin que el dueño lo vea y lo confirme (la parte de montaje de las referencias).
- Lo que diga el modelo sobre un nicho se comprueba con una medida antes de enseñarlo como recomendación; una idea
  sin medir sale como idea, no como recomendación.
- No hay volumen de búsquedas público en YouTube. Las sugerencias del autocompletado y las visitas de vídeos
  recientes son indicios; llámalos así en la página, no «búsquedas».
- Un commit por parte, con su test (API y modelo simulados); `npm run typecheck` y la suite en verde; tu rama.
- Actualiza `prompts/pipeline-progress.md` y di qué no has podido comprobar sin el servidor.

## Orden

1 (idiomas) → 2 (qué doblar) → 4 (la página, con lo que haya) → 3 (referencias a canal) → 5 (aprender).
La 2 es la que antes da dinero: usa vídeos que ya están hechos.
