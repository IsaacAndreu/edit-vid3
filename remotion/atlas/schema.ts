/**
 * Esquema del storyboard Atlas (prompts/atlas-plan.md §4).
 * Contrato único entre quien escribe el vídeo y quien lo renderiza.
 *
 * Convenciones: todo lo que aparece lleva `at: At`; colores sólo por `Accent`;
 * textos sólo por `Rich` o string; geografía sólo por `LonLat` o ruta a un archivo generado.
 */
import { z } from 'zod';

export const accentSchema = z.enum(['danger', 'data', 'good', 'amber', 'ink']);
export type Accent = z.infer<typeof accentSchema>;

export const lonLatSchema = z.tuple([
  z.number().min(-180).max(180),
  z.number().min(-90).max(90),
]);
export type LonLat = z.infer<typeof lonLatSchema>;

/** Momento en el tiempo: ancla a la narración o segundo absoluto desde el inicio del vídeo. */
export const atSchema = z.union([
  z
    .object({
      say: z.string().min(1, 'say: la frase ancla no puede estar vacía'),
      nth: z.number().int().min(1).optional(),
      offset: z.number().optional(),
    })
    .strict(),
  z.object({ t: z.number().min(0) }).strict(),
]);
export type At = z.infer<typeof atSchema>;

/** Texto con resaltado: "Clear-headed for *a minute or less*". */
export const richSchema = z.union([
  z.string(),
  z.object({ text: z.string(), accent: accentSchema.optional() }).strict(),
]);
export type Rich = z.infer<typeof richSchema>;

const cornerSchema = z.enum(['tl', 'tr', 'bl', 'br']);

export const overlaySchema = z.discriminatedUnion('kind', [
  z
    .object({
      kind: z.literal('info-card'),
      at: atSchema,
      until: atSchema.optional(),
      corner: cornerSchema,
      kicker: z.string().optional(),
      title: richSchema,
      lines: z.array(z.object({ text: z.string(), at: atSchema.optional(), accent: accentSchema.optional() }).strict()).optional(),
      sub: z.string().optional(),
    })
    .strict(),
  z
    .object({
      kind: z.literal('stamp'),
      at: atSchema,
      text: z.string(),
      /** Posición en fracción del lienzo (0–1). */
      x: z.number().min(0).max(1),
      y: z.number().min(0).max(1),
    })
    .strict(),
  z
    .object({
      kind: z.literal('counter'),
      at: atSchema,
      corner: cornerSchema,
      kicker: z.string(),
      steps: z.array(z.object({ value: z.string(), at: atSchema }).strict()).min(1),
      sub: z.string().optional(),
    })
    .strict(),
  z
    .object({
      kind: z.literal('legend'),
      at: atSchema,
      corner: cornerSchema,
      /** Segunda línea pequeña (fuente o método: «CALCULATED FROM TERRAIN DATA · 1° SQUARES»). */
      sub: z.string().optional(),
      items: z
        .array(
          z
            .object({
              style: z.enum(['dashed', 'solid', 'fill']),
              accent: accentSchema,
              label: z.string(),
            })
            .strict(),
        )
        .min(1),
    })
    .strict(),
]);
export type Overlay = z.infer<typeof overlaySchema>;

export const sceneBaseShape = {
  id: z.string().min(1),
  start: atSchema,
  theme: z.enum(['paper', 'night']),
  /** Índice en meta.chapters; controla el indicador de capítulos. */
  chapter: z.number().int().min(0).optional(),
  /** 'continuous' = hereda la cámara de la escena anterior, sin fundido. */
  enter: z.enum(['fade', 'continuous']),
  kicker: z.string().optional(),
  title: richSchema.optional(),
  sourceNote: z.string().optional(),
  overlays: z.array(overlaySchema).optional(),
  /** URL o cita de cada dato usado; obligatorio si hay cifras. */
  sources: z.array(z.string()).optional(),
};

/** Lienzo vacío: sólo fondo, HUD y superposiciones. Útil para pruebas y transiciones. */
export const blankSceneSchema = z.object({ ...sceneBaseShape, type: z.literal('atlas-blank') }).strict();

/* ── Fase 1: escenas de texto ─────────────────────────────────────────────── */

/** Texto que entra en un momento: tarjetas, líneas, casillas. */
const timedTextSchema = z
  .object({ text: richSchema, at: atSchema, sub: z.string().optional(), accent: accentSchema.optional() })
  .strict();

const textSceneShape = {
  ...sceneBaseShape,
  /** Cuándo entra el titular (por defecto, al empezar la escena). */
  titleAt: atSchema.optional(),
  /** 'previous' = la escena anterior sigue animándose detrás, atenuada. */
  backdrop: z.enum(['none', 'previous']).optional(),
};

export const chapterCardSceneSchema = z
  .object({
    ...textSceneShape,
    type: z.literal('atlas-chapter-card'),
    /** Índice en meta.chapters del capítulo que abre. El numeral sale de ahí. */
    of: z.number().int().min(0),
  })
  .strict();

export const agendaSceneSchema = z
  .object({
    ...textSceneShape,
    type: z.literal('atlas-agenda'),
    /** Un momento por capítulo (meta.chapters): cada numeral entra cuando se nombra. */
    numerals: z.array(atSchema).min(1),
    tagline: z.object({ text: richSchema, at: atSchema }).strict().optional(),
    notes: z.array(z.object({ text: z.string(), at: atSchema, accent: accentSchema.optional() }).strict()).optional(),
  })
  .strict();

export const titleOverlaySceneSchema = z
  .object({ ...textSceneShape, type: z.literal('atlas-title-overlay'), dim: z.number().min(0).max(1).optional() })
  .strict();

export const statementSceneSchema = z.object({ ...textSceneShape, type: z.literal('atlas-statement') }).strict();

export const cardRowSceneSchema = z
  .object({
    ...textSceneShape,
    type: z.literal('atlas-card-row'),
    cards: z
      .array(z.object({ heading: z.string(), text: richSchema, at: atSchema, accent: accentSchema.optional() }).strict())
      .min(1)
      .max(5),
  })
  .strict();

export const checklistSceneSchema = z
  .object({ ...textSceneShape, type: z.literal('atlas-checklist'), items: z.array(timedTextSchema).min(1).max(6) })
  .strict();

export const recapSceneSchema = z
  .object({
    ...textSceneShape,
    type: z.literal('atlas-recap'),
    /** Una tarjeta por capítulo, en el orden de meta.chapters; `text` = frase de ~4 palabras. */
    items: z.array(z.object({ text: z.string(), at: atSchema }).strict()).min(1),
  })
  .strict();

export const ctaSceneSchema = z
  .object({
    ...textSceneShape,
    type: z.literal('atlas-cta'),
    /** 'card' = titular y botón dentro de la tarjeta (mitad del vídeo); 'stack' = botón debajo (cierre). */
    layout: z.enum(['card', 'stack']),
    button: z
      .object({
        label: z.string(),
        at: atSchema.optional(),
        /** Texto tras el clic y momento del clic: el botón pasa a oscuro. */
        doneLabel: z.string().optional(),
        clickAt: atSchema.optional(),
      })
      .strict(),
  })
  .strict();

/* ── Fase 2: gráficos sin geografía ─────────────────────────────────────── */

/** Línea mono que entra en un momento (subtítulos, pies). */
const timedNoteSchema = z.object({ text: z.string(), at: atSchema, accent: accentSchema.optional() }).strict();

export const dialSceneSchema = z
  .object({
    ...textSceneShape,
    type: z.literal('atlas-dial'),
    dial: z
      .object({
        /** Valor de la vuelta completa (60 = un minuto). */
        max: z.number().positive(),
        from: z.number().min(0),
        to: z.number().min(0),
        at: atSchema,
        seconds: z.number().positive(),
        /** 'remaining' = el sector es lo que queda y se vacía; 'elapsed' = lo recorrido y se llena. */
        fill: z.enum(['remaining', 'elapsed']),
        accent: accentSchema,
        hand: z.boolean().optional(),
      })
      .strict(),
    /** Texto bajo la esfera; `{value}` se sustituye por la cifra que cuenta. */
    readout: z.object({ text: richSchema, style: z.enum(['mono', 'serif']), at: atSchema.optional() }).strict(),
  })
  .strict();

const barSchema = z
  .object({
    label: z.string(),
    value: z.number(),
    /** Cifra en pantalla ("~4.1 km"); sus números cuentan mientras la barra crece. */
    display: z.string(),
    at: atSchema,
    style: z.enum(['earth', 'hatched']),
    valueAccent: accentSchema.optional(),
    /** Texto mono dentro de la barra ("MOSTLY ICE"). */
    inside: z.string().optional(),
  })
  .strict();

export const barCompareSceneSchema = z
  .object({
    ...textSceneShape,
    type: z.literal('atlas-bar-compare'),
    axis: z
      .object({
        max: z.number().positive(),
        step: z.number().positive(),
        /** Etiquetas del eje: "{v} KM". */
        format: z.string(),
        style: z.enum(['grid', 'ticks']),
        base: z.string().optional(),
      })
      .strict(),
    /** 'below' = nombre en cursiva bajo el eje y cifra grande encima; 'above' = nombre y cifra mono encima. */
    labels: z.enum(['below', 'above']),
    bars: z.array(barSchema).min(1).max(4),
    ghost: z.object({ bar: z.number().int().min(0), value: z.number(), label: z.string(), at: atSchema }).strict().optional(),
    threshold: z
      .object({ value: z.number(), label: z.string(), at: atSchema, accent: accentSchema, band: z.boolean().optional() })
      .strict()
      .optional(),
    side: z.object({ kicker: z.string(), items: z.array(z.string()).min(1), at: atSchema }).strict().optional(),
  })
  .strict();

export const dotDensitySceneSchema = z
  .object({
    ...textSceneShape,
    type: z.literal('atlas-dot-density'),
    /** Puntos por lado de cada caja (9 → 81 puntos). */
    grid: z.number().int().min(4).max(16),
    boxes: z
      .array(
        z
          .object({ label: z.string(), percent: z.number().min(0).max(100), display: z.string(), at: atSchema, accent: accentSchema.optional() })
          .strict(),
      )
      .min(1)
      .max(3),
  })
  .strict();

export const runwayCompareSceneSchema = z
  .object({
    ...textSceneShape,
    type: z.literal('atlas-runway-compare'),
    notes: z.array(timedNoteSchema).optional(),
    runways: z
      .array(
        z
          .object({
            label: z.string(),
            /** Punto de despegue como fracción de la pista (0–1). */
            liftoff: z.number().min(0.05).max(1),
            at: atSchema,
            /** Segundos hasta el despegue. */
            seconds: z.number().positive(),
            liftoffLabel: z.string().optional(),
          })
          .strict(),
      )
      .min(1)
      .max(3),
    footer: timedNoteSchema.optional(),
  })
  .strict();

/* ── Fase 4: perfiles de altitud ───────────────────────────────────────────── */

/** Punto de una trayectoria: x = fracción del perfil (0–1), altitud en pies; `curve` = cómo se llega a él. */
const flightPointSchema = z
  .object({ x: z.number().min(0).max(1), ft: z.number().min(0), curve: z.enum(['ease', 'linear', 'step']).optional() })
  .strict();

export const elevationProfileSceneSchema = z
  .object({
    ...sceneBaseShape,
    type: z.literal('atlas-elevation-profile'),
    /** JSON de build-profile (ruta relativa a public/). */
    profile: z.string(),
    /** Eje vertical. `unit` 'm' = todas las alturas de la escena (maxFt, stepFt, ft…) en metros; 'ft' (por defecto) en pies. */
    axis: z.object({ maxFt: z.number().positive(), stepFt: z.number().positive(), km: z.boolean().optional(), unit: z.enum(['ft', 'm']).optional() }).strict(),
    /** Extremos del eje x y texto central; `{km}` se sustituye por la distancia real del perfil. */
    ends: z.object({ left: z.string(), right: z.string(), middle: z.string().optional() }).strict(),
    /** Terreno del perfil: 'terrain' (datos) o 'sea' (mar abierto); `swap` lo cambia en vivo. */
    ground: z.enum(['terrain', 'sea']),
    groundAt: atSchema.optional(),
    swap: z.object({ to: z.enum(['terrain', 'sea']), at: atSchema, label: z.string().optional() }).strict().optional(),
    /** Rótulo bajo la línea de mar cuando el terreno es mar abierto («open sea», «mar abierto»). */
    seaLabel: z.string().optional(),
    flight: z
      .object({
        points: z.array(flightPointSchema).min(2),
        at: atSchema,
        drawSeconds: z.number().positive(),
        accent: accentSchema,
        plane: z.boolean().optional(),
        /** Recorta la trayectoria por debajo de la altitud mínima segura (el descenso se detiene en ella). */
        stopAtMsa: z.boolean().optional(),
      })
      .strict()
      .optional(),
    /** Altitud mínima segura escalonada, calculada del propio perfil: máximo por tramo + margen, redondeado a 100 ft. */
    msa: z
      .object({ at: atSchema, label: z.string(), segmentKm: z.number().positive(), marginFt: z.number().min(0), accent: accentSchema.optional() })
      .strict()
      .optional(),
    /** Línea paralela al terreno (p. ej. «al menos 2.000 ft por encima de las montañas»). */
    clearance: z.object({ ft: z.number().positive(), label: z.string(), at: atSchema, accent: accentSchema.optional() }).strict().optional(),
    thresholds: z
      .array(z.object({ ft: z.number().min(0), label: z.string(), at: atSchema, accent: accentSchema, labelSide: z.enum(['left', 'right']).optional() }).strict())
      .optional(),
    bands: z
      .array(z.object({ fromFt: z.number(), toFt: z.number(), label: z.string(), at: atSchema, accent: accentSchema.optional() }).strict())
      .optional(),
    /** Tramos donde la trayectoria queda por debajo de la MSA, rellenos en rojo. */
    violations: z.object({ at: atSchema, label: z.string().optional() }).strict().optional(),
    markers: z
      .array(z.object({ x: z.number().min(0).max(1), label: z.string(), at: atSchema, accent: accentSchema, line: z.enum(['full', 'tick']).optional() }).strict())
      .optional(),
    notes: z
      .array(z.object({ text: z.string(), x: z.number().min(0).max(1), ft: z.number(), at: atSchema, accent: accentSchema.optional() }).strict())
      .optional(),
  })
  .strict();


/* ── Accidentes aéreos (prompts/accidentes-plan.md): vuelo real reproducido desde vuelo.json ─────────────────── */

/** Hora local del vuelo, como en el informe: "15:27:11" (décimas opcionales). */
export const clockSchema = z.string().regex(/^\d{2}:\d{2}:\d{2}(\.\d+)?$/, 'hora hh:mm:ss');

/**
 * Reproducción de un vuelo: desde `at` el reloj del vuelo corre de `from` a `to` a `rate` segundos de vuelo por
 * segundo de vídeo (1 = tiempo real) y se queda en `to`. Los datos (public/<data>) los genera
 * scripts/accidentes/vuelo.py desde la tabla del FDR, con su fuente.
 */
export const flightPlaybackSchema = z
  .object({
    data: z.string(),
    at: atSchema,
    from: clockSchema,
    to: clockSchema,
    rate: z.number().positive().optional(),
  })
  .strict();
export type FlightPlayback = z.infer<typeof flightPlaybackSchema>;

/** Hito sobre la trayectoria: aparece cuando el reloj del vuelo llega a su hora. */
export const flightMarkSchema = z
  .object({ clock: clockSchema, label: z.string(), sub: z.string().optional(), accent: accentSchema.optional() })
  .strict();

/** Instrumentos en pantalla, leídos de los datos en cada fotograma. */
export const flightHudSchema = z
  .object({
    show: z.array(z.enum(['clock', 'alt', 'kias', 'n1'])).min(1),
    corner: cornerSchema.optional(),
    /** Rótulos de cada instrumento en el idioma del vídeo (por defecto: HORA, ALTITUD, VELOCIDAD, MOTORES). */
    labels: z.object({ clock: z.string(), alt: z.string(), kias: z.string(), n1: z.string() }).partial().strict().optional(),
  })
  .strict();

const flightLayerSchema = flightPlaybackSchema
  .extend({
    accent: accentSchema.optional(),
    /** 'flown' = la estela crece con el avión; 'full' = la ruta entera en tenue y la volada encima. */
    trail: z.enum(['flown', 'full']).optional(),
    marks: z.array(flightMarkSchema).optional(),
    hud: flightHudSchema.optional(),
  })
  .strict();

export const reliefMapSceneSchema = z
  .object({
    ...sceneBaseShape,
    type: z.literal('atlas-relief-map'),
    /** Paquete en public/atlas-data/regions/<region>. */
    region: z.string(),
    camera: z.array(z.object({ at: atSchema, center: lonLatSchema, zoom: z.number().positive() }).strict()).min(1),
    shapes: z
      .array(
        z
          .object({
            id: z.string(),
            /** Ruta a GeoJSON generado, relativa a public/. */
            source: z.string(),
            at: atSchema,
            stroke: accentSchema.optional(),
            fill: z.boolean().optional(),
            label: z.string().optional(),
            sub: z.string().optional(),
            /** Silueta trasladada a escala (centroide → este punto). */
            moveTo: lonLatSchema.optional(),
          })
          .strict(),
      )
      .optional(),
    routes: z
      .array(
        z
          .object({
            id: z.string(),
            path: z.array(lonLatSchema).min(2),
            at: atSchema,
            drawSeconds: z.number().positive(),
            style: z.enum(['solid', 'dashed', 'dotted']),
            accent: accentSchema,
            label: z.string().optional(),
            icon: z.literal('plane').optional(),
            greatCircle: z.boolean().optional(),
          })
          .strict(),
      )
      .optional(),
    points: z
      .array(
        z
          .object({
            name: z.string(),
            at: atSchema,
            pos: lonLatSchema,
            value: z.string().optional(),
            marker: z.enum(['city', 'airport', 'event']),
            accent: accentSchema.optional(),
          })
          .strict(),
      )
      .optional(),
    labels: z
      .array(
        z
          .object({
            text: z.string(),
            at: atSchema,
            pos: lonLatSchema,
            style: z.enum(['region', 'mono']),
            accent: accentSchema.optional(),
          })
          .strict(),
      )
      .optional(),
    arrows: z
      .array(z.object({ from: lonLatSchema, to: lonLatSchema, at: atSchema, accent: accentSchema }).strict())
      .optional(),
    graticule: z
      .object({
        at: atSchema,
        /** JSON de build-cells (ruta relativa a public/). */
        cells: z.string(),
        /** Margen sobre el punto más alto de cada celda, en pies (la MSA se redondea hacia arriba a 100 ft). */
        marginFt: z.number().min(0),
        /** Cuándo aparecen las cifras de cada celda. */
        numbersAt: atSchema.optional(),
        /** Celdas con MSA ≥ value (pies) en rojo; `fill` las rellena. */
        threshold: z.object({ value: z.number(), at: atSchema, fill: z.boolean().optional() }).strict().optional(),
        highlight: lonLatSchema.optional(),
      })
      .strict()
      .optional(),
    /** Vuelo real que se dibuja mientras su reloj avanza (avión orientado, hitos, instrumentos). */
    flight: flightLayerSchema
      .extend({ /** La cámara sigue al avión (con el zoom del keyframe vigente). */ follow: z.boolean().optional() })
      .strict()
      .optional(),
  })
  .strict();

/* ── Fase 5: globo y terreno 3D ────────────────────────────────────────────── */

/** Globo ortográfico (three.js) con textura del mundo y las mismas capas vectoriales que el mapa de relieve. */
export const globeSceneSchema = z
  .object({
    ...sceneBaseShape,
    type: z.literal('atlas-globe'),
    /** zoom 1 = el globo entero con margen; 3 ≈ un continente llena la pantalla. */
    camera: reliefMapSceneSchema.shape.camera,
    shapes: reliefMapSceneSchema.shape.shapes,
    routes: reliefMapSceneSchema.shape.routes,
    points: reliefMapSceneSchema.shape.points,
    labels: reliefMapSceneSchema.shape.labels,
  })
  .strict();

const tiltKeySchema = z
  .object({
    at: atSchema,
    /** Grados sobre el horizonte: 90 = cenital, 0 = rasante. */
    tilt: z.number().min(2).max(89.5),
    /** Grados de giro alrededor del bloque: 0 = mirando hacia el norte desde el sur. */
    yaw: z.number(),
    /** Distancia de la cámara en múltiplos del lado mayor del bloque. */
    distance: z.number().positive(),
    /** Punto mirado, en lon/lat (por defecto el centro del bloque). */
    target: lonLatSchema.optional(),
    /** Altura del punto mirado, en km reales. */
    targetKm: z.number().optional(),
  })
  .strict();

export const terrain3dSceneSchema = z
  .object({
    ...sceneBaseShape,
    type: z.literal('atlas-terrain-3d'),
    /** Bloque en public/atlas-data/terrain/<terrain>. */
    terrain: z.string(),
    /** Exageración vertical (1 = escala real). */
    exaggeration: z.number().positive(),
    /** El mapa plano se extruye hasta su altura en este momento (si falta, ya está extruido). */
    extrude: z.object({ at: atSchema, seconds: z.number().positive() }).strict().optional(),
    camera: z.array(tiltKeySchema).min(1),
    threshold: z
      .object({ m: z.number(), at: atSchema, accent: accentSchema.optional(), label: z.string().optional(), labelPos: lonLatSchema.optional() })
      .strict()
      .optional(),
    labels: z
      .array(
        z
          .object({
            text: z.string(),
            pos: lonLatSchema,
            at: atSchema,
            /** 'range' = nombre de cordillera sobre el terreno; 'peak' = punto con línea guía; 'value' = cifra mono. */
            style: z.enum(['range', 'peak', 'value']),
            sub: z.string().optional(),
            accent: accentSchema.optional(),
          })
          .strict(),
      )
      .optional(),
    /** Línea horizontal a una altitud (p. ej. crucero de los aviones), de lado a lado. */
    cruise: z.object({ km: z.number().positive(), label: z.string(), at: atSchema, accent: accentSchema.optional() }).strict().optional(),
    /** Avión que cruza a una altitud, con línea vertical hasta el suelo. */
    plane: z
      .object({
        from: lonLatSchema,
        to: lonLatSchema,
        km: z.number().positive(),
        at: atSchema,
        seconds: z.number().positive(),
        dropLine: z.boolean().optional(),
        accent: accentSchema.optional(),
        trail: z.boolean().optional(),
      })
      .strict()
      .optional(),
    /** Eje vertical en km a la derecha del bloque. */
    axis: z.object({ maxKm: z.number().positive(), stepKm: z.number().positive(), at: atSchema }).strict().optional(),
    /** Rótulo en la base del bloque («SEA LEVEL»). */
    base: z.object({ label: z.string(), at: atSchema }).strict().optional(),
    /** Vuelo real sobre el terreno: trayectoria en el aire con la misma exageración vertical, línea al suelo. */
    flight: flightLayerSchema.extend({ dropLines: z.boolean().optional() }).strict().optional(),
  })
  .strict();

/** Perfil de un vuelo real en el tiempo: altitud (con el terreno debajo), velocidad o motores. */
export const flightProfileSceneSchema = z
  .object({
    ...sceneBaseShape,
    type: z.literal('atlas-flight-profile'),
    flight: flightPlaybackSchema,
    /** Qué se dibuja: altitud (ft), velocidad indicada (kt) o N1 de los dos motores (%). */
    series: z.enum(['alt', 'kias', 'n1']),
    axis: z.object({ max: z.number().positive(), step: z.number().positive(), unit: z.string() }).strict(),
    /** Terreno bajo la trayectoria (solo con series 'alt'; necesita `ground` en vuelo.json: accidentes:data suelo). */
    terrain: z.boolean().optional(),
    marks: z.array(flightMarkSchema).optional(),
    /** Líneas horizontales de referencia («300 kt para reencender»). */
    refs: z.array(z.object({ value: z.number(), label: z.string(), at: atSchema, accent: accentSchema.optional() }).strict()).optional(),
    /** Rótulos de las dos series de N1 («MOTOR 1», «MOTOR 2»). */
    legend: z.tuple([z.string(), z.string()]).optional(),
  })
  .strict();

/** Cabina en texto: reloj, frases del informe a su hora e instrumentos leídos de los datos. */
export const cockpitSceneSchema = z
  .object({
    ...sceneBaseShape,
    type: z.literal('atlas-cockpit'),
    flight: flightPlaybackSchema,
    /** Frases citadas del informe (traducidas si hace falta), a la hora en que se dijeron. */
    lines: z
      .array(z.object({ clock: clockSchema, who: z.string(), text: z.string(), ref: z.string(), accent: accentSchema.optional() }).strict())
      .min(1),
    instruments: z.array(z.enum(['alt', 'kias', 'n1'])).min(1),
    labels: flightHudSchema.shape.labels,
    /** Cuántas frases caben a la vez (las más viejas se van). */
    visible: z.number().int().min(1).max(8).optional(),
  })
  .strict();

/** PFD (pantalla principal de vuelo) dibujado con los datos: horizonte artificial, cintas de velocidad y altitud, rumbo. */
export const pfdOverlaySchema = z
  .object({
    at: atSchema,
    corner: cornerSchema,
    /** Ancho en px (por defecto 520). */
    size: z.number().min(280).max(900).optional(),
  })
  .strict();

/**
 * Vista 3D de cerca de un vuelo real a escala real: el avión (modelo dibujado en código, con el cabeceo, el alabeo y el
 * rumbo del FDR) sobre el bloque de terreno, con cámaras que cambian por keyframes.
 *   chase  = detrás y por encima del avión     side   = al lado, a la altura del avión
 *   ground = desde un punto fijo del suelo      cockpit = desde el asiento del piloto, con el horizonte que se inclina
 *   orbit  = girando alrededor del avión
 */
export const flightCamSceneSchema = z
  .object({
    ...sceneBaseShape,
    type: z.literal('atlas-flight-cam'),
    terrain: z.string(),
    flight: flightPlaybackSchema,
    model: z.enum(['narrowbody', 'bizjet']),
    camera: z
      .array(
        z
          .object({
            at: atSchema,
            mode: z.enum(['chase', 'side', 'ground', 'cockpit', 'orbit']),
            /** Distancia al avión en metros (chase, side, orbit). */
            distanceM: z.number().positive().optional(),
            /** Altura sobre el avión en metros (chase, side, orbit); sobre el suelo (ground). */
            heightM: z.number().optional(),
            /** ground: punto del suelo desde el que se mira. */
            pos: lonLatSchema.optional(),
            /** Ángulo de visión vertical en grados (por defecto 40; menos = teleobjetivo). */
            fov: z.number().min(5).max(90).optional(),
            /** side: true = lado izquierdo del avión. orbit: grados por segundo. */
            left: z.boolean().optional(),
            degPerSecond: z.number().optional(),
          })
          .strict(),
      )
      .min(1),
    pfd: pfdOverlaySchema.optional(),
    hud: flightHudSchema.optional(),
    /** Marco de la cabina (parabrisas y panel) en la vista cockpit. */
    cockpitFrame: z.boolean().optional(),
  })
  .strict();

/** El PFD a pantalla completa (o grande) leyendo un vuelo real, con las frases del informe opcionales al lado. */
export const pfdSceneSchema = z
  .object({
    ...sceneBaseShape,
    type: z.literal('atlas-pfd'),
    flight: flightPlaybackSchema,
    size: z.number().min(400).max(1000).optional(),
    lines: cockpitSceneSchema.shape.lines.optional(),
  })
  .strict();

/** Silueta de avión con piezas resaltadas (motores, timón de profundidad…). */
export const aircraftSceneSchema = z
  .object({
    ...sceneBaseShape,
    type: z.literal('atlas-aircraft'),
    model: z.enum(['narrowbody', 'bizjet']),
    view: z.enum(['top', 'side']),
    highlights: z
      .array(
        z
          .object({
            part: z.enum(['engines', 'engine-left', 'engine-right', 'wings', 'flaps', 'tail', 'elevator', 'rudder', 'nose', 'gear', 'fuselage']),
            at: atSchema,
            accent: accentSchema.optional(),
            label: z.string().optional(),
            sub: z.string().optional(),
          })
          .strict(),
      )
      .optional(),
  })
  .strict();

/** «Lo que se sabe»: cada dato con su estado y su fuente, a la hora de la última actualización. */
export const knownSceneSchema = z
  .object({
    ...textSceneShape,
    type: z.literal('atlas-known'),
    /** «Actualizado: 15 ene 2009, 18:00». */
    asOf: z.string(),
    items: z
      .array(
        z
          .object({
            status: z.enum(['confirmed', 'unconfirmed', 'unknown']),
            text: richSchema,
            source: z.string(),
            at: atSchema,
          })
          .strict(),
      )
      .min(1)
      .max(6),
    /** Rótulos de los estados en el idioma del vídeo. */
    statusLabels: z.object({ confirmed: z.string(), unconfirmed: z.string(), unknown: z.string() }).strict().optional(),
  })
  .strict();

/* ── Fase 6: diagramas ──────────────────────────────────────────────────────── */

/** Color de una capa: un acento del tema o un relleno de la paleta de dibujo. */
const layerColorSchema = z.union([accentSchema, z.enum(['paper', 'earth', 'glass', 'grey', 'amber', 'none'])]);
const pointSchema = z.tuple([z.number(), z.number()]);

export const diagramSceneSchema = z
  .object({
    ...sceneBaseShape,
    type: z.literal('atlas-diagram'),
    /** SVG en public/ con un id por capa (ver public/atlas-diagrams/*.svg y docs/atlas-authoring.md). */
    diagram: z.string(),
    /** Rectángulo de pantalla (px) donde cabe el dibujo; por defecto, bajo el titular. */
    box: z.object({ x: z.number(), y: z.number(), w: z.number().positive(), h: z.number().positive() }).strict().optional(),
    /** Cambios de estado de capas: cada uno anima desde el estado anterior de esa capa. */
    states: z
      .array(
        z
          .object({
            layer: z.string(),
            at: atSchema,
            opacity: z.number().min(0).max(1).optional(),
            fill: layerColorSchema.optional(),
            stroke: layerColorSchema.optional(),
            dashed: z.boolean().optional(),
            /** Desplazamiento en unidades del SVG. */
            x: z.number().optional(),
            y: z.number().optional(),
            rotate: z.number().optional(),
            scale: z.number().positive().optional(),
            seconds: z.number().positive().optional(),
          })
          .strict(),
      )
      .optional(),
    /** Llamadas: línea guía desde un punto del dibujo hasta el texto (coordenadas del SVG). */
    callouts: z
      .array(
        z
          .object({
            text: z.string(),
            sub: z.string().optional(),
            at: atSchema,
            anchor: pointSchema.optional(),
            label: pointSchema,
            align: z.enum(['left', 'right', 'center']).optional(),
            accent: accentSchema.optional(),
            size: z.number().positive().optional(),
          })
          .strict(),
      )
      .optional(),
    /** Barras que se llenan o se vacían (tiempo de oxígeno…), en px de pantalla. */
    meters: z
      .array(
        z
          .object({
            label: z.string(),
            at: atSchema,
            from: z.number().min(0).max(1),
            to: z.number().min(0).max(1),
            seconds: z.number().positive(),
            x: z.number(),
            y: z.number(),
            w: z.number().positive(),
            accent: accentSchema.optional(),
          })
          .strict(),
      )
      .optional(),
  })
  .strict();

/**
 * Registro de esquemas de escena. Cada fase añade aquí los suyos.
 * La clave `type` debe coincidir con la del registro de componentes (scenes/index.ts).
 */
export const sceneSchema = z.discriminatedUnion('type', [
  blankSceneSchema,
  chapterCardSceneSchema,
  agendaSceneSchema,
  titleOverlaySceneSchema,
  statementSceneSchema,
  cardRowSceneSchema,
  checklistSceneSchema,
  recapSceneSchema,
  ctaSceneSchema,
  dialSceneSchema,
  barCompareSceneSchema,
  dotDensitySceneSchema,
  runwayCompareSceneSchema,
  elevationProfileSceneSchema,
  reliefMapSceneSchema,
  globeSceneSchema,
  terrain3dSceneSchema,
  diagramSceneSchema,
  flightProfileSceneSchema,
  cockpitSceneSchema,
  aircraftSceneSchema,
  knownSceneSchema,
  flightCamSceneSchema,
  pfdSceneSchema,
]);
export type AtlasScene = z.infer<typeof sceneSchema>;
export type SceneType = AtlasScene['type'];

const storyboardShape = {
    meta: z
      .object({
        slug: z.string().regex(/^[a-z0-9-]+$/, 'sólo minúsculas, números y guiones'),
        title: z.string(),
        brand: z.object({ name: z.string(), icon: z.string() }).strict(),
        chapters: z.array(z.object({ numeral: z.string(), label: z.string() }).strict()),
        /** Duración total en segundos. Si falta, se toma de la duración de `audio.voice`. */
        duration: z.number().positive().optional(),
        /** Versión vertical (composición AtlasShort, 1080×1920): titular arriba y pie abajo del vídeo. */
        short: z.object({ top: richSchema, bottom: z.string().optional() }).strict().optional(),
      })
      .strict(),
    audio: z
      .object({
        /** Rutas relativas a public/. `voice` puede faltar en borradores mudos. */
        voice: z.string().optional(),
        music: z.string().optional(),
        /** JSON de pipeline/transcribe.py ({ words: [{word,start,end}] }). Necesario si hay anclas `say`. */
        transcript: z.string().optional(),
      })
      .strict(),
    scenes: z.array(sceneSchema).min(1, 'scenes: el storyboard necesita al menos una escena'),
};

export const storyboardSchema = z
  .object(storyboardShape)
  .strict()
  .superRefine((sb, ctx) => {
    const ids = new Set<string>();
    sb.scenes.forEach((scene, i) => {
      if (ids.has(scene.id)) {
        ctx.addIssue({ code: 'custom', path: ['scenes', i, 'id'], message: `id de escena repetido: "${scene.id}"` });
      }
      ids.add(scene.id);
      const n = sb.meta.chapters.length;
      if (scene.type === 'atlas-chapter-card' && scene.of >= n) {
        ctx.addIssue({ code: 'custom', path: ['scenes', i, 'of'], message: `capítulo ${scene.of} no existe (meta.chapters tiene ${n})` });
      }
      if (scene.type === 'atlas-agenda' && scene.numerals.length !== n) {
        ctx.addIssue({ code: 'custom', path: ['scenes', i, 'numerals'], message: `hacen falta ${n} momentos, uno por capítulo` });
      }
      if (scene.type === 'atlas-recap' && scene.items.length !== n) {
        ctx.addIssue({ code: 'custom', path: ['scenes', i, 'items'], message: `hacen falta ${n} tarjetas, una por capítulo` });
      }
      if (scene.type === 'atlas-bar-compare' && scene.ghost && scene.ghost.bar >= scene.bars.length) {
        ctx.addIssue({ code: 'custom', path: ['scenes', i, 'ghost', 'bar'], message: `la barra ${scene.ghost.bar} no existe` });
      }
      if (scene.chapter !== undefined && scene.chapter >= sb.meta.chapters.length) {
        ctx.addIssue({
          code: 'custom',
          path: ['scenes', i, 'chapter'],
          message: `capítulo ${scene.chapter} no existe (meta.chapters tiene ${sb.meta.chapters.length})`,
        });
      }
    });
  });

export type AtlasStoryboard = z.infer<typeof storyboardSchema>;

/** Esquema de props de la composición: el storyboard más lo que añade calculateMetadata. */
export const atlasCompositionSchema = z
  .object({ ...storyboardShape, resolvedDuration: z.number().optional() })
  .strict();

/** Convierte un error de zod en un mensaje legible con la ruta de cada problema. */
export const formatStoryboardError = (error: z.ZodError): string =>
  // Una sola línea: Remotion sólo enseña la primera línea del mensaje de error.
  'Storyboard inválido — ' +
  error.issues.map((issue) => `${issue.path.length ? issue.path.join('.') : '(raíz)'}: ${issue.message}`).join(' · ');

export const parseStoryboard = (input: unknown): AtlasStoryboard => {
  const result = storyboardSchema.safeParse(input);
  if (!result.success) {
    throw new Error(formatStoryboardError(result.error));
  }
  return result.data;
};
