# Fallo: con `planner.ideas` encendido, medio vídeo son pantallas de texto (23-11-2026)

Para la sesión que lleva el motor. El dueño encendió el 22-11 en todo el servidor `planner.ideas`, `judge.per_idea`,
`judge.model_literal`, `revisor.enabled`, `fallback.concept_stock`, `timeline.idea_facts_max: 2` e `idea_quotes`.
El primer vídeo hecho así («newideas», el guion de Simone Biles, 11 min 2 s) le parece horrible, y tiene razón.
Lo he visto por fotogramas cada 4 s (144 fotogramas hasta 9:36).

## Lo que se ve

- **Unos 74 de 144 fotogramas (la mitad del vídeo) son texto sobre el fondo oscuro o directamente nada.**
- **Los primeros 36 segundos no tienen ni una imagen**: seis pizarras seguidas, una con una cara de fondo, el
  rótulo de capítulo y una pantalla vacía. El primer metraje sale en 0:40. Es el gancho.
- **Pantallas vacías**: en 0:36, 1:36, 2:16, 3:24, 5:00, 5:56, 6:20 y 7:24 solo hay el subtítulo pequeño de abajo
  (varias dicen «SECRETO 2:», «SECRETO 8:»: ideas de tipo rótulo que no pintan ni rótulo ni clip).
- **Rachas enteras de texto**: 6:32-7:08 (nueve de diez fotogramas), 7:24-7:56 (nueve seguidos), 9:00-9:24 (siete).
- Las pizarras **repiten las mismas palabras que la voz y que el subtítulo** de abajo, y la misma pizarra aguanta
  8 s («PESAS MENOS SOBRE LOS APARATOS…», «INTENTABA NO MOVERSE…»). No añaden información: son la narración escrita
  dos veces.
- Lo que sí es metraje está bien elegido y casi sin repetidos. La puntería ha mejorado; lo que ha empeorado es
  cuánto vídeo queda sin imagen.

## Por qué pasa

Cada regla nueva, cuando no encuentra el clip perfecto, acaba en texto, y se suman:

- una idea literal sin su clip no admite relleno ni préstamo → pizarra;
- en el gancho no entra nada sin juez y el montaje no presta → pizarra;
- un plano que el revisor devuelve y no encuentra sustituto → texto (`revisor.no_borrow_sent_back`);
- el préstamo solo dentro de 40 s → pizarra si no hay nada cerca;
- y por debajo, las descargas siguen fallando cerca de la mitad de los tramos, así que hay muchos planos sin clip.

Parte de esto viene de mi plan (`motor-punteria-prompt.md`, bloques 1 y 2): pedí «nunca un clip de otra cosa» sin
poner un límite a cuánto texto puede salir. El límite estaba en la segunda tanda, que no llegó a aplicarse. Y la
cifra del revisor no lo delata, porque una pizarra no es un plano marcado.

## Qué hacer

El orden de preferencia tiene que ser, siempre: **el clip correcto > un clip de ambiente de quien se habla, juzgado >
una foto en tarjeta > texto**. Un clip de ambiente decente es mejor que una pizarra. El texto es el último recurso
y tiene tope.

1. **Tope duro de texto por vídeo** (`timeline.max_text_share`, propuesta 10 % del tiempo, por canal), **nada de
   pizarras en los primeros `judge.hook_seconds`**, y **nunca dos pizarras seguidas**. Cuando el tope se alcanza, el
   plano no va a texto: baja al siguiente escalón de la lista de arriba, incluido el préstamo del mismo pasaje.
2. **Idea literal sin su clip**: antes de la pizarra, foto del suceso o de la persona, y luego clip de ambiente de
   esa persona y época pasado por el juez. Lo que no puede entrar es un clip de *otra* cosa (otra persona, otro
   suceso con nombre), no «cualquier clip».
3. **El gancho**: mantén que todo pase por el juez, pero si no hay nada aceptado, usa el mejor clip juzgado del
   protagonista de todo el vídeo. Un gancho de texto es peor que cualquier otra opción.
4. **El revisor en la cola no convierte en texto.** Si lo devuelto no encuentra sustituto mejor, se queda el plano
   original, salvo roto, otra persona o marca de agua.
5. **Ninguna pantalla vacía.** Una idea de tipo rótulo pinta su rótulo de capítulo; si por lo que sea no hay nada
   que pintar, el plano se trata como de ambiente. Añade una comprobación en QA que bloquee el render si hay un
   tramo de más de 1 s sin clip, foto ni gráfico.
6. **Cuando haya pizarra, que diga algo que la voz no dice**: el dato, la cifra o la cita, no la frase repetida;
   y que no dure más de 3 s.
7. **Que la medida lo vea**: «parte del vídeo en texto o vacío» y «segundos hasta la primera imagen» en
   `revisor --base` y en la página «Puntería», al lado de los marcados por 100. Un vídeo con más del tope no
   cuenta como mejora por mucho que baje la otra cifra. Para medir sin modelo: el montaje ya sabe qué planos
   quedaron sin medio.
8. **Línea base honesta**: `newgym3`, `newgym3-ideas2`, `newgym3-ideas3` y este «newideas» con las dos cifras.

Hasta que 1-5 estén hechos, `planner.ideas` no debería estar encendido en producción. El dueño lo apaga hoy.

## Más cosas del mismo vídeo (segunda pasada, fotogramas sueltos a tamaño real)

Vistas en un fotograma cada una, a 360p: son indicios para comprobar en `timeline.json`, no mediciones.

1. **Pizarras hechas con trozos de frase.** En 3:52 la pizarra dice solo «Y»; en 4:08, «EN SPRING»; en 7:28, «UN
   SALTO»; en 9:12, «AVERGONZARSE.». La pizarra toma el texto del plano, que es media frase. Una pizarra tiene que
   salir de la idea entera (su línea de pantalla), nunca del trozo de un plano.
2. **La misma frase tres veces a la vez**: la dice la voz, la pone la pizarra y la repite el subtítulo de abajo
   (8:40: pizarra «SECRETO 11: TIENE TDAH Y NO LO ESCONDE», subtítulo «TIENE TDAH Y NO LO ESCONDE»). Cuando hay
   pizarra o rótulo de capítulo, el subtítulo de esas palabras sobra. Y los títulos de capítulo salen en el
   subtítulo en mayúsculas, como están en el guion.
3. **Encuadre que cambia sin criterio.** Clips en 16:9 salen unas veces a pantalla completa y otras en tarjeta
   pequeña sobre el fondo (1:04, 4:28, 4:48-4:56, 5:52), alternando plano a plano. Los vídeos de referencia usan la
   tarjeta solo para fotos. Si la tarjeta se está usando para tapar baja resolución, que sea una regla clara y
   estable dentro de una idea.
4. **Texto ajeno quemado en el clip**: 1:08 (subtítulos rosas en inglés de otro canal), 4:52 (rótulo de
   informativo «GOLDEN GIRL … NEWS»), 4:08 (letras gigantes «JORDA…»), 8:04 (anuncio de una tienda, «AVAILABLE AT
   MARDEL»). `analysis.max_text_area` debería haberlos quitado; mira si el filtro se salta en los clips en tarjeta
   o en los que vienen del relleno.
5. **Fotos que no son de eso**: 9:28, «Río 2016» sobre una foto de la delegación británica con su bandera; 3:08,
   «las clases con sus amigos» con un selfi de un hombre sin camiseta; 3:08-3:12 y 2:24, fotos de adulta para
   frases de su adolescencia (la época que el planner ya escribe por idea no se está exigiendo a las fotos).
6. **Bustos parlantes mudos**: 8:00, Simone hablando a cámara bajo la voz. O suena ella (cita), o no es el plano.
7. **Material muy ampliado**: 1:08 y 1:40 son clips de 2013 en baja resolución a pantalla completa; en 1:16 se ve
   una franja blanca a la izquierda (recorte mal ajustado).
8. **El final**: pantalla vacía en 10:32 y 20 s de pantalla final con los recuadros vacíos. Lo segundo es normal
   si luego se rellenan en YouTube; lo primero, no.

Lo que está bien y hay que conservar: las fichas de dato del principio (8, 7, 23), la ficha de persona de Jonathan
Owens, el selfi con Zac Efron justo cuando se cuenta, el podio de Nanning con su rótulo, los rótulos de año.
