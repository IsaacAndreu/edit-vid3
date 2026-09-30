# Hoja de ruta · canal de negocios · 5 vídeos por semana

**Objetivo:** en 4 semanas (20 vídeos, 4 de cada serie) saber qué serie funciona y quedarse con ella.
Cada semana se hace **un vídeo de cada serie**:

| Serie | Qué es | Ejemplo de título |
|---|---|---|
| `auge-caida` | Una empresa que lo tuvo todo y lo perdió | Cómo Pescanova pasó de líder mundial a la quiebra |
| `estafas` | Un fraude financiero contado como true crime | La estafa que engañó a 350.000 familias españolas |
| `negocio-oculto` | De dónde sale de verdad el dinero de una marca conocida | Cómo gana dinero Ryanair con billetes de 10 € |
| `deporte-dinero` | El dinero de clubes, fichajes y ligas | El agujero de 1.000 millones del Barça |
| `economia` | Un problema de la economía de España con datos | Por qué un piso cuesta 20 años de sueldo |

## Antes de empezar (una vez)

1. En `canales/negocios.yaml` rellena:
   - `ideas.my_channel`: tu canal, `"@tucanal"`. Lo necesita la comparativa.
   - `ideas.competitors`: entre 3 y 6 canales de la competencia.
2. Pon música en `assets/negocios/music/`. Si la carpeta está vacía, se usa la de `assets/`.
3. `git pull` y `pip install -U "yt-dlp[default]"`.

## La semana tipo

| Día | Qué haces | Comando |
|---|---|---|
| Lunes (mañana) | Sacar las 5 ideas de la semana, una por serie. Elige y cambia lo que quieras. | `python main.py --semana negocios` |
| Lunes | Escribir los 5 guiones y grabar las 5 voces. Crear `materiales/<slug>/` con `titulo.txt`, `guion.txt`, `voz.mp3` y `config.yaml` (`canal: negocios` y `serie: …`). | — |
| Lunes y martes (noche) | Hacer los vídeos, 2 a la vez. | `python main.py --all` |
| Martes y miércoles (mañana) | Revisar cada vídeo en el editor: cambiar planos flojos y retocar textos. Mirar `diagnostico.md` si algo falló. | `python main.py --editor <slug>` |
| Miércoles a domingo | Publicar **uno al día, siempre a la misma hora** (por ejemplo, a las 18:00). | — |
| Domingo | Copiar de YouTube Studio el CTR y la retención de los vídeos que ya tengan 7 días y generar la comparativa. | `python main.py --series negocios` |

**Rota el orden de publicación cada semana**, para que ninguna serie tenga siempre el mejor día:

- Semana 1: auge-caída, estafas, negocio oculto, deporte y dinero, economía.
- Semana 2: estafas, negocio oculto, deporte y dinero, economía, auge-caída.
- Y así sucesivamente.

## Reglas para que la prueba sea justa

- **La misma calidad en las 5 series:** la misma duración (9-11 min), el mismo cuidado con el
  título y la miniatura, y la pregunta o gancho en los primeros 5 segundos.
- **Mide a la misma edad:** los datos de CTR y retención a los 7 días de publicar. La comparativa ya
  usa visitas por día, pero un vídeo de 2 días no se compara con uno de 20.
- **No borres ni resubas vídeos** que funcionan mal: también son datos.
- **Shorts:** entre 1 y 2 por vídeo, como tráiler. No cuentan para decidir la serie.
- En `config.yaml` de cada vídeo, cuando tenga 7 días:
  ```yaml
  estadisticas: {ctr: 5.4, retencion: 41}   # de YouTube Studio: CTR de impresiones y % medio visto
  ```

## Cómo leer la comparativa

| Síntoma | Qué falla | Qué cambiar |
|---|---|---|
| CTR bajo (< 4 %) | Título y miniatura | El patrón de título de la serie (`package.hint` en la serie) |
| Retención baja (< 35 %) | El guion o el ritmo | Gancho más rápido y menos contexto al principio |
| CTR y retención buenos, pocas visitas | Al tema le falta demanda | Temas más conocidos dentro de la serie |
| Una serie sube sola a las 2-3 semanas | YouTube la está recomendando | Más vídeos de esa serie |

## Decisión (al acabar la semana 4)

- **Ganadora:** la mejor mediana de visitas por día con CTR ≥ 4 % → **3 vídeos por semana**.
- **Segunda:** → **1 por semana**.
- **Hueco libre:** → **1 por semana** para probar una serie nueva o repetir una que falló por el título.
- **Se descarta** una serie que, en 4 vídeos, no pasa de la mitad de la mediana del canal **y** tiene
  CTR < 3 %.

## Costes y tiempo

- Unos 0,7 $ de APIs por vídeo, así que unos 3,5 $ por semana.
- Si las noches siguen siendo lentas por las descargas, hazlo en 3 noches (2 + 2 + 1).
  `out/<slug>/diagnostico.md` dice qué etapa tardó.
