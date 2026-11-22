import { Series } from "remotion";
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

/** Remotion은 props가 Record<string, unknown>을 만족해야 한다. */
export type DemoProps = SceneDoc & Record<string, unknown>;

export const Demo: React.FC<DemoProps> = (doc) => {
  const frames = fitFrames(doc);
  return (
    <Series>
      {doc.scenes.map((scene, i) => (
        <Series.Sequence key={i} durationInFrames={frames[i]}>
          {renderScene(scene)}
        </Series.Sequence>
      ))}
    </Series>
  );
};
