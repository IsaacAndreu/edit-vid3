/**
 * Esquema del storyboard Atlas (prompts/atlas-plan.md §4).
 * Contrato único entre quien escribe el vídeo y quien lo renderiza.
 *
 * Convenciones: todo lo que aparece lleva `at: At`; colores sólo por `Accent`;
 * textos sólo por `Rich` o string; geografía sólo por `LonLat` o ruta a un archivo generado.
 */
import { z } from 'zod';

export const accentSchema = z.enum(['danger', 'data', 'good', 'amber']);
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
        cells: z.string(),
        threshold: z.object({ value: z.number(), at: atSchema }).strict().optional(),
        highlight: lonLatSchema.optional(),
      })
      .strict()
      .optional(),
  })
  .strict();

/**
 * Registro de esquemas de escena. Cada fase añade aquí los suyos.
 * La clave `type` debe coincidir con la del registro de componentes (scenes/index.ts).
 */
export const sceneSchema = z.discriminatedUnion('type', [blankSceneSchema, reliefMapSceneSchema]);
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
