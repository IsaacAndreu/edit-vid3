# Objetivo: que nuestros vídeos salgan como los de referencia

Para la sesión que lleva el motor. El dueño lo ha dicho claro (23-11-2026): los cinco vídeos de referencia que ha
pasado son «mil veces mejores» que los nuestros y **quiere que los suyos sean así**. Hasta ahora hemos corregido
fallos uno a uno; desde aquí el trabajo se mide contra esos vídeos. Este documento fija el objetivo en números y
ordena lo que ya está escrito en `motor-punteria-2-prompt.md`, `ideas-pantallas-de-texto.md` y
`descargas-rango-fallo.md` (misma rama, `claude/quirky-johnson-6m1428`).

Replicar quiere decir **las mismas decisiones de montaje**: qué tipo de imagen va con cada tipo de frase, cuánto
dura, qué lleva encima. No el metraje, la marca ni los textos de nadie.

## Las tres recetas

Medidas mías sobre los archivos, por fotogramas cada 2-6 s y recuento de cortes; sin audio. Son aproximadas.

### A. Persona o deporte — referencia: Gymnast Icons, Rebeca Andrade (`_n5-FQWizJ8`, 12 min 13 s)

| | Referencia |
|---|---|
| Corte | uno cada 3,1 s (233) |
| Primera imagen | segundo 0: la protagonista hablando |
| Metraje a pantalla completa | unas tres cuartas partes |
| Fotos en tarjeta sobre el fondo | una cuarta parte (26 de 108 fotogramas) |
| Pantallas de solo texto | ninguna (2 fundidos a negro en 12 min) |
| Rótulo corto de dato o nombre | uno cada 20-30 s, sobre la imagen de eso |
| Sin imagen posible | foto de la persona y época, o stock de concepto sin caras, 2-3 s |
| Otra persona en pantalla | solo cuando la frase va de ella, con su nombre |
| Entrevistas de la protagonista | vuelven como hilo; abren el vídeo |

### B. Un suceso contado a fondo — referencia: Messi en el Villamarín (84 s)

| | Referencia |
|---|---|
| Corte | uno cada 4 s; reacciones y testimonios de 5-6 s |
| Fuentes | unas diez, todas del suceso, cada una con una función: acción, otro ángulo, reacción, comentario, consecuencia, testimonio |
| Sonido original | arranca con él y vuelve varias veces, subtitulado |
| Texto | una palabra grande cada 12-15 s **sobre el metraje**, nunca sobre fondo vacío |
| Fuente del clip | arriba a la derecha, siempre |

### C. Teoría, explicativo o juego — referencias: Niko Bellic en GTA 6 (8 min 55 s) y COLETHEMAN, 10 errores (`xNcl7EpmYwQ`, 9 min 34 s)

| | Referencia |
|---|---|
| Corte | uno cada 3,5-4,5 s |
| Tarjetas propias sobre el fondo de marca | 35-40 % en el de teoría; pocas en el de lista |
| Tipos de tarjeta | ficha de personaje, fila de prueba ✓/✗, afirmación con sello, comparación, lista, cifra, capítulo |
| Texto sobre el metraje | casi en cada plano en el de lista: frase clave con la fuente del dato |
| Metraje | es la prueba de lo que se afirma, con un círculo sobre el detalle |
| Diálogo original del juego | pasajes largos subtitulados |

Lo que las tres comparten: **nunca hay una pantalla que solo repita lo que dice la voz**, la primera imagen llega
en el primer segundo, y cuando hay texto a pantalla completa es una tarjeta con información propia y diseño.

## Dónde estamos: «newideas» (Simone Biles, 11 min 2 s, 23-11)

| | Nuestro | Receta A |
|---|---|---|
| Corte | uno cada 4,1 s (163) | 3,1 s |
| Primera imagen | segundo 40 | segundo 0 |
| Texto o pantalla vacía | la mitad (74 de 144 fotogramas) | ninguna |
| Fotos en tarjeta | pocas | una cuarta parte |
| Clips en tarjeta pequeña | frecuentes | nunca (la tarjeta es para fotos) |
| Texto ajeno quemado en el clip | varios | alguno |

## Qué hacer, en este orden

1. **Una receta por canal.** `montaje.receta: persona | suceso | teoria` en el perfil del canal, que fija los
   objetivos de arriba como límites y preferencias del planner, del relleno y del montaje. Los canales de gimnasia,
   atletismo y patinaje, A; los de crímenes y sucesos, A con pasajes de B; GTA y explicativos, C.
2. **Receta A primero**, porque es la que más vídeos hace y casi todo existe:
   - lo de `ideas-pantallas-de-texto.md` entero (tope de texto, nada vacío, gancho con imagen);
   - **foto en tarjeta como segunda opción**, por delante de cualquier préstamo, con la época que el planner ya
     escribe; objetivo, una cuarta parte del vídeo cuando falte metraje;
   - la tarjeta, solo para fotos y material vertical; los clips, a pantalla completa;
   - el gancho abre con el mejor plano juzgado de la protagonista, a ser posible hablando.
3. **Las descargas**: `descargas-rango-fallo.md`. Con la mitad de los tramos fallando no hay receta que se cumpla.
4. **Receta C** para GTA: tarjetas de argumento y metraje como prueba (`motor-punteria-2-prompt.md`, puntos 4 y 5),
   con el material de partida, y el tope de clip por canal.
5. **Receta B**: cobertura por funciones y sonido original (`motor-punteria-2-prompt.md`, puntos 1 a 3).
6. **El guion de cada receta.** Las estructuras por canal ya existen (`guion.estructura`); comprueba que la de
   «atleta» pide lo que hace la referencia: abrir por lo último que pasó, sucesos con fecha, sede y resultado,
   citas literales, y lo que no tiene imagen en frases cortas.

## Cómo se sabe que hemos llegado

Una herramienta que mida **cualquier mp4** con las mismas cifras de las tablas: ritmo de corte, segundos hasta la
primera imagen, parte en texto o vacía, parte en tarjeta, rótulos por minuto. Ya existe
`--informe-piloto VIDEO --referencia VIDEO`: mira qué mide y amplíalo; para un vídeo nuestro, el montaje sabe la
respuesta exacta, y para uno ajeno basta con clasificar fotogramas (fondo de marca o no, con texto grande o no).
El dueño guardará las referencias en una carpeta y la página «Puntería» enseñará, por canal, nuestro último vídeo
al lado de su referencia. Un cambio es una mejora cuando acerca esas cifras, además de bajar los marcados del
revisor.

Y antes de dar una receta por buena: un vídeo de prueba que el dueño ve entero. Nada se enciende en todo el
servidor sin eso.
