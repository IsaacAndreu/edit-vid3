import type { FC } from "react";
import { AbsoluteFill, Composition, useCurrentFrame } from "remotion";
import { CreditBadge } from "./components/CreditBadge";
import { Thumbnail, type ThumbnailVariant } from "./components/Thumbnail";
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
  [key: string]: unknown;
}

/** Frame i = credit badge i on a transparent background (the render stage overlays it with ffmpeg). */
const Badges: FC<BadgesProps> = ({ credits }) => {
  const credit = credits[useCurrentFrame()];
  return (
    <AbsoluteFill>
      {credit ? <CreditBadge credit={credit} /> : null}
    </AbsoluteFill>
  );
};

interface ThumbnailsProps {
  variants: ThumbnailVariant[];
  [key: string]: unknown;
}

/** Frame i = thumbnail variant i (rendered as an image sequence by the package stage). */
const Thumbnails: FC<ThumbnailsProps> = ({ variants }) => {
  const variant = variants[useCurrentFrame()];
  return variant ? <Thumbnail variant={variant} /> : <AbsoluteFill />;
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
