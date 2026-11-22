import { AbsoluteFill, Audio, getStaticFiles, interpolate, Series, spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { Scene, SceneDoc } from "@demoday/contracts";
import { fitFrames } from "./timing";
import { TitleScene } from "./scenes/TitleScene";
import { ScreenScene } from "./scenes/ScreenScene";
import { ArchitectureScene } from "./scenes/ArchitectureScene";
import { theme } from "./theme";

/** 장면 type → 컴포넌트. 새 장면 type은 스키마 → make gen → 여기 case 추가 순서로. */
function renderScene(scene: Scene, domain?: string) {
  switch (scene.type) {
    case "title":
      return <TitleScene scene={scene} />;
    case "screen":
      return <ScreenScene scene={scene} domain={domain} />;
    case "architecture":
      return <ArchitectureScene scene={scene} />;
    default: {
      const never: never = scene;
      throw new Error(`알 수 없는 장면 type: ${JSON.stringify(never)}`);
    }
  }
}

/** 장면 진입 전환. ponytail: 들어오는 장면만 움직이는 방식이라 앞 장면과 겹치는 크로스페이드는 없다. 필요해지면 @remotion/transitions의 TransitionSeries로 바꾼다. */
const Enter: React.FC<{ kind: Scene["transition"]; children: React.ReactNode }> = ({ kind = "fade", children }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = spring({ frame, fps, config: { damping: 200 }, durationInFrames: Math.round(0.5 * fps) });
  const style =
    kind === "fade" ? { opacity: p } : kind === "slide" ? { transform: `translateX(${interpolate(p, [0, 1], [100, 0])}%)` } : {};
  return <AbsoluteFill style={{ background: theme.bg }}><AbsoluteFill style={style}>{children}</AbsoluteFill></AbsoluteFill>;
};

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
  return (
    <AbsoluteFill style={{ background: theme.bg }}>
      <Series>
        {doc.scenes.map((scene, i) => (
          <Series.Sequence key={i} durationInFrames={frames[i]}>
            <Enter kind={scene.transition}>{renderScene(scene, doc.domain)}</Enter>
          </Series.Sequence>
        ))}
      </Series>
      <Bgm total={frames.reduce((a, b) => a + b, 0)} />
    </AbsoluteFill>
  );
};
