# Fallo: los tramos por rango de bytes no funcionan nunca en producción (22-11-2026)

Para la sesión que lleva el motor. Datos de `python main.py --youtube-stats 2` en el servidor (13 vídeos).

## Lo que se ve

- `download (rango)`: 886 peticiones, **884 fallidas**, todas con el mismo texto:
  `faltan moov o sidx (['\xNfB\xN\xN'])` (el informe cambia las cifras por N).
- Ese «tipo de caja» son los bytes 4-7 del archivo. Con las cifras tapadas encaja con `9F 42 86 81`, que es lo que
  sigue a la cabecera EBML `1A 45 DF A3`: lo que llega **no es un mp4**, parece Matroska/WebM, aunque
  `_fetch_byte_range` pide `[ext=mp4][protocol=https]`. No lo he podido comprobar: puede ser también otro
  envoltorio de la respuesta. Lo seguro es que no empieza por `ftyp`.
- Como el rango falla, el tramo cae a «sin HLS y entero supera el tope del proxy residencial»: **1.376 veces** en
  dos días. Un solo vídeo de GTA (`rompergtavitrucos`) acumula 1.775 fallos «other»: se queda casi sin metraje por
  esto. Es justo el caso para el que se hizo `byte_ranges`.
- `byte_ranges` está encendido en todo el servidor desde el 22-11.

## Qué hacer

1. **Diagnóstico antes de tocar**: en el fallo `NoIndex` de `plan()` y `needed_head()`, registra el itag, `ext`,
   `vcodec`, `container` y `protocol` del formato elegido, la cabecera `Content-Type` de la respuesta, su código
   (200 o 206) y los primeros 16 bytes en hexadecimal sin tapar. Con una sola fila de esas se sabe qué llega. Añade
   una sonda sin efectos (`python -m pipeline.sonda_rango <vídeo>`) que haga solo la primera petición y lo imprima,
   para que el dueño la lance con un vídeo de `rompergtavitrucos`.
2. Según lo que salga:
   - si el formato elegido es de verdad webm (la selección no está respetando `ext=mp4`, o `_has_dash_mp4` deja
     pasar vídeos que solo tienen vp9/av1 en webm): arregla la selección y, para los que solo tengan webm, lee el
     índice `Cues` de Matroska en vez de `sidx`, o déjalos fuera con un motivo propio;
   - si es un mp4 envuelto en otro formato de respuesta: no lo fuerces; explica qué es y qué cliente de yt-dlp da
     enlaces que sí devuelven el archivo tal cual.
3. **Que el motivo se vea**: esos 884 fallos y los 1.376 descartes salen como «other». Dales causa propia
   (`rango-sin-indice`, `sin-hls-tope`) en `error_cause`, y que el descarte repetido del mismo vídeo no escriba
   una fila por plano.
4. Test con un archivo webm y con un mp4 sin `sidx` servidos por el servidor HTTP local de `tests/test_byte_ranges.py`.

## De paso, en la misma salida

- `proxy-túnel`: 328 extracciones con «Tunnel connection failed: 502 Bad Gateway». Comprueba que un 502 del túnel
  se reintenta con otra sesión (la regla de «túnel sin código = transitorio» puede no cubrir el caso con código).
- Los 138 errores 429 son todos de `get` a `www.youtube.com/api/timedtext` (subtítulos), concentrados entre la 1 y
  las 3 de la madrugada UTC. La caché negativa ya existe; mira si esas peticiones salen directas desde la IP del
  servidor y si a esa hora coinciden varios vídeos empezando a la vez.
