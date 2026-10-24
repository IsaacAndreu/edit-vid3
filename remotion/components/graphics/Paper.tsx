import type { CSSProperties, FC, ReactNode } from 'react';
import { AbsoluteFill } from 'remotion';

/** Textures of the paper graphics (search, marker, lens, scroll, news, poster, pinned map): grain, vignette,
 * blurred newsprint, a wooden table, squared paper and a starry night. Deterministic: the same every frame. */

export const rand = (seed: number) => {
  const x = Math.sin(seed * 12.9898 + 78.233) * 43758.5453;
  return x - Math.floor(x);
};

/** Film/paper grain over everything (an SVG noise, no image file). */
export const Grain: FC<{ opacity?: number; id?: string }> = ({ opacity = 0.18, id = 'grain' }) => (
  <svg width="100%" height="100%" style={{ position: 'absolute', inset: 0, opacity, mixBlendMode: 'multiply', pointerEvents: 'none' }}>
    <filter id={id}>
      <feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="3" stitchTiles="stitch" />
      <feColorMatrix type="saturate" values="0" />
    </filter>
    <rect width="100%" height="100%" filter={`url(#${id})`} />
  </svg>
);

/** Darker edges, light in the middle: the «studio light» of the reference graphics. */
export const Vignette: FC<{ strength?: number; color?: string }> = ({ strength = 0.55, color = '0,0,0' }) => (
  <AbsoluteFill
    style={{ background: `radial-gradient(ellipse 62% 58% at 50% 48%, rgba(${color},0) 40%, rgba(${color},${strength}) 100%)`, pointerEvents: 'none' }}
  />
);

const WORDS = ('después noticia durante también entre cuando mañana ciudad semana según informe consejo para sobre ' +
  'pueblo nación público trabajo gobierno durante desde hasta como pero porque luego entonces mientras siempre ' +
  'tarde noche hombre mujer partido equipo campeón jornada estadio victoria derrota final temporada').split(' ');

const column = (seed: number, lines: number) =>
  Array.from({ length: lines }, (_, i) =>
    Array.from({ length: 6 + Math.floor(rand(seed + i) * 3) }, (_, j) => WORDS[Math.floor(rand(seed * 31 + i * 7 + j) * WORDS.length)]).join(' '),
  );

/** An old newspaper page, out of focus: columns of small serif text and a few headings. */
export const Newsprint: FC<{ blur?: number; tone?: string; children?: ReactNode }> = ({ blur = 2.6, tone = '#d8d2c4', children }) => {
  const heads = ['CRISIS EN EL PUERTO', 'LA COSECHA', 'ÚLTIMA HORA', 'EL CONSEJO DECIDE', 'CRÓNICA'];
  const text: CSSProperties = { fontFamily: "'DM Serif Display', Georgia, serif", fontSize: 22, lineHeight: 1.28, color: '#2b2924', textAlign: 'justify' };
  return (
    <AbsoluteFill style={{ backgroundColor: tone, overflow: 'hidden' }}>
      <div style={{ position: 'absolute', inset: -40, display: 'flex', gap: 34, padding: 30, filter: `blur(${blur}px)`, opacity: 0.85 }}>
        {[0, 1, 2, 3, 4].map((c) => (
          <div key={c} style={{ flex: 1, ...text }}>
            {[0, 1, 2].map((b) => (
              <div key={b} style={{ marginBottom: 26 }}>
                {rand(c * 5 + b) > 0.45 ? (
                  <div style={{ fontFamily: "'Oswald'", fontWeight: 700, fontSize: 30, marginBottom: 8 }}>{heads[(c + b) % heads.length]}</div>
                ) : null}
                {column(c * 13 + b, 9).map((line, i) => (
                  <div key={i}>{line}</div>
                ))}
              </div>
            ))}
          </div>
        ))}
      </div>
      <AbsoluteFill style={{ background: 'radial-gradient(ellipse at 30% 20%, rgba(120,100,60,0.18), rgba(0,0,0,0) 60%)' }} />
      {children}
    </AbsoluteFill>
  );
};

/** A dark wooden table: planks and their grain. */
export const Wood: FC = () => (
  <AbsoluteFill
    style={{
      backgroundColor: '#3b2a1c',
      backgroundImage: [
        'repeating-linear-gradient(90deg, rgba(0,0,0,0.0) 0px, rgba(0,0,0,0.0) 316px, rgba(0,0,0,0.45) 318px, rgba(0,0,0,0.0) 322px)',
        'repeating-linear-gradient(90deg, rgba(255,220,170,0.035) 0px, rgba(0,0,0,0.05) 3px, rgba(255,220,170,0.02) 7px, rgba(0,0,0,0.06) 11px)',
        'radial-gradient(ellipse at 50% 35%, rgba(150,100,60,0.35), rgba(0,0,0,0) 70%)',
      ].join(','),
    }}
  />
);

/** Squared paper, slightly stained. */
export const GridPaper: FC = () => (
  <AbsoluteFill
    style={{
      backgroundColor: '#d6ccb4',
      backgroundImage: [
        'radial-gradient(ellipse at 20% 30%, rgba(90,70,40,0.22), rgba(0,0,0,0) 45%)',
        'radial-gradient(ellipse at 75% 70%, rgba(90,70,40,0.18), rgba(0,0,0,0) 40%)',
        'linear-gradient(rgba(70,60,40,0.16) 1px, transparent 1px)',
        'linear-gradient(90deg, rgba(70,60,40,0.16) 1px, transparent 1px)',
      ].join(','),
      backgroundSize: '100% 100%, 100% 100%, 30px 30px, 30px 30px',
    }}
  />
);

/** A black sky with faint stars. */
export const Stars: FC<{ count?: number }> = ({ count = 140 }) => (
  <AbsoluteFill style={{ backgroundColor: '#050505' }}>
    <svg width="100%" height="100%" viewBox="0 0 1920 1080" style={{ position: 'absolute', inset: 0 }}>
      {Array.from({ length: count }, (_, i) => (
        <circle key={i} cx={rand(i) * 1920} cy={rand(i + 500) * 1080} r={0.6 + rand(i + 900) * 1.4} fill="#fff" opacity={0.15 + rand(i + 1300) * 0.5} />
      ))}
    </svg>
  </AbsoluteFill>
);

/** Letters of `text` shown so far when typing at `perFrame` letters a frame from frame `from`. */
export const typed = (text: string, frame: number, from: number, perFrame = 0.9) =>
  text.slice(0, Math.max(0, Math.min(text.length, Math.floor((frame - from) * perFrame))));
