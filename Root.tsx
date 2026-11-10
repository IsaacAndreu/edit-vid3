import type { CSSProperties, FC } from 'react';
import { AbsoluteFill, Audio, Composition, Img, Sequence, Video } from 'remotion';
import { templates } from './templates/registry';
import { resolveMediaUrl } from './templates/media';
import type { SceneInput, VideoProps } from './templates/types';

export const FPS = 30;
export const VIDEO_WIDTH = 1920;
export const VIDEO_HEIGHT = 1080;

export const getTotalDurationInFrames = (scenes: SceneInput[]): number =>
  scenes.reduce((total, scene) => total + scene.durationInFrames, 0);

const missingTemplateStyle: CSSProperties = {
  alignItems: 'center',
  backgroundColor: '#050505',
  color: '#f5f5f5',
  display: 'flex',
  fontFamily: 'Arial, sans-serif',
  fontSize: 36,
  height: '100%',
  justifyContent: 'center',
  padding: 64,
  textAlign: 'center',
  width: '100%',
};

const MEDIA_BACKED_OVERLAY_TEMPLATES = new Set([
  'kinetic-text-hook',
  'lower-third',
  'stat-overlay',
]);

const backgroundMediaStyle: CSSProperties = {
  height: '100%',
  objectFit: 'cover',
  position: 'absolute',
  width: '100%',
};

const SceneBackground: FC<{ scene: SceneInput }> = ({ scene }) => {
  const source = scene.videoUrl || scene.imageUrl;

  if (!source) {
    return <AbsoluteFill style={{ backgroundColor: '#09090b' }} />;
  }

  return (
    <AbsoluteFill style={{ backgroundColor: '#09090b' }}>
      {scene.videoUrl ? (
        <Video loop={scene.mediaProvider !== 'youtube'} muted src={resolveMediaUrl(source)} style={backgroundMediaStyle} />
      ) : (
        <Img src={resolveMediaUrl(source)} style={backgroundMediaStyle} />
      )}
      <AbsoluteFill
        style={{
          background: 'linear-gradient(90deg, rgba(0, 0, 0, 0.3), rgba(0, 0, 0, 0.08) 58%, rgba(0, 0, 0, 0.28))',
        }}
      />
    </AbsoluteFill>
  );
};

const SceneRenderer: FC<{ scene: SceneInput }> = ({ scene }) => {
  const Template = templates[scene.templateName];

  if (!Template) {
    return (
      <div style={missingTemplateStyle}>
        Missing template: <strong>&nbsp;{scene.templateName}</strong>
      </div>
    );
  }

  const { templateName: _templateName, ...sceneProps } = scene;

  return <Template {...sceneProps} />;
};

export const YoutubeVideo: FC<VideoProps> = ({ audioUrl, scenes }) => {
  let from = 0;

  return (
    <AbsoluteFill>
      {audioUrl ? <Audio src={resolveMediaUrl(audioUrl)} /> : null}
      {scenes.map((scene, index) => {
        const sceneStart = from;
        from += scene.durationInFrames;

        return (
          <Sequence
            key={`${scene.templateName}-${index}`}
            from={sceneStart}
            durationInFrames={scene.durationInFrames}
          >
            <AbsoluteFill>
              {MEDIA_BACKED_OVERLAY_TEMPLATES.has(scene.templateName) ||
              (scene.templateName === 'kenburns-image' && Boolean(scene.videoUrl) && !scene.imageUrl) ? (
                <SceneBackground scene={scene} />
              ) : null}
              <SceneRenderer scene={scene} />
            </AbsoluteFill>
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};

export const RemotionRoot: FC = () => (
  <Composition
    id="YoutubeVideo"
    component={YoutubeVideo}
    durationInFrames={1}
    fps={FPS}
    width={VIDEO_WIDTH}
    height={VIDEO_HEIGHT}
    defaultProps={{ scenes: [] }}
    calculateMetadata={({ props }) => ({
      durationInFrames: Math.max(1, getTotalDurationInFrames(props.scenes)),
    })}
  />
);
