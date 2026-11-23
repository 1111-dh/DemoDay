import { Fragment } from "react";
import { AbsoluteFill, Audio, getStaticFiles, interpolate, useVideoConfig } from "remotion";
import { linearTiming, TransitionSeries } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { slide } from "@remotion/transitions/slide";
import type { Scene, SceneDoc } from "@demoday/contracts";
import { fitFrames, overlapFrames, totalFrames } from "./timing";
import { TitleScene } from "./scenes/TitleScene";
import { ScreenScene } from "./scenes/ScreenScene";
import { ArchitectureScene } from "./scenes/ArchitectureScene";
import { theme } from "./theme";

/** 장면 type → 컴포넌트. 새 장면 type은 스키마 → make gen → 여기 case 추가 순서로. */
function renderScene(scene: Scene, frames: number, domain?: string) {
  switch (scene.type) {
    case "title":
      return <TitleScene scene={scene} />;
    case "screen":
      return <ScreenScene scene={scene} domain={domain} durationInFrames={frames} />;
    case "architecture":
      return <ArchitectureScene scene={scene} />;
    default: {
      const never: never = scene;
      throw new Error(`알 수 없는 장면 type: ${JSON.stringify(never)}`);
    }
  }
}

/** 들어오는 장면의 transition으로 앞 장면과 겹쳐 전환한다. fade는 앞 장면 위로 서서히 덮는 크로스페이드. */
function presentation(kind: Scene["transition"]) {
  return kind === "slide" ? slide({ direction: "from-right" }) : fade();
}

/** 배경음악: public/bgm.mp3가 있을 때만. 낮은 볼륨, 앞 1초 페이드인·끝 2초 페이드아웃. */
const Bgm: React.FC<{ total: number }> = ({ total }) => {
  const { fps } = useVideoConfig();
  const file = getStaticFiles().find((f) => f.name === "bgm.mp3");
  if (!file) return null;
  const fadeOut = Math.max(fps + 1, total - 2 * fps);
  return (
    <Audio
      src={file.src}
      loop
      // 반복돼도 volume 콜백의 프레임이 0으로 돌아가지 않게(기본값 repeat이면 끝 페이드아웃이 안 됨)
      loopVolumeCurveBehavior="extend"
      volume={(f) => interpolate(f, [0, fps, fadeOut, total], [0, 0.18, 0.18, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })}
    />
  );
};

/**
 * Remotion은 props가 Record<string, unknown>을 만족해야 한다.
 * domain은 계약 밖 렌더 전용 값: render.mjs가 run의 scenario.json baseUrl에서 넣는다(없으면 주소창 비움).
 */
export type DemoProps = SceneDoc & { domain?: string } & Record<string, unknown>;

export const Demo: React.FC<DemoProps> = (doc) => {
  const frames = fitFrames(doc);
  const overlap = overlapFrames(doc, frames);
  return (
    <AbsoluteFill style={{ background: theme.bg }}>
      <TransitionSeries>
        {doc.scenes.map((scene, i) => (
          <Fragment key={i}>
            {overlap[i] > 0 && (
              <TransitionSeries.Transition
                presentation={presentation(scene.transition)}
                timing={linearTiming({ durationInFrames: overlap[i] })}
              />
            )}
            <TransitionSeries.Sequence durationInFrames={frames[i]}>
              {renderScene(scene, frames[i], doc.domain)}
            </TransitionSeries.Sequence>
          </Fragment>
        ))}
      </TransitionSeries>
      <Bgm total={totalFrames(doc)} />
    </AbsoluteFill>
  );
};
