# Revisión de lo fusionado en `main` hasta `aaf13ea` (22-11-2026)

Para la sesión que lleva el motor. He leído los cambios de `a94afc2..aaf13ea` (timeline, fallback, feedback, qa,
youtube, schemas, config) y he ejecutado `limit_text` con un caso propio. La CI de `main` está en verde.

## Un fallo comprobado

**El gancho se rellena con el mismo clip seis veces seguidas.** En `pipeline/timeline.py`, `limit_text`, la rama del
gancho elige `max(fitting, key=(nota, -usos, -distancia))`: la nota va primero, así que el clip mejor puntuado gana
hasta agotar `max_uses` (6). Con nueve planos vacíos en los primeros 30 s y seis clips donantes con notas distintas:

    ['s015', 's015', 's015', 's015', 's015', 's015', 's014', 's014', 's014']

Es el caso real de «newideas» (36 s sin imagen al principio) y devuelve el fallo original de `newgym3` (el mismo
tramo en siete planos del arranque). `tests/test_text_limit.py` solo mira el primer plano del gancho.

Arreglo: en el gancho, cada donante una vez (usos por delante de la nota, o un conjunto de ya usados), y que el
test compruebe que dos planos seguidos del gancho no llevan el mismo clip.

## Tres cosas que revisar

1. **De quién es el clip que se presta.** `limit_text` toma como donante cualquier plano con vídeo: en el gancho,
   el de mejor nota de todo el vídeo; fuera, el más cercano «a cualquier distancia». Nada mira que sea de la persona
   de la que habla la frase ni que no sea un suceso con nombre de otro capítulo, que es lo que puso la boda en el
   minuto 1 de `newgym3`. Los donantes deberían salir de ideas de ambiente de la misma persona, o de la misma idea o
   capítulo; un clip de una idea literal de otra cosa no se presta.
2. **Con el tope del 10 %, lo que antes era pizarra ahora es préstamo con zoom.** Es el orden pedido (clip de
   ambiente antes que texto), pero el revisor los contará como «hueco tapado». Hay que ver en un vídeo real cuántos
   salen; si son muchos, el paso que falta es la foto en tarjeta antes del préstamo también para las ideas de
   ambiente (hoy la foto solo va primero en las literales, `fallback.literal_ambient`).
3. **El bloqueo de QA por pantalla vacía puede dejar vídeos en ERROR de noche.** Vale para todos los vídeos, también
   los planificados sin ideas, donde antes una pantalla vacía se renderizaba. Mejor que el montaje la resuelva (clip
   o pizarra) y que QA bloquee solo si aun así queda; y que el aviso diga cómo desbloquear.

## Lo que no está hecho

De `prompts/objetivo-videos-referencia.md` no hay nada en `main`: ni las recetas por canal (`montaje.receta`), ni
la tarjeta solo para fotos (clips siempre a pantalla completa), ni la herramienta que mide cualquier mp4 con las
cifras de las referencias. Tampoco de la segunda pasada de `ideas-pantallas-de-texto.md`: el subtítulo repetido
bajo una pizarra o un rótulo, el texto ajeno quemado en los clips en tarjeta, y la época en las fotos.

## Lo que está bien

- `selectable()` en `youtube.py`: quitar la elección de formato que yt-dlp guardaba en los detalles explica por
  qué casi nunca se bajaba por HLS, por qué «el entero supera el tope» y por qué fallaban los rangos. Es el arreglo
  más importante de toda la serie. Falta medirlo en el servidor con `--youtube-stats`.
- El revisor ya no convierte planos en texto, las pizarras salen de la idea y no del trozo de frase, ninguna dura
  más de 3 s ni hay dos seguidas.
- El tope de clip por canal, con los vídeos a medias intactos.
