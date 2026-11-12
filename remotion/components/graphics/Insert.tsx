import type { FC } from 'react';
import { AbsoluteFill, Img, OffthreadVideo, interpolate, staticFile, useCurrentFrame } from 'remotion';
import { templates } from '../../../templates/registry';
import type { SceneProps } from '../../../templates/types';
import { theme } from '../../theme';
import type { ClipGraphic, SceneGraphic } from '../../graphics';

const media = (src?: string | null) => (!src ? undefined : /^(https?:|data:|blob:)/i.test(src) ? src : staticFile(src));

/**
 * A ready-made scene from templates/ (title card, number callout, comparison, timeline…) inserted from the editor's
 * «Recursos»: drawn full frame over the footage with its own props, in the channel's accent colour unless one is set.
 */
export const SceneInsert: FC<{ graphic: SceneGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const Template = templates[graphic.template] ?? templates.placeholder;
  const props: SceneProps = {
    sceneType: graphic.sceneType ?? 'narrative', durationInFrames, accentColor: graphic.accentColor || theme.accent,
    text: graphic.text ?? undefined, keywords: graphic.keywords ?? undefined, timelinePoints: graphic.timelinePoints ?? undefined,
    comparisonColumns: graphic.comparisonColumns ?? undefined, imageUrl: media(graphic.imageUrl), videoUrl: media(graphic.videoUrl),
  };
  return <AbsoluteFill><Template {...props} /></AbsoluteFill>;
};

/** A clip or photo of your own over the edit: full frame, or in a window in a corner (picture in picture). */
export const ClipInsert: FC<{ graphic: ClipGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 6, durationInFrames - 6, durationInFrames], [0, 1, 1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const fit = graphic.fit ?? 'cover';
  const body = graphic.kind === 'image'
    ? <Img src={staticFile(graphic.src)} style={{ width: '100%', height: '100%', objectFit: fit }} />
    : <OffthreadVideo src={staticFile(graphic.src)} muted={!graphic.volume} volume={graphic.volume ?? 0} style={{ width: '100%', height: '100%', objectFit: fit }} />;
  if (graphic.place === 'pip') {
    return (
      <AbsoluteFill style={{ opacity }}>
        <div style={{ position: 'absolute', right: 70, bottom: 90, width: '36%', aspectRatio: '16 / 9', borderRadius: 18, overflow: 'hidden',
                      boxShadow: '0 24px 70px rgba(0,0,0,0.6)', border: '4px solid rgba(255,255,255,0.9)', backgroundColor: '#000' }}>{body}</div>
      </AbsoluteFill>
    );
  }
  return <AbsoluteFill style={{ opacity, backgroundColor: '#000' }}>{body}</AbsoluteFill>;
};
