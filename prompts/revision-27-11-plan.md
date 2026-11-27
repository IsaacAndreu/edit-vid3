# Revisión a fondo del 27-11: qué arreglar y en qué orden

Para la sesión que lleva el motor. Pega todo lo que hay debajo de la línea.

---

Se ha revisado `main` en `c2a82eb` por seis frentes a la vez, y esta vez **ejecutando el código** con datos de
prueba más sucios que los de la suite, no solo leyéndolo. La suite pasa (1.277 pruebas); casi nada de lo de abajo
lo detecta, porque las pruebas comprueban que los datos de mentira cuadran entre sí.

Lo marcado **[E]** se reprodujo ejecutando; **[L]**, leído en el código; **[I]**, inferencia. Las líneas son de ese
commit: localiza por nombre de función. Si algo ya no es cierto, sáltalo y dilo.

La parte de seguridad del estudio web va en un documento aparte que te pasa el dueño (el repositorio es público).
**Va antes que todo lo demás, junto con el bloque A.**

Reglas de siempre: un commit por arreglo, con un test que reproduzca el fallo; `npm run typecheck` y la suite en
verde; tu rama; nada que cambie gasto, peticiones a YouTube o lo que sale en pantalla se enciende solo. Y una
nueva: **cada test nuevo usa datos imperfectos** (respuestas incompletas, descargas que fallan, nombres escritos de
dos formas), que es donde estaban todos estos fallos.

## Bloque A · Dinero y noches perdidas

1. **La espera tras tres fallos no existe [E].** `on_result` escribe `tries` (`main.py`, cerca de 945), pero al
   acabar la ronda el vigilante reescribe la entrada desde una copia anterior sin `tries` (969-970). Un vídeo que
   falla siempre se reintenta cada ronda, para siempre: 8 intentos en 77 minutos. Además la «firma» del vídeo es la
   fecha más nueva de su carpeta, así que cualquier archivo que escriba un intento fallido lo cuenta como material
   nuevo. Conserva `tries`, ignora en la firma lo que genera el propio programa, y pon un tope duro por día
   (cinco fallos: en espera, con un solo aviso).
2. **Bucle de gasto en «el guion se arregla solo» [E].** Con `guion.revisar_antes: parar`, `gate()` reescribe
   `imagen_guion.json` desde cero y borra `autoTries`; si el guion reescrito sigue sin pasar, se reescribe otra vez,
   con voz y planificación nuevas. Cuatro intentos: 8 reescrituras, 8 voces, 8 planificaciones. La comprobación va
   después del planner, así que cada reescritura tira una planificación pagada. Guarda los intentos en su propio
   archivo en `materiales/`, nunca reescribas dos veces, comprueba antes de planificar, y tras una reescritura
   sigue adelante. El dueño ya ha puesto `aviso` en el servidor.
3. **El tope por vídeo es por intento [E].** Cinco intentos de 1,40 $ sumaron 7 $ con el tope en 1,50 $; y una
   etapa de texto gastó 6 $ antes de pararse, porque solo se mira entre etapas y en juez y relleno. Cuenta el tope
   por vídeo y día, y llama a `budget.guard` antes de **cada** llamada de pago (modelo, voz, imágenes). Planner,
   verificación, gráficos, títulos, voz, apertura, revisor y las imágenes de `package` no lo miran hoy.
4. **Los vídeos Atlas siguen en DeepSeek [E].** La sección `atlas_guion` no tiene modelo y cae en `deepseek-flash`
   (`main.py` 221 y 1686, `atlas_doblaje.py` 178, `llm.py` 88). Sin saldo, cada uno sale con el código 77 y pone
   toda la cola «en espera» media hora. Que el modelo por defecto siga a `planner.model`, y quita `LLM_API_KEY` de
   las claves obligatorias cuando ninguna sección la use.
5. **Una negativa o un corte de Claude mata el planner [L].** `ClaudeError` no es `LLMError`, así que el reintento
   propio del planner no lo ve. Conviértela. Apunta el coste de las respuestas cortadas a medias (se cobran y no se
   registran). Añade un plazo total a `claude.ask`: hoy una llamada puede quedarse dos horas.
6. **Sin perro guardián en la cola en serie [L].** El guardián solo corre en `run_parallel`. Llévalo al modo en
   serie.
7. **El cortacircuitos casi nunca salta [E].** No salta con ocho vídeos fallando igual en etapas alternas, ni con
   `ValidationError`, ni con un mismo vídeo fallando cinco veces, ni si un vídeo dibujado sale bien entre medias; y
   se crea uno nuevo en cada ronda. Que persista entre rondas, cuente el mismo vídeo, agrupe por tipo y lugar para
   cualquier excepción, y mire una tasa de fallos, no una racha sin interrupciones.
8. **Cerrojos con un PID reutilizado bloquean para siempre [E]** (`.turno-red`, `.cola.lock`, `.proceso`), y en
   silencio, porque el guardián ignora a los que esperan turno. Guarda PID y hora de arranque, caduca por edad, y
   avisa de esperas largas.
9. **El recorte de pausas puede cortar la voz del dueño [E].** Una frase dicha que no está en `guion.txt` se ve
   como un hueco entre palabras del guion: cortó 16 de 18 palabras dichas. Y una pausa hecha a propósito de 6 s
   queda en 1. Corta solo donde el audio esté de verdad en silencio (`silencedetect`) y Whisper no oiga nada; guarda
   copia de cada voz nueva que se suba (hoy `voz.original.mp3` solo se escribe si no existe) y que una subida borre
   los archivos derivados de la anterior.
10. **El arreglo de guion puede borrar una voz grabada [I].** «Sintética» se deduce de que exista
    `voz.genaipro.json`; una grabación subida encima de un vídeo que antes tuvo voz sintética se borraría.
11. **El aviso de fallo confunde [L].** Dice la etapa de un intento anterior, «en unas horas» cuando reintenta al
    minuto, y sale «❌ Falló» también para esperas de cuota o presupuesto y para reinicios. Tipo de error, etapa
    real, número de intento, gasto y tiempo del intento, cuándo es el siguiente; nada para esperas; agrupa repetidos.
12. **Lo que no se cuenta como gasto [L]:** la voz de AI84 (a 0 $), las búsquedas de imágenes de Serper, los cortes
    de Claude, y los hilos de fondo del vigilante y todo lo lanzado desde el estudio, que no miran ningún tope.
13. **El libro de costes y el de cuota no aguantan varios procesos [E].** `costs.json` usa un `.tmp` de nombre fijo;
    en `quota.json`, de 1.600 unidades gastadas por cuatro procesos quedaron apuntadas entre 604 y 714. Cerrojo
    de archivo, o reconstruir desde el diario.
14. **La puerta de despliegue [L]** no mira si la CI pasó, no instala dependencias nuevas y deja pasar nombres
    mal importados dentro de funciones. Despliega solo commits con la CI en verde; añade una prueba del camino de
    Claude con `anthropic` instalado (la de extremo a extremo fuerza `deepseek-flash`).
15. **Una ficha por vídeo** con cada intento: etapa, error, segundos, dólares y GB de proxy. Hoy no se puede ver
    cuánto dinero y tiempo se perdió en un vídeo.

## Bloque B · Seguridad del estudio

Documento aparte. Antes que los bloques C a F.

## Bloque C · Descargas

Probado contra un servidor local que falla como falla el proxy. `selectable()` funciona.

1. **Un solo 502 o un corte pierde el clip [E].** `get()` de la lista y del segmento de arranque en
   `_fetch_hls_locally` (cerca de 2447) y `_range_get` (2681) no reintentan nada; solo los segmentos lo hacen. Y un
   tramo HD que falla es definitivo para el plano (`ingest.py` 395-398). Dos o tres reintentos con espera, en la
   misma sesión, pidiendo solo los bytes que faltan.
2. **Las ventanas a 360p estropean los rangos de bytes de todo el vídeo [E].** El selector de `a360` (2666)
   prefiere siempre el formato 18 (vídeo y audio juntos, sin índice) al 134; da «sin índice» y `no_range` apunta el
   vídeo entero, no el formato. En un vídeo de 20 minutos sin HLS, después fallan también `hd` y `hdav`. Pide solo
   formatos de vídeo sin audio para los rangos y apunta el fallo por (vídeo, formato). `sonda_rango` no lo ve porque
   prueba el 136.
3. **Si HLS falla por algo que no sea un 403, el clip se pierde [E].** En 2168-2170 se relanza todo salvo «format
   is not available». Que caiga a rango de bytes y luego a entero.
4. **Se publican como buenos clips con el audio o el vídeo cortados [E].** `fileio.media_problem` solo mira que
   haya vídeo y la duración del archivo, que es la del flujo más largo. Un audio de 2,55 s en un clip de 4,5 s se
   guarda en caché y se reutiliza. Exige pista de audio cuando se pidió sonido y comprueba la duración de cada
   flujo; compara los bytes recibidos con `Content-Length` o `Content-Range`; fija `urllib3>=2`.
5. **Tras rotar de sesión, rangos y descargas enteras reusan los enlaces viejos [E]:** un 403 pagado seguro. Y
   esos 403 cuentan para `_whole_403 >= 2`, que apaga las descargas enteras para el resto del proceso.
6. **El sonido solo coge la pista doblada [E].** `wa[protocol^=m3u8]` es «la peor» también por idioma: con pistas
   original, doblada y autodoblada elige la autodoblada. Afecta a `quotes.py` y a `expediente.py`, es decir, a
   todas las declaraciones del modo nuevo.
7. **Las fuentes a 60 fps bajan a 480p [E]:** `cap_fps` pone `[fps<=30]` delante, al revés de lo que dice su
   comentario. Y `hd` se queda con el 360p si es el único `avc1` aunque haya 720p en otro códec.
8. **Un vídeo rechazado por «bot» se vuelve a pagar en cada plano [E]** («bot» no está en `_blocking_refusals`).
9. **El techo de 1.500 peticiones por hora son 500 tramos por hora** para toda la máquina; con el ritmo por
   sesión se agota en dos minutos y medio. Cobra menos a los tramos que reutilizan una extracción.
10. **Un 502 del túnel**: reintenta una vez en la misma sesión antes de rotar, y no gastes rotaciones cuando el
    proxy entero no responde.
11. `hd` y `hdav` bajan el mismo vídeo entero dos veces; un tramo que acaba en el final del vídeo se rechaza
    aunque existan 2,5 s; 36 de 80 mensajes de error reales siguen cayendo en «other» (sobre todo los resúmenes en
    español del propio programa). La sincronía y el volumen están bien (±25 ms de normal, 60 ms en el peor caso).

## Bloque D · Modo clásico: lo que sale en pantalla

1. **Se repite el clip del vecino, desde el segundo 0 [E].** `fill_empty_shots` (cerca de 1509) toma el donante más
   cercano, que suele ser el plano de al lado, y `TimelineMedia` no tiene desplazamiento de inicio. Un clip y diez
   huecos: el mismo plano once veces, 35 s seguidos. Con el tope a 12 s, un clip de 12 más su vecino de 9 son 21 s
   seguidos de la misma fuente, y QA mira plano a plano. **Es el camino por defecto, con todo apagado.** Añade un
   inicio al medio (esquema y Remotion) para que un préstamo enseñe otros segundos, excluye los archivos de los
   vecinos, y que QA sume los tramos seguidos del mismo archivo.
2. **`fill_empty_shots` no mira de quién es el clip [E].** `may_lend` solo existe en `limit_text`. Un plano de
   ambiente enseñó el clip literal de «boda 2023»; uno sobre otra persona, un clip de la protagonista.
3. **El gancho todavía puede quedarse en texto [E]:** cuando los donantes se acaban, cuando los clips son de ideas
   literales, cuando la época difiere, o cuando el nombre está escrito distinto («Simone» y «Simone Biles» no
   casan: comparación exacta). Tras agotar donantes, reutiliza no contiguos, luego cualquier clip juzgado cuyo
   «quién debe salir» contenga al sujeto, luego una foto. Nombres por palabras y con `people.json`.
4. **El tope de texto no se cumple [E]:** 35 % con el tope en 10 %. La rama «sin donante» y los títulos no tienen
   límite; `chalkboards` junta planos seguidos en pizarras de 6 s e ignora `board_max_seconds`; una despedida leída
   se convirtió en 12 s de pizarras cortadas a media palabra; sin línea de idea, la pizarra sigue saliendo del
   trozo del plano («Y», «en Spring»).
5. **Uno de cada cuatro clips sale en tarjeta pequeña [E]:** `timeline.card_share: 0.25` de serie puso 48 de 200
   clips normales en tarjeta, con 72 saltos entre tarjeta y pantalla completa.
6. **Las recetas se aplican a medias [E].** Ningún canal tiene `montaje.receta`; y `persona` no enciende
   `planner.ideas`, así que `literal_ambient` y `ambient_photo_first` no hacen nada y `max_text_share` presta el
   clip de cualquiera. `suceso` pone `cobertura`, que solo corre con ideas. Que la receta encienda lo que necesita
   o falle diciéndolo. Quita de `agrupar.SYSTEM` la frase «si no hay ese clip, el plano se queda en texto».
7. **El orden del relleno contradice el objetivo [L]:** para una idea de ambiente, el clip «juzgado» de la
   protagonista entra sin juez por defecto (`judge_filler` apagado) y detrás de una foto juzgada; para una literal,
   la foto de la persona entra sin juez; en canales que no son de persona, el stock de Pexels sin juez va antes que
   ambos. Y las fotos «de la época» nadie las comprueba.
8. **Las medidas engañan [E]:** la pantalla final cuenta en el denominador; un gráfico a pantalla completa sobre un
   clip cuenta como imagen (56 s de tarjetas dieron 0 % de texto); una apertura de 15 s pone «primera imagen» en 0
   aunque después haya 30 s de pizarra. Y la página «Puntería» está vacía de serie porque solo se rellena con el
   revisor. Calcula las medidas desde el montaje para todos los vídeos.
9. **La raíz, antes del juez [I]:** tres vídeos por plano, dos o tres ventanas, y el juez ve tres opciones una vez.
   Dos rondas para las ideas literales; y `protagonist_pool` ordena con notas de CLIP calculadas para otros planos.
10. Ninguna prueba ejercita juntas las ideas, el gancho, el tope de texto y el revisor. Una, a la altura de
    `with_graphics`.

## Bloque E · «Material primero»

Veredicto de la revisión: **una primera ejecución real no dará un vídeo que se pueda ver.** Lo que sí sirve hoy es
la página de investigación.

Lo que impide que funcione:

1. **Se pierden todas las declaraciones por el camino normal [E/L].** `expediente.py` (cerca de 194) guarda
   «subtítulos» o «transcrito (…)» como idioma, eso llega a Whisper como `language=`, que lo rechaza, y `verify`
   descarta la declaración. Una prueba (`test_expediente.py:179`) da por bueno ese valor. Guarda el código de
   idioma aparte.
2. **`best_match` revienta si el clip es más corto que la frase [E]** (`quotes.py:120`). `bloques.py` recorta el
   clip al tope pero deja la frase entera: con el tope a 12 s se cae toda declaración de más de 12 s. Las frases de
   menos de cuatro palabras nunca pueden pasar.
3. **Un top 10 deja los puestos 7 a 10 vacíos [E]:** `max_sources: 24` a cuatro por puesto.
4. **Falla después de gastar [E]:** sin voz en el canal, tras pagar las descargas; un puesto sin secuencias, tras
   pagar la voz. Comprueba antes: voz, tope de clip suficiente, fuentes en cada puesto.
5. **No está en la cola.** Son tres trabajos sueltos lanzados desde el estudio, con el estado en memoria: un fallo
   deja la página en «investigando…» para siempre, sin aviso, sin plazo y sin cerrojo frente a la cola.

Contenido equivocado, sin avisar:

6. **Cortes viejos al repetir el montaje [E]:** `cut-NNN.mp4` se guarda por posición; el subtítulo de una persona
   puede quedar sobre el clip de otra. Clave por archivo, inicio y duración.
7. **Metraje de otro puesto bajo la narración de un puesto [E]** cuando sus secuencias fallan.
8. **La regla del nombre es floja [E].** `name_in_source` busca las palabras del nombre como subcadenas en título,
   descripción o transcripción: «Mark Rivers» pasa por «remarkable» y «drivers»; un nombre que dice el presentador
   se le pone al vecino. `confidence`, `evidence` y `eventMatch` no se usan para decidir nada, y no hay lectura del
   rótulo en pantalla. Nombre solo con prueba «dicho, título o descripción», palabras completas y un mínimo de
   seguridad; si no, el papel.
9. **Los datos del narrador solo se comprueban si llevan cifras [E].** «El conductor, John Smith, murió en el acto
   en Dallas» pasa como frase de enlace.
10. **El gancho puede destripar el número 1 [E]** si el modelo escribe el puesto como texto o lo omite.
11. Los enlaces del dueño: uno privado se ignora en silencio; un Short o un directo entran como primera fuente; y
    se asignan por posición, así que si el modelo ordena al revés el enlace 1 cae en otro caso.
12. El metraje sin voz no se puede usar: `run()` nunca pasa `scenes_fn`, el índice por escenas no está conectado.
13. La voz se desfasa unos 2 s al final de 60 bloques; con un 40 % de tramos fallidos queda un vídeo de 5 minutos
    para 10 pedidos, sin reintentar ni buscar otra toma; «investigar otra vez» descoloca los bloques ya escritos.
14. Faltan del plan: formulario (tono, doblaje, voz, música, idioma), música, tope propio del modo, revisor
    adaptado, QA, títulos y miniatura.

Orden: 1, 2, 4 y 6; luego meterlo en la cola con estado en disco; luego 3, 7-13. **Y después un top de tres
puestos real que el dueño vea entero**, con la comprobación de servidor que cierra este documento.

## Bloque F · Radar, huecos e idiomas

1. **Los idiomas nuevos se ignoran en silencio [E].** `idiomas.configured()` descarta cs, id, pl, nl, tr. La
   detección por palabras lee un título checo como portugués y uno indonesio como italiano; títulos sin palabras
   frecuentes («Tiefsee Doku 2026») no son de ningún idioma, así que la competencia se cuenta de menos (45 vídeos
   alemanes sin idioma de audio: 0 de competencia). Añade los idiomas, falla si llega un código no soportado,
   trata «desconocido» como desconocido, y usa escritura, diacríticos y trigramas.
2. **Un idioma sin resultados encabeza «doblar» [E]:** el hueco se calcula como la demanda del origen (900.000
   veces), y `doblar.rank` no filtra por veredicto. Nunca ordenes un idioma con cero resultados reconocidos.
3. **«Empezar en español» puede salir de vídeos en inglés [E]:** `huecos.measure` no comprueba el idioma. Con dos
   resultados da «hueco» 7,1: exige un mínimo.
4. **El original doblado no se ve [E]:** `in_language` devuelve con el primer campo; audio en inglés con título en
   alemán es «no alemán». Guarda las dos señales por separado: es justo el dato que hace falta.
5. **El radar semanal no acaba la lista [E]:** mide los `semanal_max_vigilados` primeros, da la semana por hecha y
   la siguiente repite los mismos. Y **un canal que dé error lo para para siempre** sin guardar ni lo medido ni lo
   gastado (`refresh` solo captura `NoKeysLeft`). Rota por «más tiempo sin mirar» y guarda tras cada lote.
6. **La lista de 2.596 canales no la lee ningún código**, y al importarla se tiran sus columnas. Por sus propios
   números solo 674 pasan los mínimos. Fíltrala y agrúpala sin gastar cuota: por categoría y etiquetas.
7. `evaluate`: la mediana incluye vídeos subidos hoy; los directos terminados cuentan como vídeos largos; un canal
   de 2015 con ocho vídeos visibles cuenta como nuevo; suscriptores ocultos pasan el filtro.
8. **El radar diario no tiene tope ni respeta `keep_for_queue` [L]:** con 37 perfiles, entre 18.000 y 30.000
   unidades al día. Y la caché de búsquedas nunca acierta con `days`, porque `publishedAfter` lleva segundos:
   redondea al día.
9. **De referencias a canal: lo medido no llega al vídeo [E].** Ritmo de corte, duración y palabras por minuto no
   se escriben en el perfil ni los lee nadie fuera de `formula.py`. Referencias en inglés dejan el canal en inglés,
   sin opción de idioma. `aprender.link` no se llama nunca.
10. Ideas baratas que la revisión comprobó posibles con lo que el código ya recibe:
    - **Visitas ganadas en la semana**: `channels()` ya devuelve el total de visitas; guardándolo cada semana, el
      aumento es la señal de «se está haciendo viral ahora», por unas 52 unidades para toda la lista. Las subidas
      se leen solo de los canales que se han movido.
    - **Redes de doblaje sin gastar**: el nombre del canal de cada resultado ya llega; quitando el sufijo de idioma
      queda la marca, y la misma marca en dos idiomas es una red.
    - **El paso 3 del radar, tal como lo escribí, no cabe**: 15 nichos por 7 idiomas son unas 32.000 unidades;
      caben 6 o 7. Dimensiónalo a la cuota real y enséñalo.

## Comprobación en el servidor antes de fiarse de «material primero»

Con un canal que tenga voz y el tope de clip a 45 s, un **top de 3** con tres enlaces elegidos:

1. `python main.py --expediente <vídeo>`: cada puesto con dos o más fuentes con tramos; abrir cinco declaraciones
   en YouTube en su segundo y mirar quién habla de verdad.
2. `python main.py --bloques <vídeo>`: leer cada frase del narrador contra sus referencias.
3. `python main.py --montar <vídeo>` y, en `work/<vídeo>/montaje_mf.json`, que `statementsChecked` esté casi todo
   por encima de 0,55.
4. Ver `video-final.mp4` entero: gancho sin el número 1, cada subtítulo con su boca y su rótulo, el crédito con su
   metraje, y la voz contra la imagen en el último minuto.
5. Montar otra vez y comprobar que los planos no cambian.

## Al terminar cada bloque

`prompts/pipeline-progress.md` con lo hecho, lo apagado y cómo probarlo; y di con claridad qué no has podido
comprobar. Si algo de aquí choca con lo que sabes del código o de producción, explícalo y propón otra cosa.
