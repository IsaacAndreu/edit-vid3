import type { CSSProperties, FC } from 'react';
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import type { SceneProps } from '../types';

const COLUMN_STAGGER_IN_FRAMES = 7;
const ITEM_STAGGER_IN_FRAMES = 4;
const ITEMS_START_OFFSET_IN_FRAMES = 11;

const containerStyle: CSSProperties = {
  alignItems: 'center',
  backgroundColor: 'transparent',
  display: 'flex',
  height: '100%',
  justifyContent: 'center',
  overflow: 'hidden',
  padding: '0 7%',
  width: '100%',
};

const getColumnColor = (accentColor: string, index: number): string => {
  if (index === 0) {
    return accentColor || '#9cff57';
  }

  if (index === 1) {
    return '#e3e9ee';
  }

  const palette = ['#67e8f9', '#fbbf24', '#f472b6', '#a78bfa'];
  return palette[(index - 2) % palette.length];
};

type ComparisonColumnProps = {
  accentColor: string;
  columnIndex: number;
  items: string[];
  title: string;
};

const ComparisonColumn: FC<ComparisonColumnProps> = ({ accentColor, columnIndex, items, title }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const columnProgress = spring({
    frame: Math.max(0, frame - columnIndex * COLUMN_STAGGER_IN_FRAMES),
    fps,
    config: {
      damping: 18,
      mass: 0.6,
      stiffness: 170,
    },
  });
  const columnOpacity = interpolate(columnProgress, [0, 1], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const columnTranslateY = interpolate(columnProgress, [0, 1], [40, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const columnColor = getColumnColor(accentColor, columnIndex);

  return (
    <div
      style={{
        backgroundColor: 'rgba(5, 12, 18, 0.78)',
        border: `1px solid ${columnColor}`,
        borderRadius: 14,
        boxShadow: `0 0 24px ${columnColor}22`,
        boxSizing: 'border-box',
        flex: '1 1 0',
        minWidth: 0,
        opacity: columnOpacity,
        padding: '30px 34px 34px',
        transform: `translateY(${columnTranslateY}px)`,
      }}
    >
      <div
        style={{
          backgroundColor: columnColor,
          height: 5,
          marginBottom: 24,
          width: 68,
        }}
      />
      <div
        style={{
          color: columnColor,
          fontFamily: 'Inter, Arial, sans-serif',
          fontSize: 36,
          fontWeight: 850,
          letterSpacing: '0.02em',
          lineHeight: 1,
          marginBottom: 30,
          textTransform: 'uppercase',
        }}
      >
        {title}
      </div>
      <div>
        {items.map((item, itemIndex) => {
          const itemProgress = spring({
            frame: Math.max(
              0,
              frame - columnIndex * COLUMN_STAGGER_IN_FRAMES - ITEMS_START_OFFSET_IN_FRAMES - itemIndex * ITEM_STAGGER_IN_FRAMES,
            ),
            fps,
            config: {
              damping: 20,
              mass: 0.5,
              stiffness: 190,
            },
          });
          const itemOpacity = interpolate(itemProgress, [0, 1], [0, 1], {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
          });
          const itemTranslateY = interpolate(itemProgress, [0, 1], [14, 0], {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
          });

          return (
            <div
              key={`${item}-${itemIndex}`}
              style={{
                alignItems: 'flex-start',
                color: '#eef2f5',
                display: 'flex',
                fontFamily: 'Inter, Arial, sans-serif',
                fontSize: 28,
                fontWeight: 500,
                lineHeight: 1.2,
                marginTop: itemIndex === 0 ? 0 : 20,
                opacity: itemOpacity,
                transform: `translateY(${itemTranslateY}px)`,
              }}
            >
              <span
                style={{
                  backgroundColor: columnColor,
                  borderRadius: '50%',
                  flex: '0 0 auto',
                  height: 10,
                  marginRight: 17,
                  marginTop: 10,
                  width: 10,
                }}
              />
              <span>{item}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

const ComparisonPanel: FC<SceneProps> = ({ accentColor, comparisonColumns, text }) => {
  const frame = useCurrentFrame();
  const { fps, height, width } = useVideoConfig();
  const columns = comparisonColumns ?? [];
  const headingProgress = spring({
    frame,
    fps,
    config: {
      damping: 20,
      mass: 0.6,
      stiffness: 170,
    },
  });
  const headingOpacity = interpolate(headingProgress, [0, 1], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  if (columns.length === 0) {
    return <AbsoluteFill style={containerStyle} />;
  }

  return (
    <AbsoluteFill style={containerStyle}>
      <div style={{ maxWidth: Math.min(width * 0.88, 1700), width: '100%' }}>
        {text ? (
          <div
            style={{
              color: '#f7fafc',
              fontFamily: 'Inter, Arial, sans-serif',
              fontSize: Math.min(width * 0.026, 46),
              fontWeight: 700,
              letterSpacing: '0.03em',
              marginBottom: height * 0.045,
              opacity: headingOpacity,
              textAlign: 'center',
            }}
          >
            {text}
          </div>
        ) : null}
        <div style={{ display: 'flex', gap: 24, width: '100%' }}>
          {columns.map((column, index) => (
            <ComparisonColumn
              key={`${column.title}-${index}`}
              accentColor={accentColor}
              columnIndex={index}
              items={column.items}
              title={column.title}
            />
          ))}
        </div>
      </div>
    </AbsoluteFill>
  );
};

export default ComparisonPanel;
