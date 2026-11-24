import { Fragment } from "react";
import { AbsoluteFill, Audio, getStaticFiles, interpolate, useVideoConfig } from "remotion";
import { linearTiming, TransitionSeries } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { slide } from "@remotion/transitions/slide";
import type { Scene, SceneDoc } from "@demoday/contracts";
import { fitFrames, overlapFrames, totalFrames } from "./timing";
import { TitleScene } from "./scenes/TitleScene";
import { pickLayouts, ScreenScene, type Layout } from "./scenes/ScreenScene";
import { ArchitectureScene } from "./scenes/ArchitectureScene";
import { PointsScene } from "./scenes/PointsScene";
import { theme } from "./theme";

/** 장면 type → 컴포넌트. 새 장면 type은 스키마 → make gen → 여기 case 추가 순서로. */
/** shot = 화면 장면 중 몇 번째인지(0부터), shots = 화면 장면 수 — 화면마다 연출을 바꾸는 데 쓴다. */
function renderScene(scene: Scene, frames: number, domain: string | undefined, shot: number, shots: number, layouts: Layout[], logo?: string) {
  switch (scene.type) {
    case "title":
      return <TitleScene scene={scene} durationInFrames={frames} logo={logo} />;
    case "screen":
      return <ScreenScene scene={scene} domain={domain} durationInFrames={frames} index={shot} count={shots} layout={layouts[shot]} />;
    case "architecture":
      return <ArchitectureScene scene={scene} />;
    case "points":
      return <PointsScene scene={scene} durationInFrames={frames} />;
    default: {
      const never: never = scene;
      throw new Error(`알 수 없는 장면 type: ${JSON.stringify(never)}`);
    }
  }
}

/** 들어오는 장면의 transition으로 앞 장면과 겹쳐 전환한다. fade는 앞 장면 위로 서서히 덮는 크로스페이드. */
function presentation(kind: Scene["transition"], prev?: Scene) {
  // 해결 모션 그래픽 다음은 쓸어 넘기듯 실제 화면으로(#34)
  const fromSolution = prev?.type === "points" && prev.kicker !== "문제";
  return kind === "slide" || fromSolution ? slide({ direction: "from-right" }) : fade();
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
 * logo도 렌더 전용: backend가 배포 사이트에서 받은 run/logo.* (없으면 로고 없이).
 */
export type DemoProps = SceneDoc & { domain?: string; logo?: string } & Record<string, unknown>;

export const Demo: React.FC<DemoProps> = (doc) => {
  const frames = fitFrames(doc);
  const overlap = overlapFrames(doc, frames);
  const shotIndex = doc.scenes.map((_, i) => doc.scenes.slice(0, i).filter((s) => s.type === "screen").length);
  const screens = doc.scenes.flatMap((s) => (s.type === "screen" ? [s] : []));
  const shots = screens.length;
  const layouts = pickLayouts(screens);
  return (
    <AbsoluteFill style={{ background: theme.bg }}>
      <TransitionSeries>
        {doc.scenes.map((scene, i) => (
          <Fragment key={i}>
            {overlap[i] > 0 && (
              <TransitionSeries.Transition
                presentation={presentation(scene.transition, doc.scenes[i - 1])}
                timing={linearTiming({ durationInFrames: overlap[i] })}
              />
            )}
            <TransitionSeries.Sequence durationInFrames={frames[i]}>
              {renderScene(scene, frames[i], doc.domain, shotIndex[i], shots, layouts, doc.logo)}
            </TransitionSeries.Sequence>
          </Fragment>
        ))}
      </TransitionSeries>
      <Bgm total={totalFrames(doc)} />
    </AbsoluteFill>
  );
};
