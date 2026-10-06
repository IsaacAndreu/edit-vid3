# Formatos de vídeo

Cada fichero `<nombre>.yaml` es un formato: la forma de contar el vídeo, sea del canal que sea.
Para elegir uno, pon `format: <nombre>` en la `config.yaml` del vídeo. También puede ir en el perfil
del canal o en una serie. Para ver la lista: `python main.py --formatos`.

| Clave | Para qué sirve |
|---|---|
| `nombre`, `descripcion`, `ejemplos` | Lo que sale en `--formatos`. |
| `guion` | Cómo se divide el guion en escenas y qué se busca para cada una. Se añade a las instrucciones del planificador. |
| `graficos` | Qué gráficos animados pegan con este formato y cuándo usarlos. |
| `segundos_por_grafico` | Cada cuántos segundos va un gráfico, más o menos (el valor por defecto es 100). |
| `tipos` | Gráficos que el formato necesita aunque el canal no los tenga en `graphics.types` (p. ej. `[receipt]`). |
| `titulos` | El patrón de los títulos y de los textos de la miniatura. |
| `escritura` | La estructura del guion para el «Borrador de guion» (página Guiones), p. ej. `caso-real`. |

**Un formato nuevo:** copia el que más se parezca, cámbiale el nombre y edítalo. No hay que tocar
código. Solo `ranking` y `prohibidos` tienen además código propio (tarjetas de puesto y sello
PROHIBIDO).

**Si cambias el formato de un vídeo ya empezado:** usa `python main.py --slug <vídeo> --force planner`
para que se rehaga el reparto en escenas.
