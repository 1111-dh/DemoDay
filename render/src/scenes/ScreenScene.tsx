import { AbsoluteFill, Easing, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import type { ScreenScene as T } from "@demoday/contracts";

const W = 1280;
const H = 720;

/**
 * 캡처 화면 + 커서 이동 → 클릭 하이라이트 → 줌 인 + 자막.
 * 좌표는 캡처 viewport(1280x720) 기준 px. Composition도 같은 크기라 그대로 쓴다.
 */
export const ScreenScene: React.FC<{ scene: T }> = ({ scene }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = (sec: number) => sec * fps;

  // 타임라인: 0~0.8초 커서 이동, 0.8초 클릭, 1초부터 줌
  const cursor = scene.cursor;
  const move = interpolate(frame, [s(0.1), s(0.8)], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.cubic),
  });
  const press = spring({ frame, fps, delay: s(0.8), config: { damping: 200 }, durationInFrames: s(0.6) });

  const zoom = scene.zoom;
  const z = zoom ? spring({ frame, fps, delay: cursor ? s(1) : s(0.3), config: { damping: 200 }, durationInFrames: s(1) }) : 0;
  const scale = zoom ? interpolate(z, [0, 1], [1, zoom.scale]) : 1;

  return (
    <AbsoluteFill style={{ background: "black", overflow: "hidden" }}>
      {/* 줌 기준점을 원점으로 잡으면 scale ≥ 1에서도 화면이 비지 않는다 */}
      <AbsoluteFill style={{ transform: `scale(${scale})`, transformOrigin: zoom ? `${zoom.x}px ${zoom.y}px` : "center" }}>
        <Img src={staticFile(`run/${scene.image}`)} style={{ width: W, height: H }} />
        {cursor && (
          <>
            <div
              style={{
                position: "absolute",
                left: cursor.x,
                top: cursor.y,
                width: 80,
                height: 80,
                marginLeft: -40,
                marginTop: -40,
                borderRadius: "50%",
                border: "4px solid #facc15",
                background: "rgba(250, 204, 21, 0.25)",
                transform: `scale(${interpolate(press, [0, 1], [0.2, 1.2])})`,
                opacity: interpolate(press, [0, 0.1, 1], [0, 1, 0.35]),
              }}
            />
            <Cursor
              x={interpolate(move, [0, 1], [W * 0.62, cursor.x])}
              y={interpolate(move, [0, 1], [H * 0.78, cursor.y])}
              pressed={frame >= s(0.8) && frame < s(0.95)}
            />
          </>
        )}
      </AbsoluteFill>
      {scene.caption && <Caption text={scene.caption} />}
    </AbsoluteFill>
  );
};

const Cursor: React.FC<{ x: number; y: number; pressed: boolean }> = ({ x, y, pressed }) => (
  <svg
    width={32}
    height={32}
    viewBox="0 0 24 24"
    style={{ position: "absolute", left: x, top: y, transform: `scale(${pressed ? 0.85 : 1})`, transformOrigin: "0 0", filter: "drop-shadow(0 2px 3px rgba(0,0,0,0.45))" }}
  >
    <path d="M2 1 L2 19 L7 14.5 L10.5 22 L13.5 20.7 L10 13.3 L16.5 13.3 Z" fill="white" stroke="black" strokeWidth={1.4} strokeLinejoin="round" />
  </svg>
);

const Caption: React.FC<{ text: string }> = ({ text }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = spring({ frame, fps, delay: 0.3 * fps, config: { damping: 200 } });
  return (
    <AbsoluteFill style={{ justifyContent: "flex-end", alignItems: "center", paddingBottom: 48 }}>
      <div
        style={{
          maxWidth: W * 0.8,
          padding: "14px 28px",
          borderRadius: 14,
          background: "rgba(11, 16, 32, 0.82)",
          color: "white",
          fontSize: 36,
          fontWeight: 600,
          fontFamily: "Pretendard, 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif",
          textAlign: "center",
          lineHeight: 1.35,
          opacity: p,
          transform: `translateY(${interpolate(p, [0, 1], [24, 0])}px)`,
        }}
      >
        {text}
      </div>
    </AbsoluteFill>
  );
};
