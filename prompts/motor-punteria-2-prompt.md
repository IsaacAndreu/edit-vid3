# Prompt: decidir clips como un montador (segunda tanda de puntería)

Para la sesión que lleva el motor (rama `claude/jolly-clarke-zttbs8`). Pega todo lo que hay debajo de la línea.

---

Sigues con la puntería del motor. La primera tanda (`prompts/motor-punteria-prompt.md`) está hecha casi entera y la
cifra del revisor bajó de 29 a 18 planos marcados por cada 100 en `newgym3`. Esta segunda tanda sale de dos vídeos
más, hechos con herramientas automáticas de la competencia, que el dueño considera claramente mejores que los
nuestros «sobre todo por la toma de decisiones de clips». Los he visto por fotogramas (uno por segundo el corto, uno
cada 5 s el largo) y recuento de cortes; **no he podido oír el audio**, así que lo que digo del sonido sale de los
subtítulos quemados en la imagen.

## Qué hacen esos dos vídeos

**Messi en el Villamarín (84 s, otra herramienta, español).** Cuenta un solo suceso (el gol de Messi al Betis y la
ovación de la grada rival) con unas diez fuentes, todas de ese suceso, y cada una cumple una función distinta:

| Segundos | Qué se ve | Función |
|---|---|---|
| 0-2 | la grada coreando, subtítulo «¡Messi, Messi!» | arranque con sonido original |
| 3-4, 21-26 | un aficionado grabado de cerca, «¡Joder, macho!», «¡Madre mía, Messi!» | reacción |
| 5-10 | la jugada en la retransmisión | la acción |
| 12-15 | el mismo gol desde detrás de la portería | otro ángulo |
| 16-20 | el gol con la narración de Cadena SER, «¡Gol, gol, gol!» | comentario |
| 27-44 | la grada aplaudiendo, tres vídeos distintos | consecuencia |
| 45-53 | los abrazos de los compañeros | protagonistas |
| 56-61 | el entrenador rival en rueda de prensa, subtitulado | testimonio |
| 62-83 | el entrenador y Messi saliendo, Messi ante el micro | cierre |

Unos 21 cortes en 84 s: un plano cada 4 s de media, con reacciones y testimonios de 5-6 s y la grada 11 s seguidos
de una misma fuente. Cada 12-15 s, una palabra sola en grande («CALDERA», «PARÁBOLA», «INSÓLITA», «OVACIONAR»,
«CONMOVIDO») con una línea pequeña debajo. El cántico de la grada, rotulado en amarillo grande. La fuente de cada
clip, arriba a la derecha.

**Niko Bellic en GTA 6 (8 min 55 s, programa de la competencia, español).** 115 cortes, uno cada 4,5 s. Es un vídeo
de teoría: afirmación, prueba, veredicto. Entre un 35 y un 40 % del tiempo son **tarjetas propias sobre el fondo de
marca**, no metraje:

- ficha de personaje: retrato, juego de origen, nombre, una línea («DE GTA 5 · JIMMY DE SANTA · EL HIJO DE MICHAEL»);
- fila de prueba: «CRÉDITOS DE GTA 6 · Josephine Phoenix · VALENTINA ✓», y la misma con ✗ cuando no cuadra;
- afirmación numerada con sello: «MENTIRA 1 · «Trevor habla en la radio de GTA 6» · FALSO»;
- comparación de dos retratos con flecha, igualdad entre dos fichas, lista corta («DENTRO DE LA TAQUILLA: …»);
- cifra grande con pie («25 años: el primer GTA sin él», «86/91 misión»), marcador de capítulo, aviso de spoilers;
- rótulo de lugar con icono sobre el metraje («SE FUE A VICE CITY», «CÁRCEL DE BOLINGBROKE»);
- **un círculo dibujado sobre el detalle del metraje** que sirve de prueba (una línea de texto en pantalla, una
  opción de un menú).

El metraje que sí usa es **prueba**: la página de un libro, una matrícula, el menú de la radio, la escena exacta
donde se dice la frase. Y al final deja casi 50 s seguidos de una escena del juego con su diálogo subtitulado.
Fuente arriba a la derecha en cada clip.

## Lo que tienen en común y nosotros no

1. **Eligen el clip por la función que cumple en el relato, no por parecido con la frase.** Para un suceso buscan
   la acción, otro ángulo, la reacción, el comentario y el testimonio, y los ordenan. Nosotros buscamos «algo que
   se parezca a esta frase» y, cuando hay varios planos del mismo suceso, salen cinco tomas equivalentes.
2. **El sonido original es parte del guion.** La voz calla y habla la grada, el locutor, el entrenador o el
   personaje, subtitulados. Nosotros tenemos la apertura, dos citas por vídeo (`quotes.count`) y golpes de 1-2 s
   bajo la voz (`sound_bites`): existe la pieza, pero como adorno.
3. **Se quedan más tiempo en un plano cuando el plano lo merece.** Reacciones y testimonios de 5-6 s. Nuestros
   planos son de 1,5-4 s cortados por tiempo.
4. **Cuando lo que se dice es un argumento, ponen una tarjeta, no un clip.** Por eso no necesitan encontrar imagen
   para cada frase.
5. **Pasan del tope de 5 s** (11 s de grada, 50 s de escena). El dueño ha decidido hacer lo mismo: ver «El tope
   de 5 s».

## Estado de partida que debes tener en cuenta

- En `newgym3-ideas2`, 18 de los 23 planos marcados eran «Repetido». El problema que queda es **pocas fuentes
  distintas por suceso**, no clips sin sentido. El punto 1 de abajo es la respuesta a eso.
- `newgym3-ideas` acabó con 47 pantallas de texto y 92 planos sin imagen. Una cifra baja del revisor conseguida
  a base de pizarras no es una mejora. Hay que medir las dos cosas (ver «Cómo se mide»).

## Qué hacer

Mismas reglas que la primera tanda: lo que suba peticiones, gasto o cambie lo que sale en pantalla entra apagado
por canal, con su test y su forma de medirlo; nada rehace vídeos a medias; tu rama, no `main`.

### 1. Cobertura de un suceso por funciones

Para los **sucesos clave** de un vídeo (los que el guion cuenta con detalle; pocos, de tres a seis), el planner
pide el material por función: la acción, otro ángulo o repetición, la reacción (grada, banquillo, aficionado, rival),
el comentario original (narración de radio o televisión), el testimonio (rueda de prensa o entrevista sobre eso) y el
después. Explica al modelo para qué sirve cada función y deja que decida cuáles tienen sentido en cada suceso; no
todas existen siempre.

- Una búsqueda por función y suceso, no por plano, en el idioma donde ese material existe («reacción afición»,
  «narración radio», «rueda de prensa» junto al suceso). Son más búsquedas por suceso clave y menos por plano:
  mide el saldo de cuota y de extracciones.
- El juez elige, para cada función, el mejor candidato; y sabe qué función está juzgando («esto debe ser la
  reacción de la grada, no la jugada»).
- El montaje ordena las funciones dentro de la idea y **no pone dos tomas de la misma función seguidas** si hay
  otra. Esto ataca los repetidos mejor que cualquier filtro posterior.
- Lo que sobra de un suceso (más ángulos, más grada) alimenta las ideas de ambiente de ese pasaje, antes que
  ningún préstamo.

Opción `planner.cobertura`, apagada. Probar en un canal de deporte.

### 2. Pasajes con sonido original

Convertir lo que hoy es adorno en parte del relato, para los sucesos clave:

- El planner marca dónde el guion deja sitio a una voz ajena: la narración del gol, el cántico, la frase del
  entrenador. Si el guion no deja sitio, no se fuerza; el aviso de guion del estudio puede sugerirlo.
- Se localiza con lo que ya hay: subtítulos de la fuente, `quotes`, picos de volumen de `sound_bites`.
- En el montaje, la voz se aparta (no se pisa), el clip suena con su audio y lleva subtítulo; un cántico o un grito
  corto puede ir como texto grande con el estilo del canal.
- Límite por vídeo y duración máxima por pasaje en la configuración del canal (hoy `quotes.count: 2`,
  `quotes.max_seconds: 12`). Requiere bajar tramos con audio: va apagado y se mide en GB.

### 3. Duración del plano según su función

Que una reacción, un testimonio o una prueba puedan ocupar la idea entera (4-5 s) en lugar de partirse en dos o
tres cortes. El planner ya agrupa por ideas; falta que el montaje pueda decidir «un solo plano» cuando la función
lo pide, hasta el tope del canal (ver «El tope de 5 s»).

### 4. Tarjetas de argumento

Para canales de teoría, explicativos y de juegos. Hoy existen `cita`, los gráficos de GTA (`wanted`, `phone`,
`gps`), la línea de idea y los rótulos de dato. Faltan las que sostienen un razonamiento:

- ficha de personaje o de cosa (retrato, origen, nombre, una línea);
- fila de prueba con ✓ o ✗ (fuente de la prueba, dato, a qué corresponde);
- afirmación numerada con sello de veredicto;
- comparación de dos fichas (flecha, igual, distinto);
- lista corta que se va completando; cifra grande con pie;
- **círculo o subrayado sobre un detalle del metraje**: necesita saber dónde está el detalle. Empieza por el caso
  fácil, texto en pantalla localizado por el OCR que el análisis ya hace, y deja el resto para después.

El planner decide por idea si lo que se dice es una **afirmación con prueba** (tarjeta, o metraje de la prueba
con círculo) o un relato (metraje). Los datos de cada tarjeta salen del guion o de una fuente citada, nunca
inventados; los colores y la tipografía, del perfil del canal. Sigue el bucle visual de `CLAUDE.md` para cada
componente nuevo y enseña los fotogramas.

Ojo con el exceso: el vídeo de referencia tiene un 35-40 % de tarjetas y funciona porque el metraje restante es
prueba real. Un vídeo nuestro con muchas pizarras y poco metraje no es lo mismo. Tope por canal de la parte del
vídeo que puede ir en tarjeta o texto.

### 5. Metraje como prueba

En esos mismos canales, cuando la idea es una afirmación, la búsqueda no pide «algo de GTA» sino la prueba
concreta: la escena donde se dice, la pantalla donde se lee. El índice por escenas del material de partida
(`pipeline/indice.py`) es la herramienta; falta la transcripción por escena, que ya tienes pendiente, y es
justo lo que hace encontrable «la escena donde dice esto».

## El tope de 5 s: decisión tomada por el dueño (21-11)

El dueño quiere trabajar como la competencia y asume el riesgo de reclamaciones. El tope deja de ser fijo:

- `MAX_THIRD_PARTY_SECONDS` pasa a ser un valor de configuración por canal y por vídeo
  (`content.max_third_party_seconds`), que el esquema recibe en vez de leer una constante. Son 29 sitios, con las
  validaciones de `Timeline` y `Selection` entre ellos: hazlo en un commit propio, con la prueba de extremo a
  extremo, y de forma que **un vídeo a medias planificado con 5 s siga validando y no se rehaga**.
- Valores que propone este plan, para que el dueño los confirme o cambie en el estudio: 12 s por clip en general;
  60 s en canales de juegos (`leonida-echt` y los que usen metraje de partida); los pasajes con sonido original,
  lo que diga `quotes.max_seconds`. Los clips propios siguen sin tope.
- Todo lo que dependía del tope se revisa con el valor nuevo: la continuación del juez (`continue_action`), el
  salto de 1,5 s entre cortes contiguos de una fuente, `fill_empty_shots`, el bloqueo de QA, los doblajes
  (un clip estirado por una voz más larga), los Shorts.
- Con el tope alto, el punto 3 (duración según la función) y el corte de una idea en tomas contiguas de la misma
  fuente dejan de chocar con nada: una idea puede ser un solo clip seguido.
- Deja el tope **por canal** aunque hoy se suba en todos: si un canal empieza a recibir reclamaciones, el dueño
  podrá bajarlo solo ahí. Añade a la página de cada vídeo cuántos segundos seguidos tiene el clip más largo de
  cada fuente, para que una reclamación se pueda relacionar con lo que la causó.
- Actualiza `docs/VPS.md` (apartado 3h) y `README.md`, que hoy describen los 5 s como regla.

## Cómo se mide

El revisor por cada 100 planos, como hasta ahora, **más tres cifras que eviten engañarse**:

- parte del vídeo en pizarra o texto sin imagen;
- fuentes distintas por minuto, y fuentes distintas por suceso clave;
- funciones cubiertas por suceso clave (cuántas de las pedidas se encontraron).

Añádelas a `--base` y a la página «Puntería». Vídeo de prueba: el mismo guion de `newgym3` otra vez, y un guion
de fútbol o de GTA escrito alrededor de un suceso, que es donde la cobertura por funciones debe notarse.

## Al terminar cada punto

`prompts/pipeline-progress.md` con lo hecho, lo apagado y cómo probarlo; y di con claridad qué no has podido
comprobar. Si algo de aquí choca con lo que sabes del código o de producción, explícalo y propón otra cosa.
