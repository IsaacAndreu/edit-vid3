/**
 * Superposiciones que se montan sobre cualquier escena vía `overlays[]`.
 * Los componentes llegan en la fase 1; hasta entonces una superposición declarada falla
 * con un mensaje claro en vez de desaparecer en silencio.
 */
import type { FC } from 'react';
import { AbsoluteFill } from 'remotion';
import type { Overlay } from '../schema';

type OverlayKind = Overlay['kind'];

export const atlasOverlays: Partial<Record<OverlayKind, FC<{ overlay: Overlay }>>> = {};

export const OverlayLayer: FC<{ overlays: Overlay[] | undefined; sceneId: string }> = ({ overlays, sceneId }) => {
  if (!overlays?.length) return null;
  return (
    <AbsoluteFill style={{ pointerEvents: 'none' }}>
      {overlays.map((overlay, i) => {
        const Component = atlasOverlays[overlay.kind];
        if (!Component) {
          throw new Error(`Escena "${sceneId}": la superposición "${overlay.kind}" todavía no tiene componente`);
        }
        return <Component key={i} overlay={overlay} />;
      })}
    </AbsoluteFill>
  );
};
