import { AbsoluteFill } from "remotion";
import type { TitleScene as T } from "@demoday/contracts";

// TODO(B): 타이틀 모션 템플릿
export const TitleScene: React.FC<{ scene: T }> = ({ scene }) => (
  <AbsoluteFill style={{ background: "#0b1020", color: "white", justifyContent: "center", alignItems: "center", fontSize: 72 }}>
    {scene.text}
  </AbsoluteFill>
);
