# Prompt: radar semanal de nichos virales en inglés y huecos por idioma

Para la sesión que lleva el motor. Pega todo lo que hay debajo de la línea.

---

El dueño quiere que **cada semana**, solo, el programa: encuentre los nichos que se están haciendo virales en
inglés, mida en qué otros idiomas (español, portugués, alemán, francés, italiano, checo, indonesio y los que se
añadan) ese mismo contenido tiene público y poca competencia, y le entregue una lista **ordenada por mejor
oportunidad**, con sus números.

Las piezas de medida ya existen y no hay que rehacerlas: `pipeline/huecos.py`, `pipeline/idiomas.py` (tabla tema ×
idioma, con tope de cuota), `pipeline/radar.py` (outliers, canales revelación), `pipeline/recomendar.py` («Qué hacer
ahora»), `pipeline/formula.py` (de referencias a canal), `pipeline/doblar.py`, `pipeline/aprender.py`. Lo que falta
es **el embudo semanal** que las encadena: de dónde salen los temas, en qué orden se gasta la cuota y cómo se
ordena el resultado. Hoy los temas los propone un modelo y el descubrimiento mira sobre todo el español
(`radar.discover` busca con `language="es"`).

## Una prueba real, y lo que enseña

Antes de escribir esto hice una pasada a mano con una base de datos de canales (NexLev) y búsquedas de YouTube.
Es una muestra pequeña: un filtro en inglés y un nicho en cuatro idiomas. Sirve para afinar el método, no como
resultado.

**En inglés.** Canales sin cara, con su primer vídeo desde marzo de 2026, más de 50.000 visitas de media por vídeo,
vídeos de más de 7 minutos y menos de 300.000 suscriptores: **1.880 canales**. De los 40 primeros:

- Muchos son **un solo vídeo que explotó** (un canal con 1 vídeo y 7,9 millones de visitas). La media engaña: hay
  que exigir varios vídeos y mirar la **mediana**.
- Los sólidos se agrupan solos en nichos. El más claro, tres canales nacidos entre octubre de 2025 y abril de 2026
  con el mismo tema y los mismos títulos: *Fossil* (16 vídeos), *BlackWater* (10, mediana 762.000) y *Depth Theory*
  (11, mediana 743.000, 2,5 vídeos por semana). Tema: océano profundo y fauna prehistórica. Fórmula de título:
  «Why You'd Never Want To Meet a…», «Would X Survive Every Prehistoric Ocean?», «How Long You'd Last in Every…».
  **Tres canales nuevos con la misma fórmula y medianas altas es la señal más fuerte que hay.**
- Otros grupos que se ven: historia antigua explicada («What Did Ancient Humans Actually Do All Day?»), cámaras
  policiales con título de fórmula («…Has No Idea Police…», 45 vídeos, el pago por visita más alto de la lista),
  documentales de pueblos remotos, ingeniería de barcos y aviones.

**El mismo nicho en otros idiomas** (vídeos del último año, ordenados por visitas):

| Idioma | Los más vistos | Quién está |
|---|---|---|
| Español | 2-2,9 millones | «Aventura Salvaje - Español» (ocho de los veinte primeros), «Abyss Primal Español», «Ciencia Salvaje» |
| Indonesio | 1,1-1,7 millones | canales locales, más la BBC y DW dobladas |
| Alemán | 100.000-900.000 | «Wild Nature Science DE», «Nature Empire Deutsch», ARTE, National Geographic |
| Checo | 11.000-70.000 | «Wild Nature Science CZ», «Nature Empire Čeština», «Abyss Primal Česky», «Extinct Primal Čeština» |

Cuatro cosas que cambian el diseño:

1. **Ya hay redes haciendo exactamente esto.** La misma marca con el idioma detrás (*Wild Nature Science DE / CZ*,
   *Nature Empire Deutsch / Čeština*, *Abyss Primal Español / Česky*). Hay que **detectarlas**: donde ya hay una
   red, el hueco es menor de lo que dice el recuento de vídeos; y a la vez son una fuente gratis de pistas, porque
   el idioma o el tema que una red abre nuevo es lo que le está funcionando.
2. **El tamaño del idioma manda.** En checo el vídeo más visto del nicho no pasa de 70.000 visitas, con cuatro
   redes ya dentro. Un hueco en un idioma pequeño puede ser real y no valer la pena. Hace falta el **techo de cada
   idioma** medido, no supuesto.
3. **El tema puede estar lleno y la fórmula no.** En los otros idiomas lo que hay son documentales de una a cuatro
   horas («para dormir»). La fórmula viral inglesa es otra: 15 minutos, pregunta hipotética, título de patrón. La
   unidad que se mide tiene que ser **tema + fórmula**, no solo el tema.
4. **El dinero no es proporcional a las visitas.** Indonesio tiene mucha audiencia y paga poco por visita; alemán,
   al revés. Sin el dato de ingresos por idioma, el orden de la lista solo puede ser de visitas, y hay que decirlo.

## El embudo semanal

De ancho y barato a estrecho y caro. La cuota de la API es el recurso escaso: una búsqueda cuesta 100 unidades;
leer los vídeos de un canal o las cifras de 50 vídeos, 1.

### Paso 0 · Techo de cada idioma (una vez al mes)

Una cesta fija de ocho a diez búsquedas de temas de siempre (documental de animales, historia, crimen real,
ciencia, ingeniería…), traducidas, y por idioma la mediana de visitas de los vídeos largos más vistos del año.
Eso es el techo: cuánto da de sí un buen vídeo en ese idioma. Todo lo demás se lee contra él. Lista de idiomas en
`radar.idiomas`, ampliable: es, pt, de, fr, it, cs, id, pl, nl, tr y los que el dueño añada. `idiomas.WORDS` (la
comprobación de idioma por palabras frecuentes) hay que ampliarla para cada uno nuevo.

### Paso 1 · Qué se está haciendo viral en inglés (cada semana, casi gratis)

No por búsquedas, que son caras, sino por **canales vigilados**:

- **Lista de vigilancia** (`out/_radar/vigilados.json`): canales en inglés pequeños o nuevos. Cada semana, sus
  últimas subidas (`playlistItems`, 1 unidad) y sus cifras (`videos`, 1 unidad por 50). Quinientos canales cuestan
  unas mil unidades a la semana, lo que diez búsquedas.
- **Cómo crece la lista**: los canales de los outliers que ya encuentra el radar; unas pocas búsquedas sembradas
  por semana (ordenadas por visitas, de los últimos 90 días); las listas de «más populares» por país
  (`videos.list` con `chart=mostPopular`, 1 unidad), en EE. UU. y Reino Unido y también en los países de los idiomas
  de destino; los canales que pegue el dueño; y un botón para **importar una lista** (CSV de canales de cualquier
  herramienta de nichos que él use).
- **Cuándo un canal cuenta**: creado hace menos de 18 meses, o con su primer vídeo en ese plazo; al menos cinco
  vídeos largos; **mediana** de visitas por encima de un mínimo; menos de 300.000 suscriptores. Un canal con un
  solo vídeo que explotó se apunta para vigilar, no como nicho.
- **Agrupar**: un modelo lee los títulos de los canales que cuentan y los agrupa en **nichos-fórmula**: el tema,
  el patrón de título, la duración típica, cada cuánto suben. Un nicho-fórmula es fuerte cuando lo sostienen **tres
  o más canales nuevos**, o uno solo con ocho o más vídeos y la mediana alta. El modelo agrupa y nombra; los
  números salen de la API.
- **Tendencia**: guarda cada semana; lo que importa es lo que **sube** respecto a la anterior (canales nuevos que
  entran al grupo, mediana que crece), no lo que lleva un año arriba.

### Paso 2 · Cuáles pasan a medirse por idioma

Los quince mejores nichos-fórmula de la semana (configurable), ordenados por fuerza y tendencia, más los que el
dueño marque. También el **encaje**: si la herramienta puede hacerlo (`fit` de Huecos) y con qué receta de montaje
y qué camino de «Nuevo vídeo». Un nicho que exige cara, cámara propia o animación a medida se enseña, pero no gasta
cuota de idiomas.

### Paso 3 · El hueco en cada idioma

Por cada nicho-fórmula e idioma, primero lo gratis y luego lo caro:

1. **Sugerencias del buscador** en ese idioma para el tema y para el patrón de título traducidos (sin cuota).
   Sin ninguna sugerencia, ese idioma se salta esta semana.
2. **La medida que ya hace `idiomas.measure_language`**: lo más visto del año y lo subido en los últimos 30 días.
3. **La fórmula, no solo el tema**: una búsqueda más con el patrón de título traducido. Si el tema tiene vídeos
   pero ninguno con esa fórmula, se apunta como «tema ocupado, fórmula libre».
4. **Redes de doblaje**: entre los canales que salen, los que comparten marca con otro idioma (mismo nombre con
   «DE», «Deutsch», «Español», «Česky», «Čeština», «Français», «Italiano», «Indonesia», «Português»…, o el mismo
   canal de origen en varios resultados). Se cuentan aparte y se guardan: son competencia directa y, además,
   canales que añadir a la lista de vigilancia.
5. **El original doblado**: si entre los primeros resultados en ese idioma salen los propios canales ingleses (con
   pista de audio doblada o subtítulos), la competencia es el original. Mira qué deja ver la API de eso
   (`defaultAudioLanguage`, `localizations`) y, si no basta, dilo en vez de suponerlo.

Reparto de la cuota: `radar.semanal_units` (propuesta, 20.000 a la semana), repartida en trozos por la noche, sin
bajar nunca de `radar.keep_for_queue` para los vídeos en cola, y **reanudable**: lo que no cabe hoy sigue mañana
desde donde quedó. La página dice cuántos nichos e idiomas caben con la cuota que hay.

### Paso 4 · La nota de oportunidad

Una nota por nicho-fórmula e idioma, con sus partes a la vista, nunca una cifra sola:

- **Tamaño**: visitas de lo más visto, en bruto y como parte del techo de ese idioma.
- **Apertura**: canales pequeños que ganan, peso de los canales grandes, vídeos nuevos al mes, redes ya dentro.
- **Tendencia en inglés**: si el nicho sube o ya está estable.
- **Fórmula libre**: sí o no.
- **Encaje y esfuerzo**: receta, material disponible, vídeos por semana que hacen falta, coste por vídeo.
- **Ingresos**: solo si `radar.rpm` tiene el dato de ese idioma; si no, la nota es de visitas y lo dice.

Y un veredicto en palabras: «abrir canal», «doblar *tal* canal propio» (si el dueño ya tiene uno de ese nicho),
«vigilar», «tarde: ya hay red» o «idioma pequeño».

### Paso 5 · Lo que recibe el dueño

- Una página «Radar semanal»: la tabla ordenada por oportunidad, con filtro por idioma, y al abrir una fila, los
  canales de referencia en inglés, lo que hay en ese idioma y qué redes están dentro.
- Un resumen por Telegram el día que termina la pasada: las cinco mejores y lo que ha cambiado desde la semana
  anterior («se está llenando», «nueva red en alemán»).
- Historial: cada semana guardada, para ver si un hueco se cierra.
- De una fila a la acción: el botón que ya existe en `formula.py`, con los vídeos más fuertes del nicho en inglés
  como referencias, crea el canal y su piloto. Y `aprender.py` apunta la recomendación para compararla a los 30 días.

## Cuándo corre

Una vez por semana (`radar.semanal_dia`, `radar.semanal_hora`), desde el vigilante, como `radar.run_if_due`. El
paso 1 entero la primera noche; el paso 3, repartido en las siguientes según la cuota. A mano:
`python main.py --radar-semanal` y un botón en el estudio. Si una semana no termina, la siguiente sigue; no empieza
de cero.

## Reglas

- **Nada de visitas inventadas ni de «volumen de búsquedas».** YouTube no lo publica; las sugerencias y las
  visitas de vídeos recientes son indicios y se llaman así.
- **La mediana, no la media**, y siempre el número de vídeos y de canales detrás de cada cifra.
- Lo que dice un modelo (agrupar, nombrar, traducir) se separa en la página de lo que se ha medido.
- Toda la cuota pasa por el libro de `ytapi.py`. Si no hay cuota, espera; no cambia a buscar por el proxy sin que
  el dueño lo haya activado (`api_overflow`).
- Un commit por paso, con su test (API y modelo simulados), y una prueba del embudo entero con datos de mentira;
  `npm run typecheck` y la suite en verde; tu rama.
- Actualiza `prompts/pipeline-progress.md` y di qué no has podido comprobar sin el servidor: sobre todo, cuántos
  nichos e idiomas caben de verdad con la cuota del dueño.

## Orden

Paso 1 (vigilancia y nichos-fórmula) → página con solo el inglés → paso 0 (techos) → paso 3 puntos 1-3 → paso 4 y
la página completa → redes y original doblado → Telegram, historial y aprendizaje.

Tras el paso 1, el dueño tiene que ver la lista de nichos en inglés de una semana real y decir si se parece a lo
que él ve en YouTube. Si esa lista no es buena, medir idiomas encima no sirve.

## Lo que este diseño no resuelve

- La base de datos con la que hice la prueba tiene clasificados los canales (sin cara, con voz sintética, pago
  estimado por visita, fecha de inicio). La API de YouTube no da nada de eso: el programa tendrá que deducir «sin
  cara» de los títulos y descripciones, o dejarlo al dueño. Por eso el botón de importar listas.
- Los resultados de búsqueda cambian con el país y con el momento; dos pasadas del mismo nicho no dan lo mismo.
  De ahí guardar el historial y no fiarse de una sola semana.
- No hay forma de saber de antemano cuánto paga cada idioma: sale de los canales propios, con el tiempo.
