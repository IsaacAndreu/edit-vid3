/** Capas globales: fondo papel/noche, viñeta, grano, marca e indicador de capítulos. */
import type { FC } from 'react';
import { AbsoluteFill, Img, staticFile, useCurrentFrame } from 'remotion';
import GRAIN from '../../data/grain.png';
import { progress } from '../anim';
import { useAtlasTime, useScene, useTheme } from '../context';
import { fonts } from '../fonts';
import type { ThemeName } from '../theme';
import { LAYOUT, themes } from '../theme';
import { Mono } from '../ui';

/** Fondo liso + textura de papel muy sutil: la misma tesela de grano que el Atlas automático, ampliada y fija. */
export const Background: FC<{ theme: ThemeName }> = ({ theme }) => {
  const t = themes[theme];
  return (
    <AbsoluteFill style={{ backgroundColor: t.bg }}>
      <AbsoluteFill
        style={{ backgroundImage: `url(${GRAIN})`, backgroundSize: '1024px 1024px', opacity: theme === 'paper' ? 0.045 : 0.05, mixBlendMode: 'multiply' }}
      />
      {/* El centro del original es un poco más claro que el token de fondo (bajo el contenido). */}
      <AbsoluteFill
        style={{
          background: `radial-gradient(ellipse 50% 50% at 50% 48%, rgba(255,250,235,${theme === 'paper' ? 0.2 : 0.03}) 0%, rgba(255,250,235,0) 100%)`,
        }}
      />
    </AbsoluteFill>
  );
};

/** Viñeta ovalada suave hacia el color de borde. */
export const Vignette: FC<{ theme: ThemeName }> = ({ theme }) => (
  <AbsoluteFill
    style={{
      background: `radial-gradient(ellipse 72% 68% at 50% 48%, rgba(0,0,0,0) 55%, ${themes[theme].vignette} 100%)`,
      pointerEvents: 'none',
    }}
  />
);

/**
 * Grano fino animado (~4 %): una tesela PNG fija que salta de posición cada fotograma. Un filtro de ruido SVG
 * recalculado por fotograma costaba casi 2 s por fotograma en render sin GPU.
 */
export const Grain: FC = () => {
  const frame = useCurrentFrame();
  const seed = (frame * 7919) % 997;
  return (
    <AbsoluteFill
      style={{
        pointerEvents: 'none',
        opacity: 0.08,
        mixBlendMode: 'multiply',
        backgroundImage: `url(${GRAIN})`,
        backgroundSize: '256px 256px',
        backgroundPosition: `${(seed * 37) % 256}px ${(seed * 53) % 256}px`,
      }}
    />
  );
};

const isImagePath = (icon: string) => /\.(svg|png|jpe?g|webp)$/i.test(icon);

/** Marca arriba a la izquierda: icono + nombre en mono mayúsculas, siempre visible. */
export const Brand: FC = () => {
  const { storyboard } = useScene();
  const { tokens } = useTheme();
  const { name, icon } = storyboard.meta.brand;
  return (
    <div
      style={{
        position: 'absolute',
        left: LAYOUT.margin - 8,
        top: LAYOUT.hudTop + 4,
        display: 'flex',
        alignItems: 'center',
        gap: 16,
        color: tokens.ink,
      }}
    >
      {icon ? (
        isImagePath(icon) ? (
          <Img src={staticFile(icon)} style={{ height: 26 }} />
        ) : (
          <span style={{ fontSize: 50, lineHeight: 1, marginTop: -6, fontFamily: 'DejaVu Sans, sans-serif' }}>{icon}</span>
        )
      ) : null}
      <Mono size={19} color={tokens.ink} tracking="0.24em">
        {name}
      </Mono>
    </div>
  );
};

/**
 * Indicador de capítulos arriba a la derecha: vistos en tinta, actual en rojo subrayado con su
 * etiqueta en cursiva, pendientes en gris. Sólo aparece en escenas con `chapter`.
 */
export const ChapterIndicator: FC = () => {
  const { storyboard, scene, start } = useScene();
  const { name, tokens } = useTheme();
  const time = useAtlasTime();
  const chapters = storyboard.meta.chapters;
  if (scene.chapter === undefined || chapters.length === 0) return null;
  const current = scene.chapter;
  const underline = progress(time, start + 0.2, 0.6);
  const danger = tokens.accents.danger;
  const pending = name === 'paper' ? 'rgba(42,33,24,0.32)' : 'rgba(237,230,211,0.3)';
  return (
    <div
      style={{
        position: 'absolute',
        right: LAYOUT.margin + 52,
        top: LAYOUT.hudTop - 6,
        display: 'flex',
        gap: 54,
      }}
    >
      {chapters.map((c, i) => {
        const color = i < current ? tokens.ink : i === current ? danger : pending;
        return (
          <div key={i} style={{ position: 'relative', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
            <span style={{ fontFamily: fonts.serif, fontWeight: 600, fontSize: 30, color, lineHeight: 1.1 }}>{c.numeral}</span>
            {i === current ? (
              <>
                <div
                  style={{
                    marginTop: 8,
                    height: 2.5,
                    width: 56 * underline,
                    backgroundColor: danger,
                  }}
                />
                <span
                  style={{
                    position: 'absolute',
                    top: 58,
                    fontFamily: fonts.serifItalic,
                    fontStyle: 'italic',
                    fontSize: 23,
                    letterSpacing: '0.22em',
                    color: tokens.ink,
                    whiteSpace: 'nowrap',
                    opacity: underline,
                  }}
                >
                  {c.label}
                </span>
              </>
            ) : null}
          </div>
        );
      })}
    </div>
  );
};
