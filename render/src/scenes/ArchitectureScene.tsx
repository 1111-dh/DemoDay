import { AbsoluteFill } from "remotion";
import type { ArchitectureScene as T } from "@demoday/contracts";

// TODO(C): 노드·연결 애니메이션 다이어그램
export const ArchitectureScene: React.FC<{ scene: T }> = ({ scene }) => (
  <AbsoluteFill style={{ background: "#0b1020", color: "white", justifyContent: "center", alignItems: "center", gap: 24, flexDirection: "row", fontSize: 36 }}>
    {scene.nodes.map((n, i) => (
      <span key={i}>{i > 0 ? "→ " : ""}{n}</span>
    ))}
  </AbsoluteFill>
);
