/**
 * Composición AtlasVideo: resuelve tiempos, monta escenas con fundido cruzado y aplica las capas
 * globales. Separada de YoutubeVideo (plan §2.1).
 */
import type { FC } from 'react';
import type { CalculateMetadataFunction } from 'remotion';
import { AbsoluteFill, Audio, Sequence, interpolate, staticFile, useCurrentFrame } from 'remotion';
import { getAudioDurationInSeconds } from '@remotion/media-utils';
import { ease } from './anim';
import { SceneContext } from './context';
import { waitForFonts } from './fonts';
import { Background, Brand, ChapterIndicator, Grain, Vignette } from './layers';
import { OverlayLayer, SourceNote } from './overlays';
import { atlasScenes } from './scenes';
import type { AtlasStoryboard } from './schema';
import { parseStoryboard } from './schema';
import type { Transcript } from './time';
import { resolveStoryboardAnchors, sceneTimings } from './time';
import { VIDEO, themes } from './theme';

export type AtlasVideoProps = AtlasStoryboard & {
  /** Rellenado por calculateMetadata: duración total en segundos ya resuelta. */
  resolvedDuration?: number;
};

const loadTranscript = async (path: string | undefined): Promise<Transcript | null> => {
  if (!path) return null;
  const res = await fetch(staticFile(path));
  if (!res.ok) throw new Error(`No se pudo leer audio.transcript "${path}" (HTTP ${res.status}); debe estar en public/`);
  const json = (await res.json()) as Transcript;
  if (!Array.isArray(json.words)) throw new Error(`audio.transcript "${path}" no tiene "words"`);
  return json;
};

export const calculateAtlasMetadata: CalculateMetadataFunction<AtlasVideoProps> = async ({ props }) => {
  const { resolvedDuration: _ignored, ...raw } = props;
  const storyboard = parseStoryboard(raw);
  const transcript = await loadTranscript(storyboard.audio.transcript);
  const resolved = resolveStoryboardAnchors(storyboard, transcript);
  let duration = resolved.meta.duration;
  if (duration === undefined) {
    if (!resolved.audio.voice) {
      throw new Error('Falta meta.duration y no hay audio.voice del que sacar la duración');
    }
    duration = await getAudioDurationInSeconds(staticFile(resolved.audio.voice));
  }
  sceneTimings(resolved, duration);
  await waitForFonts();
  return {
    durationInFrames: Math.max(1, Math.round(duration * VIDEO.fps)),
    props: { ...resolved, resolvedDuration: duration },
  };
};

const sceneComponent = (type: AtlasStoryboard['scenes'][number]['type'], id: string): FC => {
  const Component = atlasScenes[type];
  if (!Component) throw new Error(`Escena "${id}": el tipo "${type}" todavía no tiene componente`);
  return Component;
};

/**
 * La escena anterior sigue animándose detrás (titular sobre el globo, CTA sobre el terreno).
 * Se monta con su propio contexto y el mismo origen de tiempo que la escena actual.
 */
const Backdrop: FC<{ storyboard: AtlasStoryboard; index: number; origin: number; dim: number }> = ({
  storyboard,
  index,
  origin,
  dim,
}) => {
  const scene = storyboard.scenes[index];
  const Component = sceneComponent(scene.type, scene.id);
  const timings = { start: origin, end: origin };
  return (
    <SceneContext.Provider
      value={{ storyboard, scene, index, ...timings, origin, previous: index > 0 ? storyboard.scenes[index - 1] : null }}
    >
      <Background theme={scene.theme} />
      <Component />
      <OverlayLayer overlays={scene.overlays} />
      <AbsoluteFill style={{ backgroundColor: themes[scene.theme].bg, opacity: dim }} />
    </SceneContext.Provider>
  );
};

const SceneSlot: FC<{
  storyboard: AtlasStoryboard;
  index: number;
  start: number;
  end: number;
  fadeFrames: number;
}> = ({ storyboard, index, start, end, fadeFrames }) => {
  const frame = useCurrentFrame();
  const scene = storyboard.scenes[index];
  const Component = sceneComponent(scene.type, scene.id);
  // 'continuous' hereda la cámara y también se funde: el encuadre coincide, así que sólo se ve desvanecerse lo que
  // cambia (sin el fundido, lo que la escena nueva ya no dibuja desaparecería de golpe)
  const opacity =
    index > 0
      ? interpolate(frame, [0, fadeFrames], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: ease })
      : 1;
  const backdrop = 'backdrop' in scene && scene.backdrop === 'previous' && index > 0;
  const dim = scene.type === 'atlas-title-overlay' ? scene.dim ?? 0.35 : 0.2;
  const dimIn = interpolate(frame, [0, fadeFrames * 2], [0, dim], { extrapolateRight: 'clamp', easing: ease });
  return (
    <SceneContext.Provider
      value={{ storyboard, scene, index, start, end, origin: start, previous: index > 0 ? storyboard.scenes[index - 1] : null }}
    >
      <AbsoluteFill style={{ opacity }}>
        {backdrop ? (
          <Backdrop storyboard={storyboard} index={index - 1} origin={start} dim={dimIn} />
        ) : (
          <Background theme={scene.theme} />
        )}
        <Component />
        {/* La viñeta oscurece el lienzo pero no las tarjetas ni el HUD, como en el original. */}
        <Vignette theme={scene.theme} />
        <OverlayLayer overlays={scene.overlays} />
        <SourceNote />
        <Brand />
        <ChapterIndicator />
      </AbsoluteFill>
    </SceneContext.Provider>
  );
};

export const AtlasVideo: FC<AtlasVideoProps> = ({ resolvedDuration, ...storyboard }) => {
  if (resolvedDuration === undefined) {
    throw new Error('AtlasVideo: los props no pasaron por calculateAtlasMetadata');
  }
  const fps = VIDEO.fps;
  const fadeFrames = Math.round(VIDEO.crossfade * fps);
  const timings = sceneTimings(storyboard, resolvedDuration);
  const total = Math.round(resolvedDuration * fps);
  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      {timings.map((t) => {
        const from = Math.round(t.start * fps);
        const isLast = t.index === timings.length - 1;
        // La escena sigue visible debajo durante el fundido de la siguiente.
        const until = isLast ? total : Math.min(total, Math.round(t.end * fps) + fadeFrames);
        return (
          <Sequence key={storyboard.scenes[t.index].id} from={from} durationInFrames={Math.max(1, until - from)} name={storyboard.scenes[t.index].id}>
            <SceneSlot storyboard={storyboard} index={t.index} start={t.start} end={t.end} fadeFrames={fadeFrames} />
          </Sequence>
        );
      })}
      <Grain />
      {storyboard.audio.voice ? <Audio src={staticFile(storyboard.audio.voice)} /> : null}
      {storyboard.audio.music ? <Audio src={staticFile(storyboard.audio.music)} volume={0.18} /> : null}
    </AbsoluteFill>
  );
};
