/** Piezas tipográficas compartidas: mono en mayúsculas, titular con resaltado en cursiva. */
import type { CSSProperties, FC, ReactNode } from 'react';
import { fonts } from './fonts';
import type { Accent, Rich } from './schema';
import type { ThemeName } from './theme';
import { accentOn, LAYOUT, themes } from './theme';

export const Mono: FC<{
  children: ReactNode;
  size?: number;
  color?: string;
  tracking?: string;
  italic?: boolean;
  style?: CSSProperties;
}> = ({ children, size = LAYOUT.monoSize, color, tracking = LAYOUT.monoTracking, italic, style }) => (
  <span
    style={{
      fontFamily: fonts.mono,
      fontSize: size,
      fontWeight: 500,
      fontStyle: italic ? 'italic' : 'normal',
      letterSpacing: tracking,
      textTransform: italic ? 'none' : 'uppercase',
      color,
      whiteSpace: 'nowrap',
      ...style,
    }}
  >
    {children}
  </span>
);

/** Divide "texto *resaltado* texto" en tramos. */
export const splitRich = (text: string): { text: string; emphasis: boolean }[] => {
  const parts: { text: string; emphasis: boolean }[] = [];
  const re = /\*([^*]+)\*/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    if (m.index > last) parts.push({ text: text.slice(last, m.index), emphasis: false });
    parts.push({ text: m[1], emphasis: true });
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push({ text: text.slice(last), emphasis: false });
  return parts;
};

export const richText = (rich: Rich): { text: string; accent?: Accent } =>
  typeof rich === 'string' ? { text: rich } : rich;

/**
 * Titular serif con la palabra clave en cursiva de color (la firma del estilo).
 * `defaultAccent` se usa si el Rich no trae acento.
 */
export const RichTitle: FC<{
  rich: Rich;
  theme: ThemeName;
  size: number;
  color?: string;
  defaultAccent?: Accent;
  /** Sobre tarjeta clara: el acento se toma del tema papel. */
  onCard?: boolean;
  style?: CSSProperties;
}> = ({ rich, theme, size, color, defaultAccent = 'danger', onCard, style }) => {
  const { text, accent } = richText(rich);
  const palette = onCard ? 'paper' : theme;
  const ink = color ?? (onCard ? themes.paper.ink : themes[theme].ink);
  return (
    <span
      style={{
        fontFamily: fonts.serif,
        fontWeight: 600,
        fontSize: size,
        lineHeight: 1.08,
        letterSpacing: '-0.02em',
        color: ink,
        fontVariationSettings: '"opsz" 144',
        ...style,
      }}
    >
      {splitRich(text).map((part, i) =>
        part.emphasis ? (
          <span
            key={i}
            style={{
              fontFamily: fonts.serifItalic,
              fontStyle: 'italic',
              color: accentOn(palette, accent ?? defaultAccent),
            }}
          >
            {part.text}
          </span>
        ) : (
          <span key={i}>{part.text}</span>
        ),
      )}
    </span>
  );
};

/** Halo del color del fondo detrás de textos sobre mapa (§2). */
export const halo = (bg: string, width = 3.5): CSSProperties => ({
  WebkitTextStroke: `${width * 2}px ${bg}`,
  paintOrder: 'stroke fill',
});
