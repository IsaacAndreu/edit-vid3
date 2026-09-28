import type { FC } from "react";
import { AbsoluteFill, Composition, Sequence, useCurrentFrame } from "remotion";
import { CreditBadge } from "./components/CreditBadge";
import { Thumbnail, type ThumbnailVariant } from "./components/Thumbnail";
import { GraphicScene } from "./components/graphics/GraphicScene";
import { ParallaxPhoto } from "./components/ParallaxPhoto";
import type { Graphic } from "./graphics";
import type { Media } from "./types";
import { applyBrand, type Brand } from "./theme";
import { Documentary } from "./Documentary";
import type { TimelineProps } from "./types";

const empty: TimelineProps = {
  slug: "empty",
  title: "",
  fps: 30,
  width: 1920,
  height: 1080,
  durationInFrames: 30,
  shots: [],
  groups: [],
  audio: { voice: "", musicVolume: 0, duckedVolume: 0, speech: [], sfx: [] },
};

interface BadgesProps {
  credits: string[];
  brand?: Brand | null;
  [key: string]: unknown;
}

/** Frame i = credit badge i on a transparent background (the render stage overlays it with ffmpeg). */
const Badges: FC<BadgesProps> = ({ credits, brand }) => {
  applyBrand(brand);
  const credit = credits[useCurrentFrame()];
  return (
    <AbsoluteFill>
      {credit ? <CreditBadge credit={credit} /> : null}
    </AbsoluteFill>
  );
};

interface ThumbnailsProps {
  variants: ThumbnailVariant[];
  brand?: Brand | null;
  [key: string]: unknown;
}

/** Frame i = thumbnail variant i (rendered as an image sequence by the package stage). */
const Thumbnails: FC<ThumbnailsProps> = ({ variants, brand }) => {
  applyBrand(brand);
  const variant = variants[useCurrentFrame()];
  return variant ? <Thumbnail variant={variant} /> : <AbsoluteFill />;
};

interface ShowcaseProps {
  scenes: { graphic?: Graphic; parallax?: Media; seconds: number }[];
  brand?: Brand | null;
  [key: string]: unknown;
}

/** Every animated template one after another (samples to review the templates). */
const Showcase: FC<ShowcaseProps> = ({ scenes, brand }) => {
  applyBrand(brand);
  let from = 0;
  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      {scenes.map((scene, i) => {
        const frames = Math.round(scene.seconds * 30);
        const at = from;
        from += frames;
        return (
          <Sequence key={i} from={at} durationInFrames={frames}>
            {scene.graphic ? <GraphicScene graphic={scene.graphic} durationInFrames={frames} /> : null}
            {scene.parallax ? <ParallaxPhoto media={scene.parallax} durationInFrames={frames} seed={`s${i}`} /> : null}
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};

/** Props = work/<slug>/timeline.json; render with --public-dir=work/<slug>. */
export const RemotionRoot: FC = () => (
  <>
    <Composition
      id="Documentary"
      component={Documentary}
      defaultProps={empty}
      durationInFrames={30}
      fps={30}
      width={1920}
      height={1080}
      calculateMetadata={({ props }) => ({
        durationInFrames: Math.max(1, props.durationInFrames),
        fps: props.fps,
        width: props.width,
        height: props.height,
      })}
    />
    <Composition
      id="Badges"
      component={Badges}
      defaultProps={{ credits: [] } as BadgesProps}
      durationInFrames={1}
      fps={30}
      width={1920}
      height={1080}
      calculateMetadata={({ props }) => ({
        durationInFrames: Math.max(1, props.credits.length),
      })}
    />
    <Composition
      id="Showcase"
      component={Showcase}
      defaultProps={{ scenes: [] } as ShowcaseProps}
      durationInFrames={30}
      fps={30}
      width={1920}
      height={1080}
      calculateMetadata={({ props }) => ({
        durationInFrames: Math.max(1, props.scenes.reduce((s, x) => s + Math.round(x.seconds * 30), 0)),
      })}
    />
    <Composition
      id="Thumbnails"
      component={Thumbnails}
      defaultProps={{ variants: [] } as ThumbnailsProps}
      durationInFrames={1}
      fps={30}
      width={1280}
      height={720}
      calculateMetadata={({ props }) => ({ durationInFrames: Math.max(1, props.variants.length) })}
    />
  </>
);
