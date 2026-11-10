import type { FC } from 'react';
import { AbsoluteFill, Easing, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import type { SatelliteGraphic } from '../../graphics';
import { condensedFamily, fontFamily, theme } from '../../theme';

const W = 1920;
const H = 1080;

/**
 * Satellite zoom: one continuous flight from the wide view to the place (each layer is 1920x1080 centred on it at
 * its own zoom; the camera scales the nearest layer and cross-fades into the next one), then a pin with the
 * place's name and the other spots the script names. The imagery's credit stays in the corner.
 */
export const SatelliteZoom: FC<{ graphic: SatelliteGraphic; durationInFrames: number }> = ({ graphic, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const layers = [...graphic.layers].sort((a, b) => a.z - b.z);
  const zMin = layers[0].z;
  const zMax = layers[layers.length - 1].z;
  // virtual zoom level: the flight takes the first 65% of the graphic, easing in and out
  const Z = interpolate(frame, [0, durationInFrames * 0.65], [zMin, zMax], {
    extrapolateRight: 'clamp', easing: Easing.inOut(Easing.cubic) });
  const pin = spring({ frame: frame - durationInFrames * 0.62, fps, config: { damping: 12, stiffness: 150 } });
  const labels = interpolate(frame, [durationInFrames * 0.7, durationInFrames * 0.8], [0, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  return (
    <AbsoluteFill style={{ backgroundColor: '#0d141c', overflow: 'hidden' }}>
      {layers.map((layer, i) => {
        const next = layers[i + 1];
        // a layer shows from its own zoom until the next one is reached, fading out over the last half level
        if (Z < layer.z - (i === 0 ? 99 : 1)) return null;
        if (next && Z > next.z + 0.01) return null;
        const scale = 2 ** (Z - layer.z);
        const fadeIn = i === 0 ? 1 : interpolate(Z, [layer.z - 1, layer.z - 0.2], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
        return (
          <Img key={layer.z} src={staticFile(layer.media.src)} style={{
            position: 'absolute', left: 0, top: 0, width: W, height: H, opacity: fadeIn,
            filter: layer.media.source === 'eox' ? 'brightness(1.25) contrast(1.05) saturate(1.15)' : undefined,
            transform: `scale(${scale})`, transformOrigin: '50% 50%',
          }} />
        );
      })}
      {/* vignette, so the pin and labels read on any ground */}
      <AbsoluteFill style={{ background: 'radial-gradient(ellipse at 50% 50%, rgba(0,0,0,0) 45%, rgba(0,0,0,0.45) 100%)' }} />
      <div style={{ position: 'absolute', left: W / 2, top: H / 2, transform: `translate(-50%, -100%) scale(${pin})`, transformOrigin: '50% 100%' }}>
        <div style={{
          fontFamily: condensedFamily, fontWeight: 700, fontSize: 46, color: '#fff', backgroundColor: theme.mapHighlight || theme.accent,
          padding: '6px 20px', borderRadius: 6, whiteSpace: 'nowrap', textTransform: 'uppercase', boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
        }}>
          {graphic.place}
        </div>
        <div style={{ width: 4, height: 60, backgroundColor: '#fff', margin: '0 auto' }} />
        <div style={{ width: 22, height: 22, borderRadius: 11, backgroundColor: '#fff', margin: '-6px auto 0', boxShadow: '0 0 0 6px rgba(255,255,255,0.3)' }} />
      </div>
      {(graphic.labels ?? []).map((l, i) => (
        <div key={i} style={{
          position: 'absolute', left: W / 2 + l.dx, top: H / 2 + l.dy, transform: 'translate(-50%, -50%)', opacity: labels,
          fontFamily: condensedFamily, fontWeight: 700, fontSize: 40, color: '#fff', whiteSpace: 'nowrap',
          textShadow: '0 3px 10px rgba(0,0,0,0.85)',
        }}>
          {l.name}
        </div>
      ))}
      {graphic.credit ? (
        <div style={{ position: 'absolute', right: 30, bottom: 22, fontFamily, fontSize: 18, color: 'rgba(255,255,255,0.75)',
          textShadow: '0 1px 4px rgba(0,0,0,0.9)' }}>
          {graphic.credit}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};
