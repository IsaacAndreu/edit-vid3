# Prompt: modo «material primero» (tops, noticias y documentales con testimonios)

Para la sesión que lleva el motor. Pega todo lo que hay debajo de la línea.

---

El dueño quiere un modo nuevo de hacer vídeos, al lado del actual: **primero se busca y se lee el material real del
tema, y después se escribe el guion con lo que se ha encontrado**. Hoy es al revés (se ilustra un guion ya
escrito), y de ahí vienen casi todos los problemas de puntería que hemos ido tapando. La referencia es una
herramienta de la competencia (Elftuber V2) y un vídeo suyo que el dueño considera muy bueno.

No toques el modo actual: sigue sirviendo para gimnasia, mapas, GTA y simulaciones. Esto es otro camino que
comparte casi todas las piezas.

## La referencia, medida

«Top 5 persecuciones policiales más largas», 6 min 6 s, en español. Visto por fotogramas cada 3 s y recuento de
cortes; **sin audio**, así que lo que digo del sonido sale de los subtítulos que lleva en pantalla.

| Tramo | Qué hay |
|---|---|
| 0:00-1:12 | **Gancho de 72 s**: los momentos más fuertes de todos los puestos, cortes cada 1,5-3 s, con el audio original subtitulado en español («¡Sal del auto ahora!», «Sentí que estaba en un circuito de F1») y una palabra grande de vez en cuando («DESTRUCTIVAS», «BLOQUEO») |
| 1:15 | Tarjeta de título del top |
| 1:24-5:40 | Cinco puestos, de 50 a 75 s cada uno |
| 5:42-6:06 | Cierre: repaso rápido de los cinco |

Cada puesto está hecho igual: tarjeta con el número grande y el nombre del caso sobre el metraje → metraje de
**ese** suceso de dos a cuatro fuentes (informativo local, cámara del coche patrulla, documental) → una o dos
personas hablando de él, con su voz y subtítulo: la presentadora que dio la noticia, una vecina con su rótulo, el
sargento que conducía → más metraje.

Los números que definen el formato:

- **Planos largos.** 61 cortes en 366 s; quitando el gancho, tramos de 30 a 46 s seguidos sin un corte duro,
  normalmente de la misma fuente. Es lo contrario de nuestros 3 s por plano.
- **Todo el material es del suceso que se cuenta.** Unas quince fuentes en total, tres o cuatro por puesto.
- **Voz ajena en torno a una cuarta parte del vídeo** (fotogramas con subtítulo de alguien hablando); el narrador
  conecta el resto.
- **Pocos gráficos**: la tarjeta de cada puesto, una ficha de persona, las palabras grandes del gancho. Ninguna
  pantalla de solo texto fuera de eso.
- **La fuente de cada clip**, arriba a la derecha, siempre.

Lo que no hay que copiar: subtítulos en inglés y rótulos de cadena quemados en los clips, y un orden del top que
no se sostiene (no se ve por qué un caso va delante de otro).

## Lo que enseña su vídeo de presentación (formulario y opciones)

El dueño pasó también el anuncio de la herramienta (2 min 51 s), que es una grabación de su pantalla. Sirve para
saber qué deja elegir y para resolver dos dudas de arriba.

El formulario de «Nuevo vídeo» de ese modo pide, en este orden:

1. **Tipo**: «Top (puestos)» o «Noticias y documental».
2. **De qué trata, con una frase**, y un botón para que la IA mejore la idea o «lo escribo yo».
3. **Tono**: automático, documental de alto impacto, sensacionalista, ácido, fatalista, serio, humorístico,
   entretenimiento con datos, finanzas.
4. **Vídeos**: «elegir automáticamente» o «los elijo yo», con una casilla de enlace por puesto.
5. **Puestos** y **duración en minutos** (10 y 10 en el ejemplo).
6. **Doblaje de los testimonios**: «estilo documental (una voz grave)» o «una voz por persona».
7. **Voz del narrador** y **música** por estado de ánimo.
8. Avanzado: idioma del vídeo (español, inglés, portugués, francés), estilo de gráficos, con o sin gráficos, con
   o sin subtítulos, y cuántas llamadas a suscribirse lleva el guion (de ninguna a cinco).

Al lanzar avisa de que tarda entre una y tres horas y de que se puede cerrar la página; una lista «Mis pedidos»
enseña en qué paso va cada uno («Escribiendo el guion»).

Lo que cambia respecto a lo escrito arriba:

- **Sí doblan los testimonios**, y lo dan a elegir entre una sola voz para todos o una por persona. Mantén el
  subtítulo con voz original como opción por defecto nuestra y añade las dos de doblaje; «una por persona» quiere
  decir una voz distinta del catálogo para cada uno (hombre o mujer según quien hable), no una imitación.
- **El gancho lo decide un paso propio** («un director con IA elige cada corte del gancho»). Hazlo así: una
  llamada aparte que recibe los momentos candidatos del expediente, con su fotograma y su frase, y devuelve el
  orden y la duración de cada corte; no lo dejes como un bloque más del guion.
- **El tono** entra en el guion por bloques como una instrucción más, igual que hoy el formato y la estructura del
  canal. Reutiliza las estructuras y formatos que ya hay antes de crear una lista nueva de tonos.
- **El formulario del estudio** puede seguir ese mismo orden; casi todos los campos existen ya en «Nuevo vídeo»
  (voz, música, idioma, subtítulos). Los nuevos son el tipo, el enlace por puesto, el número de puestos y el
  doblaje de testimonios.

## Cómo se entra: tres caminos en «Nuevo vídeo»

Decisión del dueño (22-11): el modo nuevo no sustituye a nada. «Nuevo vídeo» ya abre con dos tarjetas para elegir
camino (commit `e1865b8`); pasa a tener **tres**, y las dos de ahora se quedan como están:

1. **Ya tengo el guion** (y opcionalmente la voz). El camino de siempre: el programa ilustra ese guion.
2. **Desde un título**. El programa escribe el guion a partir del título y la información que se le dé, y luego lo
   ilustra. Lo que ya existe.
3. **Material primero** (nuevo). El programa busca y lee los vídeos reales del tema, y con eso escribe el guion.
   Tops, noticias y documentales con testimonios.

La tercera tarjeta lleva una línea que diga para qué sirve y cuánto tarda y cuesta de más (más búsquedas y más
descarga por el proxy que los otros dos). Sus campos son los del formulario de arriba; todo lo que comparten los
tres caminos (canal, voz, música, idioma, subtítulos) es el mismo trozo de formulario, no una copia.

Un vídeo recuerda por qué camino se hizo (`modo` en su `config.yaml`), se ve en su ficha y en «Experimentos», para
poder comparar cómo les va a los de cada camino.

Desde el camino 2 tiene que poder saltarse al 3 sin volver a empezar: si al escribir desde un título el aviso de
«qué se puede enseñar» dice que medio guion no tiene imagen, un botón «hacerlo con material primero» lleva el
título y los enlaces ya pegados a la tercera tarjeta.

## Cómo funciona el modo

### 1. Investigación

A partir del título y de los enlaces que dé el dueño: búsqueda por la API de las fuentes de cada puesto o capítulo
(informativos, material original, documentales; se prefiere quien grabó el suceso a quien lo resume). De tres a
seis por puesto, con tope total.

De cada fuente, **sin bajar el vídeo todavía**: sus subtítulos con tiempos, y el índice por escenas que ya hace
`pipeline/indice.py` (miniaturas del storyboard y una línea de descripción por escena). Solo si una fuente
imprescindible no tiene subtítulos se baja su audio para transcribirlo, avisando del coste.

### 2. Expediente

Un archivo por vídeo (`work/<vídeo>/expediente.json`) con, por fuente, los tramos útiles: de qué segundo a qué
segundo, qué se ve, qué se dice literalmente, en qué idioma, y **quién habla y en calidad de qué** (testigo,
periodista, policía, familiar, experto, el protagonista).

Quién habla es la parte delicada: los subtítulos no lo dicen. Se saca del rótulo en pantalla (el OCR que ya hay),
de lo que dice el propio vídeo y de su título y descripción, y lleva una nota de seguridad. **Un nombre solo sale
en pantalla si está escrito o dicho en la fuente**; si no, sale el papel («una vecina», «el agente»). Atribuir una
frase a quien no la dijo es el peor fallo que puede tener este modo.

### 3. El guion sale del expediente

Una llamada al modelo de guion escribe el vídeo como una lista de bloques, no como un texto corrido:

- **narrador**: lo que dice la voz. Cada dato que afirme lleva la referencia al tramo del expediente del que sale;
  lo que no está en el expediente no se afirma. Esto encaja con la regla de siempre de no inventar.
- **declaración**: una persona hablando; fuente, segundos exactos, la frase y su traducción.
- **secuencia**: metraje con su sonido de ambiente bajo la voz; fuente y segundos.
- **tarjeta**: número y título del puesto, ficha de persona, fecha, mapa.

Y el gancho, que es un bloque propio: de seis a diez momentos, los más fuertes del expediente, en un minuto como
mucho.

Explícale al modelo para qué es cada bloque y qué hace bueno a este formato (se ve y se oye a quien estuvo allí;
el narrador solo une); no le des una plantilla rígida. El orden de un top tiene que poder justificarse con un
dato del expediente (duración, velocidad, daños): el criterio se dice en la narración.

El dueño ve el guion por bloques en el estudio antes de gastar en voz y descargas, y puede quitar o cambiar
declaraciones.

### 4. Voz, descargas y montaje

- La voz sintética solo lee los bloques de narrador.
- Se bajan los tramos exactos: las declaraciones con audio, las secuencias en la calidad final. El estudio enseña
  antes cuántos MB va a costar por el proxy.
- Cada declaración bajada se comprueba: se transcribe el clip y tiene que coincidir con la frase del expediente
  (`quotes.min_match` ya hace esto); si no coincide, no entra.
- El montaje no pasa por el corte en planos de 3 s: cada bloque es un plano o una secuencia larga. Lo que ya
  existe para citas con subtítulos, apertura con sonido original, fichas de persona, rótulos, crédito de fuente y
  el formato de ranking se reutiliza.
- **Doblaje de declaraciones**: por defecto, subtítulo traducido y voz original. Como opción por canal, voz en
  español por encima con el original bajo, al estilo de un informativo; una voz neutra de hombre o de mujer, nunca
  una imitación de la voz de la persona, y con el rótulo de que está doblado.

### 5. El tope de clip en este modo

El formato vive de planos largos; con el tope general de 12 s no sale. El dueño ya decidió asumir el riesgo de
reclamaciones. Tope propio del modo, por canal (`content.max_third_party_seconds` del perfil; propuesta, 45 s), y
la pestaña «Fuentes» de cada vídeo sigue diciendo cuánto se ve seguido de cada una.

### 6. Comprobaciones

- Ninguna declaración sin su comprobación de transcripción; ningún nombre que no venga de la fuente.
- El revisor, adaptado: en un bloque de declaración mira que quien sale hablando sea quien dice el rótulo; en una
  secuencia, que sea del suceso de ese puesto.
- Texto ajeno quemado (subtítulos en otro idioma, franjas de «última hora»): recorte del encuadre cuando ocupa
  solo la franja de abajo; si no se puede, otra toma.
- La herramienta que mide cualquier mp4 (`prompts/objetivo-videos-referencia.md`) con las cifras de la tabla de
  arriba: duración del gancho, largo medio de plano fuera del gancho, parte con voz ajena, fuentes por puesto.

## Reglas

- Apagado por defecto; se elige por vídeo. Nada de esto cambia los vídeos del modo actual ni los que están a medias.
- Cuota de la API y GB del proxy: con tope por vídeo, enseñados antes de empezar, y por el libro de cuota que ya hay.
- Un commit por etapa con su test (API, modelo y descargas simulados) y la prueba de extremo a extremo de un top de
  tres puestos; `npm run typecheck` y la suite en verde; tu rama.
- Si las descargas siguen fallando cerca de la mitad de los tramos, dilo antes de empezar: este modo depende de
  bajar los segundos exactos, con audio, mucho más que el actual.

## Orden

1. Investigación y expediente, con una página en el estudio para verlo. Ya sirve por sí solo: el dueño ve qué
   material hay de un tema antes de decidir si hace el vídeo.
2. Guion por bloques desde el expediente, visible y editable.
3. Montaje de un **top de tres puestos sin gancho**, de principio a fin.
4. El gancho.
5. Noticia y documental (misma maquinaria, otra estructura de bloques).
6. Doblaje de declaraciones.

Tras el paso 3, un vídeo de prueba que el dueño ve entero, medido al lado de la referencia. No sigas al 4 sin eso.

## Lo que no he podido comprobar

No he oído ni la referencia ni el anuncio: cuánto habla el narrador y cómo suena la mezcla del doblaje lo tiene
que decir el dueño, o salir de la transcripción si el vídeo está en YouTube. Y no sé cómo decide esa herramienta qué fuentes usar: el diseño de arriba es el mío, no el suyo.
