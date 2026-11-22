import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { TitleScene as T } from "@demoday/contracts";

const FONT = "Pretendard, 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif";

export const TitleScene: React.FC<{ scene: T }> = ({ scene }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = spring({ frame, fps, config: { damping: 14, mass: 0.8 } });
  const sub = spring({ frame, fps, delay: 0.4 * fps, config: { damping: 200 } });
  const bar = spring({ frame, fps, delay: 0.2 * fps, config: { damping: 200 } });

  return (
    <AbsoluteFill
      style={{
        background: "radial-gradient(circle at 30% 20%, #1e2a5a 0%, #0b1020 60%)",
        color: "white",
        justifyContent: "center",
        alignItems: "center",
        flexDirection: "column",
        fontFamily: FONT,
      }}
    >
      <div style={{ fontSize: 84, fontWeight: 800, letterSpacing: -1, opacity: t, transform: `scale(${interpolate(t, [0, 1], [0.85, 1])})` }}>
        {scene.text}
      </div>
      <div style={{ width: 160 * bar, height: 6, borderRadius: 3, background: "#facc15", margin: "28px 0" }} />
      {scene.subtitle && (
        <div style={{ fontSize: 36, color: "#cbd5e1", opacity: sub, transform: `translateY(${interpolate(sub, [0, 1], [16, 0])}px)` }}>
          {scene.subtitle}
        </div>
      )}
    </AbsoluteFill>
  );
};
