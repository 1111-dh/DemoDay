import { AbsoluteFill, Img, staticFile } from "remotion";
import type { ScreenScene as T } from "@demoday/contracts";

// TODO(B): 줌·커서 이동·클릭 하이라이트·자막 모션. 좌표는 캡처 viewport(1280x720) 기준 px.
export const ScreenScene: React.FC<{ scene: T }> = ({ scene }) => (
  <AbsoluteFill style={{ background: "black" }}>
    <Img src={staticFile(`run/${scene.image}`)} style={{ width: "100%", height: "100%" }} />
    {scene.caption && (
      <div style={{ position: "absolute", bottom: 48, width: "100%", textAlign: "center", color: "white", fontSize: 40 }}>
        {scene.caption}
      </div>
    )}
  </AbsoluteFill>
);
