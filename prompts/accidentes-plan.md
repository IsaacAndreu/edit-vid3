# Plan de construcción — reconstrucciones de accidentes aéreos

Objetivo: vídeos que explican accidentes de avión reales con reconstrucciones dibujadas en código
(mapa, perfil de vuelo, terreno 3D, cabina en texto), sin sangre ni morbo, todo sacado de fuentes
oficiales. Dos formatos:

- **Caso cerrado** (8-15 min): un accidente con informe final. Qué pasó, por qué y qué cambió después.
- **Lo que se sabe** (1-5 min, también Short vertical): un accidente reciente con los datos
  confirmados hasta ese momento, cada uno con su fuente, y la reconstrucción preliminar.

Se construye **encima de Atlas** (`remotion/atlas/`): mismo storyboard, mismos anclajes `{say}` a la voz,
mismo estilo, mismo `--atlas-guion`, mismo doblaje a 5 idiomas. Lo nuevo son escenas de vuelo.

## 1. Por qué (datos de NexLev, noviembre de 2026)

- Un accidente reciente con mucha atención (el Learjet 60 de Florida, principios de noviembre) dio en una
  semana vídeos de 0,2-4,4 M de visitas en canales de 100 a 10.000 suscriptores: «The Last 77 Seconds of the
  Florida Learjet 60» 4,4 M; «Accidente Aéreo del Learjet 60 en West Palm Beach (lo que se sabe hasta ahora)»
  1,9 M; «Lo que muestran los datos sobre el accidente…» 1,1 M; en portugués 752 mil; en italiano
  «74 secondi: la caduta del Learjet… ricostruita con i dati di volo e l'audio della torre» 238 mil
  (canal de 1.000 suscriptores).
- Las animaciones cortas «en tiempo real» funcionan solas: «The Crash of Air India 171 | REAL TIME
  ANIMATION» 946 mil (2:29); «Jeju Air 2216 Final 37 Seconds Reconstruction» 534 mil (0:55).
- Casos cerrados con simulación: MPC Flights (110 mil suscriptores) 1-6,7 M por vídeo.
- Ingresos por visualización estimados bajos-medios (≈1,5-3,8 $ por 1.000): los anuncios se limitan en
  tragedias recientes. El volumen y el doblaje lo compensan; el caso cerrado paga mejor que la noticia.
- Riesgo: en cada accidente grande salen decenas de canales en 48 h. Gana quien llega pronto **y** con datos
  verificados (los títulos que más funcionan prometen datos: «lo que muestran los datos», «rebuilt in 3D»).

## 2. Decisiones de arquitectura (cerradas)

1. **Extender Atlas, no un motor nuevo.** Escenas nuevas en `remotion/atlas/scenes/`, tipos nuevos en
   `remotion/atlas/schema.ts`, los mismos `theme.ts`, `layers`, `overlays` y bucle visual.
2. **Reproducir datos, no simular física.** El avión se mueve entre puntos de control sacados del informe
   (tiempo, posición, altitud, velocidad, rumbo). Entre dos puntos se interpola. Nada de física inventada.
3. **Cada punto de vuelo lleva su fuente** (documento y página o tabla). El validador falla si falta.
4. **Sin audio de cabina ni de la torre.** Las frases se ponen como texto en pantalla, citadas del informe.
5. **Estilo explicativo**: siluetas limpias de avión, líneas de trayectoria, terreno real. Sin restos, sin
   fuego, sin víctimas. El impacto se marca con un punto y una hora, no se dibuja.
6. **Rótulo fijo** en cada escena de reconstrucción: «Reconstrucción simplificada · Fuente: <organismo>».

## 3. Capa de datos

- `public/accidentes/<caso>/vuelo.json`: `{fuente, puntos: [{t, lat, lon, alt_ft, kias?, rumbo?, ref}]}`.
  `t` en segundos desde un instante del informe; `ref` = «NTSB DCA24MA001, tabla 2».
- `public/accidentes/<caso>/aeropuerto.json`: pistas (umbrales y rumbo) desde los datos públicos del
  aeropuerto o del informe.
- Terreno: el mismo de Atlas (`npm run atlas:data -- terrain`) alrededor de la trayectoria.
- Fuentes válidas: informes de NTSB (dominio público EE. UU.), BEA, AAIB, CIAIAC, JTSB… y sus anexos.
- **ADS-B** (trayectorias de radares): OpenSky Network es solo para uso no comercial; ADS-B Exchange tiene
  licencia comercial; Flightradar24 no permite reutilizar. Usarlos solo con licencia; por defecto, los datos
  del informe.
- Script `npm run accidentes:data -- vuelo <tabla.csv>`: convierte la tabla de datos del informe a
  `vuelo.json` y comprueba unidades y saltos imposibles (más de 2.000 ft en 1 s, etc.).

## 4. Escenas nuevas

| Tipo | Qué muestra |
|---|---|
| `atlas-flight-track` | Mapa de relieve (el de Atlas) con la trayectoria dibujándose, el avión como silueta orientada, horas en los puntos clave, el aeropuerto y sus pistas. |
| `atlas-flight-profile` | Perfil vertical: altitud contra tiempo o distancia, el terreno real debajo, la senda de aproximación ideal en línea discontinua, anotaciones («aviso de pérdida», «tren abajo»). |
| `atlas-flight-3d` | El terreno 3D de Atlas con la trayectoria en el aire y el avión siguiéndola; cámara de seguimiento o fija. |
| `atlas-cockpit` | Reloj de los últimos minutos y tarjetas con las frases del informe (quién habla, hora); a un lado, altitud, velocidad y velocidad vertical como números que cambian según `vuelo.json`. |
| `atlas-aircraft` | Silueta lateral o en planta del tipo de avión (SVG de `scripts/atlas-diagrams/`) con la pieza implicada resaltada (timón de profundidad, motor, sensor). |
| `atlas-known` | «Lo que se sabe»: tarjetas confirmado / sin confirmar / fuente y hora de cada dato. |

Más el formato **vertical 9:16** (composición `AtlasShort`, 1080×1920) para los Shorts.

## 5. Reglas (además de las de Atlas en `CLAUDE.md`)

1. Ningún dato de vuelo sin `ref`. Ninguna causa antes del informe final; en el preliminar se dice
   «el informe preliminar indica…».
2. Nombres de tripulación y pasajeros: solo si el informe o las autoridades los publicaron y aportan algo; nunca
   fotos de víctimas.
3. Nada de «disturbing», «aterrador» en los rótulos de las escenas (el título del vídeo lo decide el canal).
4. Imágenes reales: oficiales o con licencia, cortas, como ya hace el programa (5 s de terceros).

## 6. Fases

Cada fase: renderizar fotogramas (mitad y final de cada escena), revisarlos y corregir; typecheck y tests;
commit y apuntarlo en `prompts/accidentes-progress.md`.

### Fase A0 — Datos y esquema
`vuelo.json` + validador + script de conversión; tipos nuevos en el esquema (aún sin dibujar).
Caso de prueba: un accidente cerrado con tabla de datos pública en el informe final.
**Puerta:** si el caso de prueba no da una trayectoria limpia con los datos del informe, parar y decidir.

### Fase A1 — Trayectoria en el mapa (`atlas-flight-track`)
Sobre el mapa de relieve; silueta orientada por el rumbo; horas; pistas.

### Fase A2 — Perfil vertical (`atlas-flight-profile`)
Terreno real bajo la trayectoria; senda ideal; anotaciones ancladas a la voz.

### Fase A3 — Vuelo en 3D (`atlas-flight-3d`)
Trayectoria y avión sobre el terreno 3D; cámaras de seguimiento.

### Fase A4 — Cabina y avión (`atlas-cockpit`, `atlas-aircraft`)
Reloj, tarjetas de frases, instrumentos en números; siluetas de 4-5 tipos de avión comunes.

### Fase A5 — «Lo que se sabe» y vertical (`atlas-known`, `AtlasShort`)
Tarjetas de confirmado y sin confirmar; las escenas anteriores en 9:16.

### Fase A6 — Vídeo de referencia: un caso cerrado completo
Guion y escenas a mano, de principio a fin, con el informe final. Lo revisa una persona antes de publicar.

### Fase A7 — Producción
Canal `accidentes-aereos` (y sus dobles por idioma); el radar de noticias detecta accidentes y abre un
borrador «lo que se sabe» con los enlaces a las fuentes oficiales; doblaje como Atlas.

## 7. Límites conocidos
- No es CGI realista: siluetas y terreno, no aviones con texturas ni efectos.
- Cada caso exige leer el informe y extraer datos: la IA ayuda, una persona revisa las cifras.
- En las primeras horas casi no hay datos fiables: el formato «lo que se sabe» se queda corto a propósito.
