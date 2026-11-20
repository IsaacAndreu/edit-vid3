# Prompt: que cada plano enseñe lo que se está contando

Para la sesión que lleva el motor (rama `claude/jolly-clarke-zttbs8`). Pega todo lo que hay debajo de la línea.

---

Vas a seguir el trabajo de puntería del motor de vídeos: que cada plano enseñe lo que dice la voz, sin clips sin
sentido ni repetidos. Este documento es la segunda opinión que pediste en `prompts/motor-informe-para-fable.md`,
convertida en plan de trabajo. El razonamiento largo y las pruebas están en `prompts/motor-informe-respuesta.md`
(rama `claude/quirky-johnson-6m1428`); léelo antes de empezar.

## Dónde estamos

Ya hecho por ti, no lo rehagas: no repetir los mismos segundos de una fuente (`same_stretch`), prestar solo dentro
del mismo pasaje (`borrow_window_seconds`), y el revisor leyendo del vídeo final con la foto del protagonista.
Esos dos últimos commits no están en `main`: en el servidor el revisor viejo marcó `tedbundy` (120 de 124) y
`guiadelmapa` (155 de 155) enteros como «Roto» con 0-4 planos vistos, porque los clips de `work/` ya se habían
limpiado. No son datos válidos; hay que repetirlos con el revisor nuevo.

## La idea central

Tus causas A, B y C salen de una sola: **la unidad de trabajo es un trozo de unos 3 s cortado por tiempo, no una
idea**. `newgym3` tiene 221 planos en 10 min 40 s y muchos son medias frases («en París. Pero detrás», «con
veintisiete años,»). Cada trozo se busca, se puntúa y se juzga solo; para la mitad no hay nada que buscar, quedan
huecos y los huecos se tapan. Prestar mejor reduce el daño, pero mientras se busque por trozo seguirá habiendo
decenas de huecos por vídeo.

Tres vídeos ajenos que quedan bien lo confirman. Los tres cortan al mismo ritmo que nosotros (uno cada 3,1-3,5 s),
así que el ritmo no es el problema. Ninguno busca un vídeo distinto para cada trozo, y cada uno tiene una salida
digna cuando no hay imagen exacta:

- **Gymnast Icons, Rebeca Andrade** (`_n5-FQWizJ8`, 12 min, 784.000 visitas; es el canal de `ideas.competitors`).
  233 cortes para unas 110 frases: dos o tres cortes por frase, del mismo momento. Un tercio de los planos son
  **fotos en tarjeta**. Cuando el guion nombra un sitio, un año, una edad o una nota, se ve y se rotula («Guarulhos»,
  «in 2015», «19 year old», «14.166 for Andrade»). Para detalles sin imagen («Rosa cleaned houses for a living»)
  usa **stock de concepto sin caras** de 2-3 s: unas manos con guantes limpiando. Una entrevista de la protagonista
  vuelve varias veces como hilo.
- **COLETHEMAN GTA, 10 errores en GTA 6** (`xNcl7EpmYwQ`, 9 min 34 s). Casi todos los planos llevan **una línea de
  texto diseñada**, con la palabra clave destacada y la fuente («Rockstar:», «IGN:», «Per previews:»). El texto lleva
  el significado; el metraje del juego solo acompaña. Gráficos propios que imitan la interfaz del juego, capítulos
  con título y barra de progreso, y las citas en tarjeta con foto y nombre.
- **Un vídeo de crimen hecho con otra herramienta automática** (3 min, sin enlace). Nunca enseña algo ajeno al
  caso: unas diez fuentes, todas del caso, de 4 a 12 s seguidos en cada una. A cambio se le cuelan rótulos de
  cadena, bustos parlantes y repeticiones; eso no hay que copiarlo.

**El guion también cuenta.** El de Gymnast Icons (2.134 palabras) está escrito sobre cosas que se grabaron: casi
cada párrafo se apoya en una competición con fecha y sede, una nota, un podio o una cita literal de alguien
(«She's queen»). Los tramos abstractos son cortos y se resuelven con una imagen concreta (la madre andando al
trabajo, los hermanos acompañándola a pie). El de GTA (2.393 palabras) repite diez veces la misma estructura:
error, qué dijo Rockstar o un medio, ejemplo, cómo evitarlo, con unas veinte afirmaciones atribuidas. Nuestro
`newgym3` es una lista de doce datos curiosos, varios sin imagen posible («dejó el instituto», «mide un metro
cuarenta y dos», «firmar contratos»).

## Reglas

Las del apartado 6 de tu informe siguen valiendo, con una precisión: planificar por ideas **baja** las peticiones
a YouTube y la cuota, así que no choca con ellas. Además:

- Nada de esto rehace los vídeos a medias. Lo que cambia cómo se planifica un vídeo entra con una opción por
  canal, apagada por defecto, y se enciende primero en un canal para medir.
- El tope de 5 s por clip de terceros no se toca. Una idea de 8 s se cubre con dos o tres clips distintos.
- Cada bloque se mide con el revisor antes y después (ver «Cómo se mide»). Si no mejora la cifra, no se enciende.
- Un commit por mejora con su test; `npm run typecheck` y `python -m pytest tests -q` en verde; tu rama, no `main`.

## Bloque 0 · Medir bien antes de tocar

1. **El revisor culpa al plano equivocado en los repetidos.** Marca el que sale más tarde, pero en un préstamo el
   original es el tardío: en `newgym3`, s203-s217 y s222-s229 son elecciones correctas del juez y figuran como
   «repite el plano s076…». Que marque el prestado, y que cuente parejas, no planos.
2. **Que distinga plano literal de plano de ambiente** en cuanto exista la etiqueta del bloque 1; hasta entonces,
   que «no tiene que ver» no se aplique a un plano del protagonista en una frase sin imagen posible (s071: Simone
   con una medalla para «dejó el instituto»).
3. **Línea base.** Deja escrito el comando para pasar el revisor nuevo a `newgym3`, `tedbundy`, `guiadelmapa` y
   `elcrimendepazos` y guardar el resumen en un solo archivo (`out/_revisor_base.md`): planos marcados por cada
   100, por motivo, separando huecos tapados, repetidos por parejas y «no tiene que ver» en planos literales.
4. **Comprueba el juez barato.** `python -m pipeline.rejuzgar newgym3 gpt-5-mini` sobre s065, s074, s097 y s127
   (los fallos sueltos de tu causa D). Si el modelo fuerte los rechaza, el bloque 3 punto 1 sube de prioridad.
   Lo lanza el usuario en el servidor; déjale el comando y qué mirar.

## Bloque 1 · Planificar por ideas

Es el cambio grande. Opción `planner.ideas` por canal, apagada.

1. **El planner agrupa los planos seguidos que cuentan lo mismo en una idea** (una o dos frases, 4-12 s) y le pone
   una etiqueta:
   - `literal`: hay que ver exactamente eso («una abeja en el podio», «Biles se sale del tapiz dos veces»).
   - `ambiente`: no tiene imagen propia; vale material de quien se habla, de esa época o suceso.
   - `rotulo`: título de capítulo leído por la voz («SECRETO 4: …») y despedida («suscríbete»). No se busca nada.
   Explica al modelo para qué sirve cada etiqueta y dale ejemplos de varios canales; no una lista de reglas.
2. **Una búsqueda, un análisis y una decisión del juez por idea**, no por plano. `scene_search` y los vídeos
   maestros del juez ya van en esa dirección: reutiliza lo que sirva.
3. **Los cortes dentro de una idea salen de la misma fuente y el mismo momento**: segundos distintos y seguidos
   del vídeo elegido, cada clip ≤ 5 s. Es `continue_action` convertido en regla. Pide el tramo con unos segundos
   de margen a cada lado; con HLS los segmentos vecinos casi siempre ya se han bajado.
4. **Por cada idea, además de las búsquedas, el planner escribe**:
   - quién debe salir y quién no puede salir;
   - la época o el suceso, para no poner París 2024 cuando se habla de 2013;
   - **la línea de pantalla** (bloque 2, punto 1);
   - los datos rotulables que nombra: lugar, año, edad, nota, cifra.
5. El montaje, el relleno, el QA y el revisor leen la etiqueta. Los esquemas (`Shot`, `BrollSpec`,
   `pipeline/schemas.py`) llevan los campos nuevos como opcionales para no invalidar los `shots.json` existentes.

## Bloque 2 · Una salida digna cuando no hay vídeo

1. **Línea de texto en pantalla por idea.** Frase corta con la palabra clave destacada y, si el dato tiene fuente,
   la fuente delante. Usa los componentes que ya existen (kinetic, LowerThird, DataCard) antes de crear otros. La
   frecuencia es por canal (`timeline.idea_lines`): en GTA y explicativos, casi siempre; en biografías, en las
   ideas de ambiente y en las que nombran un dato. Es lo que más separa al canal de GTA de los otros dos.
2. **Rótulo de dato** cada vez que la idea nombra un lugar, un año, una edad o una nota, sobre la imagen de eso.
3. **Orden del relleno para una idea de ambiente**: alargar el clip vecino (sus segundos siguientes) → foto en
   tarjeta de la persona correcta y de esa época → stock de concepto sin caras → clip prestado del mismo pasaje (lo
   que ya hiciste) → pizarra de palabras. Hoy la foto va casi al final y el clip prestado antes.
4. **Stock de concepto sin caras, pasado por el juez**, permitido en vídeos de persona solo para ideas de ambiente
   (opción `fallback.concept_stock`, apagada: cuesta una llamada al juez por plano). El planner escribe la búsqueda
   («hands cleaning with rubber gloves»), con objetos, manos y lugares, nunca personas reconocibles.
   `pexels_for_person: false` sigue mandando para todo lo demás.
5. **Orden para una idea literal**: juez estricto; si rechaza, siguiente opción juzgada; si no hay, foto del
   suceso o pizarra. Nunca un clip de otra cosa, ni prestado ni de relleno.
6. **Citas en tarjeta**: cuando el guion cita a alguien y no hay su declaración en vídeo, tarjeta de persona con
   la frase, no un busto parlante de otra cosa. Y mira si `quotes.count: 2` se queda corto: Gymnast Icons usa
   cinco o seis citas reales en doce minutos.
7. **El gancho**: en los primeros `judge.hook_seconds` no entra nada que no haya pasado por el juez.

## Bloque 3 · Juez y revisor

1. **Modelo fuerte donde importa**: gancho, ideas literales y candidatos juzgados solo con miniaturas
   (`model_hook` ya existe apagado; amplíalo a esos casos). El modelo barato, para ambiente. Con el resultado del
   bloque 0.4 delante.
2. **El juez recibe la etiqueta y la lista de quién debe y quién no puede salir.** No necesita más contexto ni ver
   el vídeo entero.
3. **Revisor en la cola, antes del render**, con el bloque 0 hecho. Lo que marque con seguridad alta en ideas
   literales, y todos los repetidos y huecos tapados, vuelven al relleno una vez; lo que siga marcado sale en el
   aviso al móvil con su hoja. Tope de coste por vídeo y opción para apagarlo.
4. Un segundo modelo que confirme todos los casos dudosos, no: el revisor ya es esa segunda mirada y ve el momento
   exacto que se va a usar.

## Bloque 4 · Material de partida con índice por canal

Tu punto 4 del apartado 5, con una vuelta: **primero un índice, luego la búsqueda**.

1. De cada vídeo o clip de partida se hace una vez un índice por escenas: cortes, huella CLIP, lo que se dice y
   una línea de descripción por escena escrita por un modelo de visión barato sobre una hoja de contactos. Las
   etiquetas que escriba el dueño al subir un clip («Vice Beach de noche») entran en el índice.
2. Cada idea consulta el índice por texto y por CLIP; el juez ve las tres mejores. Solo las ideas sin resultado
   van a YouTube.
3. El índice se guarda por canal: el segundo vídeo no parte de cero.
4. **Los clips propios no son de terceros**: sin tope de 5 s y sin crédito. Hoy el tope es una constante que usan
   29 sitios y las validaciones; distingue el origen en el esquema en vez de tocar la constante.
5. Para enlaces de YouTube, el índice se hace con miniaturas del storyboard y subtítulos, que no pasan por el
   proxy, y solo se bajan los tramos elegidos.
6. Para GTA, además, **un juego de gráficos del canal en Remotion** (estrellas de búsqueda, móvil, mapa con
   marcador, medidor de niveles, tarjeta de cita). Los colores salen del perfil del canal, no del componente.

## Bloque 5 · El guion

Lo último, porque depende de tener la etiqueta del bloque 1.

1. **Aviso antes de grabar la voz.** Al planificar, cuenta qué parte del guion son ideas de ambiente y cuáles no
   tienen ni foto posible, y enséñalo en el estudio junto a la verificación de datos, con las frases concretas. Es
   un aviso, no un bloqueo.
2. **Los borradores de guion reciben antes qué material existe**: los sucesos con vídeo encontrado, con fecha,
   sede y resultado, y las citas reales localizadas. Que el modelo escriba apoyándose en eso y deje lo que no tiene
   imagen en frases cortas. Explícale el porqué; no le des una plantilla rígida.

## Cómo se mide

Una cifra por vídeo: **planos marcados por el revisor por cada 100**, con el desglose del bloque 0.3. Línea base
con los cuatro vídeos de ese punto. Después de cada bloque, el usuario rehace el mismo guion de `newgym3` en una
carpeta nueva y se compara. `newgym3` hoy: 80 de 221, de los que 57 son repetidos (bastantes, la misma pareja
contada por el lado bueno) y 32 huecos tapados.

## Al terminar cada bloque

Actualiza `prompts/pipeline-progress.md` con lo hecho, lo apagado y el comando para probarlo, y di con claridad
qué no has podido comprobar desde tu entorno. Si un punto de este plan choca con algo que ya sabes del código o
de producción, no lo fuerces: explícalo y propón la alternativa.
