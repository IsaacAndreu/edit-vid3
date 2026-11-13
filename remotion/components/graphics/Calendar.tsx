import type { FC } from 'react';
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { fontFamily, theme } from '../../theme';
import type { CalendarGraphic } from '../../graphics';

/**
 * A key date as a page of the calendar, the way true-crime channels mark the day everything changed: the month big
 * in spaced capitals, the year under it, a row of days sliding in and THE day lifting out of the row in a white card
 * that a red ring is drawn around. The words come from the script (graphics.clean), nothing is written here.
 */
export const Calendar: FC<{ graphic: CalendarGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame, fps, config: { damping: 200, stiffness: 80 } });
  const days = [-4, -3, -2, -1, 0, 1, 2, 3, 4];
  const lift = spring({ frame: frame - 14, fps, config: { damping: 14, stiffness: 140 } });
  const ring = interpolate(frame, [26, 44], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const label = interpolate(frame, [34, 46], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const drift = interpolate(frame, [0, durationInFrames], [0, -24]);
  const year = graphic.year ?? 2001;
  // the days around it, across the month's edges (the 2nd of April shows 29, 30, 31 of March before it)
  const dayOf = (offset: number) => new Date(Date.UTC(year, graphic.month - 1, graphic.day + offset)).getUTCDate();
  const circumference = 2 * Math.PI * 84;
  return (
    <AbsoluteFill style={{ backgroundColor: theme.canvas, justifyContent: 'center', alignItems: 'center', fontFamily }}>
      <AbsoluteFill style={{ background: `radial-gradient(ellipse at center, rgba(255,255,255,0.06) 0%, rgba(0,0,0,0) 55%, rgba(0,0,0,0.75) 100%)` }} />
      <div style={{ opacity: enter, transform: `translateY(${(1 - enter) * 30}px)`, textAlign: 'center' }}>
        <div style={{ fontFamily: "'DM Serif Display', Georgia, serif", fontSize: 128, letterSpacing: '0.18em', color: theme.text,
                      lineHeight: 1, marginRight: '-0.18em' }}>
          {graphic.monthName.toUpperCase()}
        </div>
        {graphic.year ? (
          <div style={{ fontSize: 34, letterSpacing: '0.5em', color: theme.muted, marginTop: 18, marginRight: '-0.5em' }}>{graphic.year}</div>
        ) : null}
      </div>
      <div style={{ display: 'flex', gap: 34, marginTop: 70, alignItems: 'flex-end', transform: `translateX(${drift}px)` }}>
        {days.map((offset, i) => {
          const day = dayOf(offset);
          const marked = offset === 0;
          const show = spring({ frame: frame - 4 - Math.abs(offset) * 2, fps, config: { damping: 200, stiffness: 120 } });
          const fade = marked ? 1 : 0.32 + 0.2 * (1 - Math.abs(offset) / 4);
          const weekday = graphic.weekdays.length ? graphic.weekdays[(((graphic.weekday + offset) % 7) + 7) % 7] : '';
          return (
            <div key={offset} style={{ width: 120, textAlign: 'center', opacity: show * fade,
                                       transform: marked ? `translateY(${-18 * lift}px) scale(${1 + 0.12 * lift})` : undefined }}>
              <div style={{ fontSize: 22, letterSpacing: '0.2em', color: marked ? theme.text : theme.muted, marginBottom: marked ? 30 : 10 }}>
                {weekday.toUpperCase()}
              </div>
              <div style={{ position: 'relative', height: 132, display: 'flex', alignItems: 'center', justifyContent: 'center',
                            borderRadius: 10, background: marked ? '#f4f1ea' : 'transparent',
                            boxShadow: marked ? '0 18px 40px rgba(0,0,0,0.6)' : undefined }}>
                <span style={{ fontFamily: "'DM Serif Display', Georgia, serif", fontSize: 84,
                               color: marked ? '#111' : theme.text }}>{day}</span>
                {marked ? (
                  <svg width={220} height={220} viewBox="0 0 220 220" style={{ position: 'absolute', left: -50, top: -44, overflow: 'visible' }}>
                    <circle cx={110} cy={110} r={84} fill="none" stroke="#e3262f" strokeWidth={6} strokeLinecap="round"
                            strokeDasharray={circumference} strokeDashoffset={circumference * (1 - ring)}
                            transform="rotate(-100 110 110)" />
                  </svg>
                ) : null}
              </div>
            </div>
          );
        })}
      </div>
      {graphic.label ? (
        <div style={{ marginTop: 64, fontSize: 30, letterSpacing: '0.24em', color: theme.accent, opacity: label,
                      textTransform: 'uppercase' }}>{graphic.label}</div>
      ) : null}
    </AbsoluteFill>
  );
};
