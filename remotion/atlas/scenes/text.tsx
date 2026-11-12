/**
 * Escenas de texto y estructura (fase 1): chapter-card, agenda, title-overlay, statement,
 * card-row, checklist, recap, cta. Todo el contenido llega del storyboard.
 */
import type { FC, ReactNode } from 'react';
import { AbsoluteFill } from 'remotion';
import { drawOn, progress, reveal } from '../anim';
import { useAtlasTime, useScene, useTheme } from '../context';
import { fonts } from '../fonts';
import type { AtlasScene, At, Accent } from '../schema';
import { accentOn, themes } from '../theme';
import { sec } from '../time';
import { Caps, Mono, PaperCard, RichTitle } from '../ui';

type SceneOf<T extends AtlasScene['type']> = Extract<AtlasScene, { type: T }>;

export const useSceneOf = <T extends AtlasScene['type']>(type: T): SceneOf<T> => {
  const { scene } = useScene();
  if (scene.type !== type) throw new Error(`componente ${type} montado con escena ${scene.type}`);
  return scene as SceneOf<T>;
};

/** Momento de un `At` opcional; si falta, `fallback` segundos tras el inicio de la escena. */
export const useAtOr = () => {
  const { start } = useScene();
  return (at: At | undefined, fallback = 0.25) => (at ? sec(at) : start + fallback);
};

export const Center: FC<{ top: number; children: ReactNode; style?: React.CSSProperties }> = ({ top, children, style }) => (
  <div style={{ position: 'absolute', left: 0, right: 0, top, display: 'flex', justifyContent: 'center', ...style }}>{children}</div>
);

/** Antetítulo mono + titular serif con resaltado, centrados arriba. */
export const Header: FC<{ top?: number; size?: number; defaultAccent?: Accent }> = ({ top = 168, size = 66, defaultAccent = 'danger' }) => {
  const { scene } = useScene();
  const { name, tokens } = useTheme();
  const time = useAtlasTime();
  const atOr = useAtOr();
  const titleAt = atOr('titleAt' in scene ? scene.titleAt : undefined);
  const k = reveal(time, titleAt - 0.1);
  const t = reveal(time, titleAt + 0.15);
  return (
    <>
      {scene.kicker ? (
        <Center top={top} style={k.style}>
          <Mono size={26} color={tokens.inkSoft} tracking="0.2em">
            {scene.kicker}
          </Mono>
        </Center>
      ) : null}
      {scene.title ? (
        <Center top={top + (scene.kicker ? 46 : 0)} style={t.style}>
          <RichTitle rich={scene.title} theme={name} size={size} defaultAccent={defaultAccent} />
        </Center>
      ) : null}
    </>
  );
};

/* ── atlas-chapter-card ─────────────────────────────────────────────────── */

export const ChapterCardScene: FC = () => {
  const scene = useSceneOf('atlas-chapter-card');
  const { storyboard, start } = useScene();
  const { name, tokens } = useTheme();
  const time = useAtlasTime();
  const numeral = storyboard.meta.chapters[scene.of].numeral;
  const rules = progress(time, start + 0.15, 0.7);
  const n = reveal(time, start + 0.1);
  const title = reveal(time, sec(scene.titleAt ?? { t: start + 0.45 }));
  return (
    <AbsoluteFill>
      <Center top={372} style={{ alignItems: 'center', gap: 56 }}>
        <div style={{ width: 190 * rules, height: 2, backgroundColor: tokens.inkSoft, marginLeft: 190 * (1 - rules) }} />
        <span style={{ ...n.style, fontFamily: fonts.serif, fontWeight: 600, fontSize: 88, lineHeight: 1, color: tokens.ink }}>
          {numeral}
        </span>
        <div style={{ width: 190 * rules, height: 2, backgroundColor: tokens.inkSoft, marginRight: 190 * (1 - rules) }} />
      </Center>
      {scene.title ? (
        <Center top={526} style={title.style}>
          <RichTitle rich={scene.title} theme={name} size={96} defaultAccent="data" />
        </Center>
      ) : null}
    </AbsoluteFill>
  );
};

/* ── atlas-agenda ───────────────────────────────────────────────────────── */

export const AgendaScene: FC = () => {
  const scene = useSceneOf('atlas-agenda');
  const { storyboard } = useScene();
  const { name, tokens } = useTheme();
  const time = useAtlasTime();
  const atOr = useAtOr();
  const title = reveal(time, atOr(scene.titleAt, 0.1));
  return (
    <AbsoluteFill>
      {scene.title ? (
        <Center top={176} style={title.style}>
          <RichTitle rich={scene.title} theme={name} size={82} defaultAccent="data" />
        </Center>
      ) : null}
      <Center top={410} style={{ gap: 110 }}>
        {storyboard.meta.chapters.map((c, i) => {
          const at = scene.numerals[i] ?? scene.numerals[scene.numerals.length - 1];
          const r = reveal(time, sec(at), 0.5);
          return (
            <span key={i} style={{ ...r.style, fontFamily: fonts.serif, fontWeight: 600, fontSize: 124, lineHeight: 1, color: tokens.ink }}>
              {c.numeral}
            </span>
          );
        })}
      </Center>
      {scene.tagline ? (
        <Center top={650} style={reveal(time, sec(scene.tagline.at)).style}>
          <RichTitle
            rich={scene.tagline.text}
            theme={name}
            size={52}
            color={tokens.inkSoft}
            style={{ fontFamily: fonts.serifItalic, fontStyle: 'italic', fontWeight: 600 }}
          />
        </Center>
      ) : null}
      {scene.notes?.map((note, i) => (
        <Center key={i} top={758 + i * 56} style={reveal(time, sec(note.at)).style}>
          <Mono size={30} color={note.accent ? accentOn(name, note.accent) : tokens.inkSoft} tracking="0.2em" style={{ opacity: 0.75, fontWeight: 400 }}>
            {note.text}
          </Mono>
        </Center>
      ))}
    </AbsoluteFill>
  );
};

/* ── atlas-title-overlay ────────────────────────────────────────────────── */

export const TitleOverlayScene: FC = () => {
  const scene = useSceneOf('atlas-title-overlay');
  const { name, tokens } = useTheme();
  const time = useAtlasTime();
  const atOr = useAtOr();
  const t = reveal(time, atOr(scene.titleAt, 0.2), 0.7);
  return (
    <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'center' }}>
      {scene.title ? (
        <div style={{ ...t.style, textAlign: 'center', maxWidth: 1600 }}>
          <RichTitle
            rich={scene.title}
            theme={name}
            size={88}
            defaultAccent="amber"
            style={{
              WebkitTextStroke: `10px ${tokens.bg}`,
              paintOrder: 'stroke fill',
              textShadow: `0 4px 24px ${tokens.bg}`,
            }}
          />
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

/* ── atlas-statement ────────────────────────────────────────────────────── */

export const StatementScene: FC = () => (
  <AbsoluteFill>
    <Header />
  </AbsoluteFill>
);

/* ── atlas-card-row ─────────────────────────────────────────────────────── */

export const CardRowScene: FC = () => {
  const scene = useSceneOf('atlas-card-row');
  const { name } = useTheme();
  const time = useAtlasTime();
  const n = scene.cards.length;
  const w = n > 3 ? 360 : 400;
  const gap = 30;
  const left = (1920 - (n * w + (n - 1) * gap)) / 2;
  return (
    <AbsoluteFill>
      <Header />
      {scene.cards.map((card, i) => {
        const r = reveal(time, sec(card.at), 0.5);
        return (
          <div
            key={i}
            style={{
              position: 'absolute',
              top: 430,
              left: left + i * (w + gap),
              width: w,
              height: 362,
              opacity: r.opacity,
              filter: r.style.filter,
              transform: `translateX(${(1 - r.progress) * -24}px)`,
            }}
          >
            <PaperCard theme={name} padding="44px 28px" style={{ height: '100%', boxSizing: 'border-box', textAlign: 'center' }}>
              <div
                style={{
                  fontFamily: fonts.serif,
                  fontWeight: 600,
                  fontSize: 62,
                  lineHeight: 1,
                  color: accentOn('paper', card.accent ?? 'data'),
                }}
              >
                {card.heading}
              </div>
              <div style={{ marginTop: 74 }}>
                <RichTitle rich={card.text} theme={name} onCard size={40} style={{ fontWeight: 500 }} />
              </div>
            </PaperCard>
          </div>
        );
      })}
    </AbsoluteFill>
  );
};

/* ── atlas-checklist ────────────────────────────────────────────────────── */

const Checkbox: FC<{ p: number; color: string; ink: string }> = ({ p, color, ink }) => {
  const d = drawOn(p, 0, 1, (x) => x);
  return (
    <svg width={62} height={62} viewBox="0 0 62 62" style={{ flexShrink: 0 }}>
      <rect x={3} y={3} width={56} height={56} fill="none" stroke={ink} strokeWidth={3} />
      <path
        d="M12 32 L25 46 L53 8"
        fill="none"
        stroke={color}
        strokeWidth={5}
        strokeLinecap="round"
        strokeLinejoin="round"
        pathLength={1}
        strokeDasharray={d.strokeDasharray}
        strokeDashoffset={d.strokeDashoffset}
      />
    </svg>
  );
};

export const ChecklistScene: FC = () => {
  const scene = useSceneOf('atlas-checklist');
  const { name, tokens } = useTheme();
  const time = useAtlasTime();
  const atOr = useAtOr();
  const title = reveal(time, atOr(scene.titleAt, 0.1));
  return (
    <AbsoluteFill>
      {scene.title ? (
        <Center top={150} style={title.style}>
          <RichTitle rich={scene.title} theme={name} size={70} defaultAccent="data" />
        </Center>
      ) : null}
      <Center top={290}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 66 }}>
          {scene.items.map((item, i) => {
            const at = sec(item.at);
            const r = reveal(time, at, 0.5);
            const tick = progress(time, at + 0.25, 0.45);
            return (
              <div key={i} style={{ ...r.style, display: 'flex', gap: 32, alignItems: 'flex-start' }}>
                <Checkbox p={tick} color={accentOn(name, item.accent ?? 'good')} ink={tokens.ink} />
                <div style={{ display: 'flex', flexDirection: 'column', gap: 14, paddingTop: 4 }}>
                  <RichTitle rich={item.text} theme={name} size={45} style={{ fontWeight: 600 }} />
                  {item.sub ? (
                    <Mono size={23} color={tokens.inkSoft} tracking="0.2em">
                      {item.sub}
                    </Mono>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      </Center>
    </AbsoluteFill>
  );
};

/* ── atlas-recap ────────────────────────────────────────────────────────── */

export const RecapScene: FC = () => {
  const scene = useSceneOf('atlas-recap');
  const { storyboard } = useScene();
  const { name } = useTheme();
  const time = useAtlasTime();
  const atOr = useAtOr();
  const title = reveal(time, atOr(scene.titleAt, 0.1));
  const n = Math.min(scene.items.length, storyboard.meta.chapters.length || scene.items.length);
  const gap = 24;
  const w = Math.min(340, (1800 - gap * (n - 1)) / n);
  const left = (1920 - (n * w + (n - 1) * gap)) / 2;
  return (
    <AbsoluteFill>
      {scene.title ? (
        <Center top={172} style={title.style}>
          <RichTitle rich={scene.title} theme={name} size={76} defaultAccent="data" />
        </Center>
      ) : null}
      {scene.items.map((item, i) => {
        const chapter = storyboard.meta.chapters[i];
        if (!chapter) return null;
        const r = reveal(time, sec(item.at), 0.5);
        return (
          <div
            key={i}
            style={{
              position: 'absolute',
              top: 400,
              left: left + i * (w + gap),
              width: w,
              height: 380,
              opacity: r.opacity,
              filter: r.style.filter,
              transform: `translateY(${(1 - r.progress) * 16}px)`,
            }}
          >
            <PaperCard theme={name} padding="38px 54px" style={{ height: '100%', boxSizing: 'border-box', textAlign: 'center' }}>
              <div style={{ fontFamily: fonts.serif, fontWeight: 600, fontSize: 76, lineHeight: 1, color: themes.paper.ink }}>
                {chapter.numeral}
              </div>
              <div
                style={{
                  marginTop: 22,
                  fontFamily: fonts.serifItalic,
                  fontStyle: 'italic',
                  fontSize: 30,
                  letterSpacing: '0.24em',
                  color: themes.paper.ink,
                }}
              >
                {chapter.label}
              </div>
              <div
                style={{
                  marginTop: 34,
                  fontFamily: fonts.serif,
                  fontWeight: 600,
                  fontSize: 33,
                  lineHeight: 1.2,
                  letterSpacing: '-0.01em',
                  color: themes.paper.ink,
                }}
              >
                {item.text}
              </div>
            </PaperCard>
          </div>
        );
      })}
    </AbsoluteFill>
  );
};

/* ── atlas-cta ──────────────────────────────────────────────────────────── */

const SubscribeButton: FC<{ label: string; doneLabel?: string; clicked: number; appear: number }> = ({
  label,
  doneLabel,
  clicked,
  appear,
}) => {
  const { storyboard } = useScene();
  const icon = storyboard.meta.brand.icon;
  const red = themes.paper.accents.danger;
  const dark = themes.paper.ink;
  const done = doneLabel !== undefined && clicked > 0.5;
  const press = clicked > 0 && clicked < 1 ? 1 - 0.06 * Math.sin(Math.PI * clicked) : 1;
  return (
    <div
      style={{
        opacity: appear,
        transform: `scale(${press})`,
        backgroundColor: done ? dark : red,
        color: themes.paper.card,
        width: 508,
        height: 94,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 30,
      }}
    >
      {icon && !/\.(svg|png|jpe?g|webp)$/i.test(icon) ? (
        <span style={{ fontSize: 58, lineHeight: 1, fontFamily: 'DejaVu Sans, sans-serif', marginTop: -6 }}>{icon}</span>
      ) : null}
      <Caps size={44} color={themes.paper.card} tracking="0.04em" style={{ fontWeight: 600 }}>
        {done ? doneLabel : label}
      </Caps>
    </div>
  );
};

export const CtaScene: FC = () => {
  const scene = useSceneOf('atlas-cta');
  const { name } = useTheme();
  const time = useAtlasTime();
  const atOr = useAtOr();
  const cardIn = reveal(time, atOr(scene.titleAt, 0.15));
  const buttonIn = progress(time, atOr(scene.button.at, 0.6), 0.5);
  const clicked = scene.button.clickAt ? progress(time, sec(scene.button.clickAt), 0.35) : 0;
  const button = (
    <SubscribeButton label={scene.button.label} doneLabel={scene.button.doneLabel} clicked={clicked} appear={buttonIn} />
  );
  const heading = (
    <>
      {scene.kicker ? (
        <div style={{ marginBottom: 18 }}>
          <Caps size={27} color={themes.paper.inkSoft} tracking="0.14em">
            {scene.kicker}
          </Caps>
        </div>
      ) : null}
      {scene.title ? (
        <RichTitle rich={scene.title} theme={name} onCard size={56} defaultAccent={scene.layout === 'card' ? 'data' : 'danger'} />
      ) : null}
    </>
  );
  if (scene.layout === 'card') {
    return (
      <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'center' }}>
        <div style={cardIn.style}>
          <PaperCard theme={name} padding="56px 72px 64px" style={{ textAlign: 'center', minWidth: 860 }}>
            {heading}
            <div style={{ display: 'flex', justifyContent: 'center', marginTop: 30 }}>{button}</div>
          </PaperCard>
        </div>
      </AbsoluteFill>
    );
  }
  return (
    <AbsoluteFill>
      <Center top={94} style={cardIn.style}>
        <PaperCard theme={name} padding="46px 80px 50px" style={{ textAlign: 'center', minWidth: 1060 }}>
          {heading}
        </PaperCard>
      </Center>
      <Center top={400}>{button}</Center>
    </AbsoluteFill>
  );
};
