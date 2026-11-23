import { Composition } from "remotion";
import fixture from "@demoday/contracts/fixtures/scene.json";
import { Demo, type DemoProps } from "./Demo";
import { totalFrames } from "./timing";

export const Root: React.FC = () => (
  <Composition
    id="Demo"
    component={Demo}
    width={1280}
    height={720}
    fps={30}
    durationInFrames={1}
    defaultProps={fixture as DemoProps}
    calculateMetadata={({ props }) => ({
      fps: props.fps,
      durationInFrames: totalFrames(props),
    })}
  />
);
