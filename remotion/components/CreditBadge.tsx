import type { FC } from 'react';
import { AbsoluteFill } from 'remotion';
import { fontFamily } from '../theme';

/** Top-right source credit, visible for the whole third-party clip. Text comes from the manifest. */
export const CreditBadge: FC<{ credit: string }> = ({ credit }) => (
  <AbsoluteFill style={{ justifyContent: 'flex-start', alignItems: 'flex-end', padding: '34px 40px' }}>
    <div
      style={{
        fontFamily,
        fontSize: 24,
        fontWeight: 500,
        color: 'rgba(255,255,255,0.92)',
        backgroundColor: 'rgba(0,0,0,0.6)',
        padding: '8px 16px',
        borderRadius: 8,
        maxWidth: 760,
        whiteSpace: 'nowrap',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        letterSpacing: '0.01em',
      }}
    >
      {credit}
    </div>
  </AbsoluteFill>
);
