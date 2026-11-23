import { AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { TitleScene as T } from "@demoday/contracts";
import { theme } from "../theme";
import { Backdrop, Pill, Words } from "../motion";

type Props = { scene: T; durationInFrames: number };

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

/** 오른쪽 장식: 선이 그려지며 도는 동심원 호 + 가운데 이니셜 배지. */
const Rings: React.FC<{ letter: string }> = ({ letter }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const draw = (delay: number) => interpolate(frame, [delay * fps, (delay + 1.2) * fps], [1, 0], { ...clamp, easing: Easing.out(Easing.cubic) });
  const badge = spring({ frame, fps, delay: 0.5 * fps, config: { damping: 12 } });
  const rings = [
    { r: 190, w: 3, d: 0.1, op: 0.5, dash: 0.72 },
    { r: 150, w: 10, d: 0.25, op: 0.9, dash: 0.32 },
    { r: 230, w: 1.5, d: 0.4, op: 0.35, dash: 0.9 },
  ];
  return (
    <div style={{ position: "absolute", right: 70, top: 360 - 260, width: 520, height: 520 }}>
      <svg width={520} height={520} viewBox="-260 -260 520 520" style={{ position: "absolute", inset: 0 }}>
        {rings.map((g, i) => {
          const c = 2 * Math.PI * g.r;
          return (
            <circle
              key={i}
              r={g.r}
              fill="none"
              stroke={theme.accent}
              strokeWidth={g.w}
              strokeLinecap="round"
              opacity={g.op}
              strokeDasharray={`${c * g.dash} ${c}`}
              strokeDashoffset={c * g.dash * draw(g.d)}
              transform={`rotate(${-90 + frame * (i % 2 ? -0.35 : 0.5)})`}
            />
          );
        })}
      </svg>
      <div
        style={{
          position: "absolute",
          left: 260 - 80,
          top: 260 - 80,
          width: 160,
          height: 160,
          borderRadius: 44,
          background: `linear-gradient(135deg, ${theme.accent}, #ff9a52)`,
          boxShadow: "0 24px 60px rgba(242,107,29,0.35)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "white",
          fontSize: 84,
          fontWeight: 700,
          transform: `scale(${badge}) rotate(${interpolate(badge, [0, 1], [-20, 0])}deg)`,
        }}
      >
        {letter}
      </div>
    </div>
  );
};

/**
 * 오프닝 타이틀: 큰 서비스 이름이 단어별로 솟아오르고, 오른쪽에 선이 그려지는 원 장식.
 * kicker가 있으면 장 구분 카드(문제·정리): 라벨 알약 + 큰 문장 + 밑줄이 그어진다.
 * 장면 내내 아주 천천히 다가가 정지 화면처럼 보이지 않게 한다.
 */
export const TitleScene: React.FC<Props> = ({ scene, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const chapter = Boolean(scene.kicker);
  const problem = scene.kicker === "문제";
  const drift = interpolate(frame, [0, durationInFrames], [1, 1.04]);
  const bar = spring({ frame, fps, delay: 0.05 * fps, config: { damping: 200 } });
  const words = scene.text.split(/\s+/).length;
  const underline = interpolate(frame, [(0.35 + words * 0.07) * fps, (0.95 + words * 0.07) * fps], [0, 1], {
    ...clamp,
    easing: Easing.inOut(Easing.cubic),
  });
  const color = problem ? theme.red : theme.accent;

  return (
    <AbsoluteFill style={{ fontFamily: theme.font, color: problem ? "white" : theme.ink, ...theme.keepAll }}>
      <Backdrop seed={chapter ? 2 : 0} dark={problem} />
      <AbsoluteFill style={{ transform: `scale(${drift})`, transformOrigin: "30% 50%" }}>
        {chapter ? (
          <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", padding: "0 140px", textAlign: "center" }}>
            <Pill text={scene.kicker ?? ""} color={color} light={problem} />
            <div style={{ position: "relative", marginTop: 34 }}>
              <Words text={scene.text} delay={0.2} style={{ fontSize: 70, fontWeight: 700, letterSpacing: "-0.03em", lineHeight: 1.22, justifyContent: "center", maxWidth: 1000 }} />
              <div
                style={{
                  margin: "26px auto 0",
                  width: 220 * underline,
                  height: 8,
                  borderRadius: 4,
                  background: `linear-gradient(90deg, ${color}, ${problem ? "#ff8a7a" : "#ffb37a"})`,
                }}
              />
            </div>
          </AbsoluteFill>
        ) : (
          <AbsoluteFill style={{ justifyContent: "center", alignItems: "flex-start", padding: "0 120px" }}>
            <div style={{ width: 72 * bar, height: 8, borderRadius: 4, background: theme.accent, marginBottom: 36 }} />
            <Words text={scene.text} delay={0.1} stagger={0.09} style={{ fontSize: 92, fontWeight: 700, letterSpacing: "-0.035em", lineHeight: 1.12, maxWidth: 640 }} />
            {scene.subtitle && (
              <Words text={scene.subtitle} delay={0.6} stagger={0.05} style={{ fontSize: 32, fontWeight: 500, color: theme.sub, marginTop: 30, maxWidth: 600, lineHeight: 1.4 }} />
            )}
            <Rings letter={[...scene.text.trim()][0] ?? "D"} />
          </AbsoluteFill>
        )}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
