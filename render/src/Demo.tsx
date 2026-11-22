import { AbsoluteFill, interpolate, Series, spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { Scene, SceneDoc } from "@demoday/contracts";
import { fitFrames } from "./timing";
import { TitleScene } from "./scenes/TitleScene";
import { ScreenScene } from "./scenes/ScreenScene";
import { ArchitectureScene } from "./scenes/ArchitectureScene";

/** 장면 type → 컴포넌트. 새 장면 type은 스키마 → make gen → 여기 case 추가 순서로. */
function renderScene(scene: Scene) {
  switch (scene.type) {
    case "title":
      return <TitleScene scene={scene} />;
    case "screen":
      return <ScreenScene scene={scene} />;
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
  return <AbsoluteFill style={{ background: "black" }}><AbsoluteFill style={style}>{children}</AbsoluteFill></AbsoluteFill>;
};

/** Remotion은 props가 Record<string, unknown>을 만족해야 한다. */
export type DemoProps = SceneDoc & Record<string, unknown>;

export const Demo: React.FC<DemoProps> = (doc) => {
  const frames = fitFrames(doc);
  return (
    <Series>
      {doc.scenes.map((scene, i) => (
        <Series.Sequence key={i} durationInFrames={frames[i]}>
          <Enter kind={scene.transition}>{renderScene(scene)}</Enter>
        </Series.Sequence>
      ))}
    </Series>
  );
};
