# Canal de aviación: referencias (NexLev, 02-10-2026)

Unos 50 canales de aviación en inglés y español, de la búsqueda de canales de NexLev y sus últimos vídeos (la
herramienta de vídeos outlier llegó al límite, así que no es el mercado completo).

## Lo que funciona en inglés (millones de visitas con canales de 10-40K suscriptores)

| Formato | Canal | Vídeo | Visitas |
|---|---|---|---|
| Por qué fracasó X / dramas del negocio | Beyond Sky | Por qué las aerolíneas RECHAZAN el 777X | 1,6M |
| | Jet Crumbs | Cómo Boeing mató estratégicamente al A380 | 1,7M |
| | Jet Crumbs | Qué pasa cuando una aerolínea cierra | 1,3M |
| | Airspeed (7 vídeos, 17K subs) | ¿Por qué el Spirit of St. Louis no tenía ventana frontal? | 1,6M |
| Economía de aerolíneas y aeropuertos | Air Core (6 vídeos) | El arte miserable del taxeo | 936K |
| | Aviation Explained | Las PEORES aerolíneas | 299K |
| Comparativas visuales | Gloww (3,7K subs) | Comparación de tamaño de aviones | 765K |

## Lo que existe en español

- **Plane Curious Español**: 17K subs, ~1.000 $/mes, documentales de 16-52 min (A350, 777, A380), 165-264K visitas.
- **Ingeniería del Aire** (el mejor dato): 13K subs, vídeos de 8-10 min: "¿Por qué los aviones cruzan el Atlántico
  de noche?" (759K), "¿Por qué ya no hay aviones de 4 motores?" (438K).
- Aeronum, Historia del Motor: 24-27K subs, hasta 565K, pero historia militar/naval.
- Minutos de Aviación: clips de errores de pilotos (55-70K) con material ajeno → evitar (copyright).
- Canales con IA pequeños (AEROPLANET 12K subs y 17 $/mes; Experto en aviación 1,7K): lo genérico con IA no funciona.

## Hueco

El estilo Beyond Sky / Jet Crumbs (negocio, rivalidades, fracasos) casi no tiene competencia propia en español.
RPM estimado en español 1,5-2,3 $ frente a 2-4 $ en inglés: el volumen tiene que compensarlo.

## Cómo queda en el programa (`canales/aviacion.yaml`)

- Series (una por semana para ver cuál funciona): `fracasos` (cronología), `rivalidades` (Boeing contra Airbus),
  `por-que` (explicativo, estilo Ingeniería del Aire), `dinero` (cuánto cuesta / cómo gana dinero), `tamanos`
  (récords y comparativas de tamaño, estilo Gloww).
- Metraje: aviones reales y concretos (aerolínea + modelo + lugar), vídeos oficiales de Airbus/Boeing, anuncios
  antiguos de aerolíneas, noticias y spotters. Nunca simuladores ni el material de la competencia (bloqueado por
  nombre de canal). Pexels permitido: un avión genérico despegando es b-roll válido.
- Aspecto: azul marino con ámbar de cabina y azul cielo, paquete `editorial`, cifra gigante sobre el avión,
  capítulos numerados, tono de color `frio`.
