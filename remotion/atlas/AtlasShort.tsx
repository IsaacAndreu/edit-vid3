/**
 * Versión vertical de un storyboard Atlas (1080×1920, Shorts): el vídeo 16:9 entero a 0,5625 en el centro, con el
 * titular de meta.short.top arriba y meta.short.bottom abajo. Mismo storyboard, mismos anclajes y misma voz.
 */
import type { FC } from 'react';
import { AbsoluteFill } from 'remotion';
import { AtlasVideo, type AtlasVideoProps } from './AtlasVideo';
import { fonts } from './fonts';
import { themes } from './theme';
import { Mono, RichTitle } from './ui';

export const SHORT = { width: 1080, height: 1920 } as const;
const SCALE = SHORT.width / 1920;
const VIDEO_H = 1080 * SCALE;
const VIDEO_TOP = Math.round((SHORT.height - VIDEO_H) / 2);

export const AtlasShort: FC<AtlasVideoProps> = (props) => {
  const theme = props.scenes[0]?.theme ?? 'paper';
  const t = themes[theme];
  const short = props.meta.short;
  return (
    <AbsoluteFill style={{ backgroundColor: t.bg }}>
      <div style={{ position: 'absolute', top: 150, left: 70, right: 70, textAlign: 'center' }}>
        <Mono size={28} color={t.ink}>{`${props.meta.brand.icon} ${props.meta.brand.name}`}</Mono>
        {short ? (
          <div style={{ marginTop: 60 }}>
            <RichTitle rich={short.top} theme={theme} size={78} style={{ lineHeight: 1.12, whiteSpace: 'normal' }} />
          </div>
        ) : null}
      </div>
      <div style={{ position: 'absolute', top: VIDEO_TOP, left: 0, width: SHORT.width, height: VIDEO_H, overflow: 'hidden', borderTop: `2px solid ${t.ink}`, borderBottom: `2px solid ${t.ink}` }}>
        <div style={{ width: 1920, height: 1080, transform: `scale(${SCALE})`, transformOrigin: '0 0' }}>
          <AtlasVideo {...props} />
        </div>
      </div>
      {short?.bottom ? (
        <div style={{ position: 'absolute', top: VIDEO_TOP + VIDEO_H + 70, left: 90, right: 90, textAlign: 'center', fontFamily: fonts.mono, fontSize: 26, letterSpacing: '0.14em', color: t.inkSoft, textTransform: 'uppercase', lineHeight: 1.5 }}>
          {short.bottom}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};
