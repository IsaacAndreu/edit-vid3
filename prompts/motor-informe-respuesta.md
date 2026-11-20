# Segunda opinión sobre `motor-informe-para-fable.md` (20-11-2026)

Responde al informe de la rama `claude/jolly-clarke-zttbs8`. Base: ese informe, el informe del revisor sobre
`newgym3` (`out/newgym3/revisor/`, 80 de 221 planos marcados), una de sus catorce hojas, y el código de `main`
(`pipeline/timeline.py` → `fill_empty_shots`, `pipeline/planner.py` → `cut_shots`). No he visto el vídeo ni las
otras hojas: lo que sale de la tabla del revisor es lectura mía, no medición.

## Resumen

Las causas A-D son correctas, pero A-C son síntomas de una sola: **la unidad de trabajo es un trozo de 2,9 s cortado
por tiempo, no una idea**. `newgym3` tiene 221 planos en 10 min 40 s, y muchos son medias frases («en París. Pero
detrás», «de la campeona hay una persona que casi», «con veintisiete años,»). Cada trozo se busca, se puntúa y se
juzga por separado, así que para la mitad no hay nada que buscar, quedan huecos y los huecos se tapan. Arreglar
el tapado (A) es necesario, pero mientras se busque por trozo seguirá habiendo 30 huecos por vídeo que tapar.

## 1. Otras causas además de A-D

- **Corte por tiempo, no por sentido** (arriba). Es la causa de C.
- **No se distingue un plano «literal» de uno «de ambiente».** «Las abejas. Y hay pruebas en vídeo» exige ver eso
  y nada más; «con unos quince años dejó el instituto» no tiene imagen posible y vale cualquier Simone de esa
  época. Hoy los dos pasan por el mismo juez con la misma instrucción («la descripción es una guía, no una lista»),
  y el juez acepta gimnasia para «pasó parte de su infancia en un centro de acogida» (s083) y para «las abejas»
  (s127). El revisor, al revés, marca como fallo planos de ambiente que son aceptables (s071: Simone con una
  medalla). Sin esa etiqueta ni el juez ni el revisor saben con qué vara medir.
- **Los títulos de capítulo leídos por la voz se buscan como planos normales**: «SECRETO 4: SUS PADRES SON SUS
  ABUELOS» (s082), «SECRETO 6:» (s113), «SECRETO 10: …» (s171). Deberían ser el rótulo del capítulo, no una búsqueda.
- **La despedida también se busca**: «Déjamelo en los comentarios», «suscríbete» (s227-s229). Es un tramo de
  ambiente por definición.
- **El préstamo coge el clip más lejano, que suele ser el del final**: la boda (9:57) aparece a los 0:58, 1:20 y
  1:48. Además de no tener sentido, destripa el final del vídeo en el primer minuto.
- **El revisor culpa al plano equivocado en los repetidos.** Marca el que sale más tarde, pero en los préstamos el
  original es el tardío: s203-s217 y s222-s229 (elegidos por el juez, correctos) figuran como «repite el plano
  s076…», cuando el repetido es el préstamo de los primeros minutos. Debe marcar el prestado (`heredado:`), y
  contar parejas, no planos. De los 57 «Repetido», bastantes son la misma pareja contada una vez por el lado bueno.
- **El gancho**: s002-s009 (los primeros 15 s) son el mismo relleno. Es donde más cuesta un fallo; B lo arregla,
  pero el gancho merece que el relleno sin juez no pueda entrar nunca.
- **Juez barato en todo el vídeo** (`judge.model: gpt-6-luna` en producción, también en el gancho). Los cuatro
  fallos de D son del tipo que un modelo flojo sobre miniaturas pequeñas deja pasar. No lo afirmo: se comprueba en
  diez minutos con `python -m pipeline.rejuzgar newgym3 gpt-5-mini` mirando s065, s074, s097 y s127.

## 2. Estrategia para los huecos (A y C)

Por orden: primero que haya menos, luego taparlos bien.

1. **Planificar por ideas («tiempos»), no por trozos.** El planner agrupa los planos seguidos que cuentan lo mismo
   (una frase o dos, 4-12 s) y hace **una** búsqueda, **un** análisis y **una** decisión del juez por idea. El
   montaje sigue cortando cada 2-4 s, pero los cortes salen de la **misma fuente y el mismo momento**: segundos
   distintos y contiguos del vídeo elegido, cada clip ≤ 5 s. Es lo que ya hacen `continue_action` y
   `scene_search` a medias; aquí sería la regla. Menos búsquedas y extracciones por vídeo (menos proxy y menos
   cuota), y los cortes dentro de una idea se ven hechos a propósito.
2. **Cada idea lleva su etiqueta: literal, de ambiente, o rótulo.** Literal: el juez es estricto y, si no hay,
   foto o rótulo, nunca un clip de otra cosa. Ambiente: vale material del protagonista de la misma época o suceso.
   Rótulo: títulos de capítulo y despedida.
3. **Tapar un hueco alargando al vecino antes que prestando.** Un hueco suele ser 2-3 s entre dos clips buenos:
   lo coherente es que el clip anterior siga (los segundos siguientes de su misma fuente) o que el siguiente
   empiece antes. Con HLS los segmentos de alrededor ya se han bajado casi siempre; pedir el tramo con 3 s de
   margen a cada lado cuesta muy poco.
4. **Si hay que prestar, por cercanía en la historia, no en el reloj**: mismo suceso > mismo capítulo > misma
   época, elegido por parecido de texto entre la frase del hueco y lo que el planner escribió del donante
   (`visualIntent`, `event`). No por CLIP: una frase abstracta no tiene imagen que comparar. Nunca un clip que el
   juez aceptó para un suceso concreto de otro capítulo (la boda), y nunca del último capítulo hacia el primero.
5. **Por debajo de un mínimo de parecido, foto del protagonista o palabras clave.** Mejor un plano sobrio que uno
   sin sentido. Las opciones 3-5 cubren lo que está «en curso» en el informe; la 1 es la que reduce el problema.

## 3. El juez

- No necesita ver el vídeo entero. Necesita saber **si el plano es literal o de ambiente** y **quién debe y quién
  no puede salir** (con retrato). Eso cambia más que añadir contexto.
- Un segundo modelo para todo, no. Sí dos cosas baratas: (a) subir al modelo fuerte solo los planos literales, el
  gancho y los que se juzgaron sobre miniaturas; (b) **el revisor antes del render** como segunda mirada: ya
  existe, cuesta 0,013 $ por vídeo y ve el momento exacto que se va a usar, que es lo que el juez no siempre ve.
  Que lo que marque con seguridad alta en planos literales vuelva al relleno.
- Antes de meter el revisor en la cola: arreglar a quién culpa en los repetidos, que lea los cinco «rotos», que
  encuentre el retrato (`work/<vídeo>/people/`), y que no marque «no tiene que ver» en planos de ambiente.

## 4. GTA y temas sin personas reales: material de partida

Darle la vuelta al flujo: **primero un índice, luego la búsqueda**.

- De cada vídeo de partida (enlaces o clips propios) se hace una vez un índice por escenas: corte de escenas,
  huella CLIP, lo que se dice (subtítulos o Whisper) y **una línea de descripción por escena** escrita por un
  modelo de visión barato sobre una hoja de contactos. En gameplay casi no hay voz útil: la descripción y las
  etiquetas que escriba el dueño al subir el clip («misión X», «Vice Beach de noche») son lo que permite encontrar.
- Cada idea del guion consulta ese índice por texto (descripción, etiquetas, transcripción) y por CLIP, y el juez
  ve las tres mejores. Solo las ideas sin resultado van a YouTube.
- El índice se guarda por canal: el segundo vídeo de GTA ya no parte de cero.
- Los clips propios no son de terceros: sin tope de 5 s y sin crédito. Hay que distinguirlos en el esquema
  (`source: propio`), porque hoy el tope es una constante que usan las validaciones.
- Coste: bajar un vídeo de partida entero por el proxy es caro. Para enlaces de YouTube, índice primero con
  miniaturas del storyboard y subtítulos (gratis), y bajar solo los tramos elegidos.

## 5. Tres cambios con más impacto

1. **Ideas en vez de trozos, con etiqueta literal / ambiente / rótulo** (2.1 y 2.2). Quita la mayoría de los
   huecos en origen y da al juez y al revisor la vara que les falta.
2. **Política de huecos: alargar al vecino, prestar por historia, y si no, foto o palabras** (2.3-2.5), con el
   revisor corregido dentro de la cola antes del render.
3. **Índice de material de partida por canal** (4). Imprescindible para GTA y útil en todos.

## Cómo saber si mejora

Una sola cifra, por vídeo: **planos marcados por el revisor por cada 100**, separando huecos tapados, repetidos
(por parejas) y «no tiene que ver» en planos literales. `newgym3` hoy: 80 de 221. Pasar el revisor a tres vídeos
ya hechos de canales distintos (uno de crimen, uno de GTA) antes de tocar nada, y a los mismos guiones después.

## Anexo: dos vídeos de referencia que no son nuestros (20-11)

Vistos por fotogramas cada 2-4 s y recuento de cortes, sin audio.

**Canal de GTA en inglés (9 min 34 s, hecho a mano o con herramienta propia).** Un corte cada 3,5 s, como
nosotros. La diferencia: casi todos los planos llevan una línea de texto diseñada con la palabra clave destacada
y la fuente del dato («Rockstar:», «Per previews:», «IGN:»), así que la imagen de detrás solo acompaña y no
tiene que encajar con la frase al milímetro. Gráficos propios que imitan la interfaz del juego (tarjetas, cajero,
medidor de niveles, mapa con marcador, móvil), capítulos con título y barra de progreso, citas en tarjeta con foto
y nombre en vez del vídeo de la persona hablando, y un solo mundo visual: todo metraje del juego, sin logos ajenos.

**Vídeo de crimen en español hecho con una herramienta parecida a la nuestra (3 min).** Nunca enseña algo ajeno
al caso: sale de unas diez fuentes, todas del caso, y se queda en cada una entre 4 y 12 s seguidos. Paga por ello
con lo que nosotros evitamos: rótulos de cadena a la vista (Court TV, ABC, Inside Edition, AP, la marca de agua
de un canal en todos los planos de la casa), bustos parlantes de 8-12 s bajo la narración, y los mismos planos de
ambiente tres y cuatro veces. Tiene tarjetas de persona, sellos de fecha y texto a máquina muy parecidos a los
nuestros, pocos (unos cinco en tres minutos).

Qué sale de aquí:

1. **Una línea de texto en pantalla por idea**, escrita por el planner, con palabra clave y fuente. Es lo que más
   reduce el daño de un clip flojo y lo que hace el canal que mejor queda.
2. **Pocas fuentes buenas por vídeo y más tiempo en cada una** refuerza «ideas en vez de trozos» y «material de
   partida»: la otra herramienta no desvaría porque no busca frase a frase.
3. **No copiar sus defectos**: mantener los filtros de busto parlante y de texto en pantalla, y recortar el
   encuadre cuando el rótulo de la cadena solo ocupa la franja de abajo.
4. **Citas en tarjeta** y **un juego de gráficos por canal** (para GTA: estrellas de búsqueda, móvil, mapa,
   medidores), hecho una vez en Remotion.

**Canal de gimnasia en inglés, vídeo sobre Rebeca Andrade (12 min 13 s).** 233 cortes, uno cada 3,1 s: otra vez
el mismo ritmo que nosotros, y la misma plantilla de tarjeta sobre cuadrícula. Lo que hace distinto:

- **Cuando no hay vídeo del momento, pone una foto en tarjeta**, no un clip de otra cosa. Alrededor de un tercio de
  los planos son fotos (familia, infancia, podios, premios). Nosotros dejamos la foto casi al final del relleno
  y antes prestamos clips.
- **Lo que se nombra, se ve y se rotula**: «Guarulhos» sobre una vista aérea de la ciudad, «in 2015», «19 year
  old», «14.166 for Andrade», el nombre de cada persona nueva sobre su imagen. Un rótulo corto cada 20-30 s.
- **Para detalles biográficos sin imagen usa stock de concepto sin caras**: unas manos con guantes limpiando, una
  mano sobre una alfombra, una silueta a contraluz, unas manos tecleando. Planos de 2-3 s. Nosotros tenemos
  `fallback.pexels_for_person: false`, que lo prohíbe del todo en vídeos de persona.
- **Una entrevista de la propia protagonista vuelve varias veces** (0:00, 4:06, 4:24) y abre el vídeo; también hay
  entrevistas de Simone Biles hablando de ella. Sin audio no sé si suenan con su voz; por cómo abre, es probable.
- **Otra persona en pantalla solo cuando la frase va de ella** (Biles, compañeras, un regatista con su nombre).
- Repite algo (la rueda de prensa, el podio, la entrevista), pero como hilo, no como relleno. Se le cuelan logos
  de cadena (CGTN, Eurosport, Access Hollywood) igual que a todos.

Qué añade a la lista: **foto antes que clip prestado** en las ideas de ambiente; **stock de concepto sin caras,
pasado por el juez**, permitido en vídeos de persona para ideas abstractas; y **rótulo de dato cada vez que el
guion nombra un lugar, un año, una edad o una nota**.
