import type { FC } from 'react';
import { AbsoluteFill } from 'remotion';
import { fontFamily, theme } from '../theme';

/**
 * Top-right source credit, visible for the whole third-party clip. Text comes from the manifest ("Fuente: MLive").
 * Shown as a small chip — a dot in the channel accent, the word ("FUENTE", "SOURCE") small and dim, the source in
 * bold — like the news-clip tags of the documentary channels: clear about where each image comes from, never loud.
 */
export const CreditBadge: FC<{ credit: string }> = ({ credit }) => {
  const match = /^([^:]{2,14}):\s*(.+)$/.exec(credit.trim());
  const word = match ? match[1] : '';
  const source = match ? match[2] : credit;
  return (
    <AbsoluteFill style={{ justifyContent: 'flex-start', alignItems: 'flex-end', padding: '30px 36px' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          fontFamily,
          color: 'rgba(255,255,255,0.94)',
          backgroundColor: 'rgba(0,0,0,0.45)',
          padding: '7px 16px 7px 14px',
          borderRadius: 6,
          maxWidth: 760,
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textShadow: '0 1px 3px rgba(0,0,0,0.6)',
        }}
      >
        <div style={{ width: 9, height: 9, borderRadius: 5, backgroundColor: theme.accent, flexShrink: 0 }} />
        {word ? (
          <span style={{ fontSize: 17, fontWeight: 600, letterSpacing: '0.14em', textTransform: 'uppercase', opacity: 0.7 }}>
            {word}
          </span>
        ) : null}
        <span style={{ fontSize: 22, fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis' }}>{source}</span>
      </div>
    </AbsoluteFill>
  );
};
