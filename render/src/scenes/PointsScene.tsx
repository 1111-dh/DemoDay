import { AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { PointsScene as T } from "@demoday/contracts";
import { theme } from "../theme";
import { Backdrop, fitFont, Pill, Words } from "../motion";
import { ProblemStory } from "./ProblemStory";

type Props = { scene: T; durationInFrames: number };
type IconName = T["items"][number]["icon"];

/** 24x24 선 아이콘(stroke 2). 계약의 Icon enum과 1:1 — 하나라도 빠지면 Record 타입에서 typecheck가 실패한다. */
const ICONS: Record<IconName, React.ReactNode> = {
  clock: (<><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>),
  alert: (<><path d="M12 3 2 20h20Z" /><path d="M12 9v5M12 17h.01" /></>),
  search: (<><circle cx="11" cy="11" r="7" /><path d="m20 20-4-4" /></>),
  document: (<><path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8Z" /><path d="M14 3v5h5M9 13h6M9 17h6" /></>),
  chart: (<><path d="M4 4v16h16" /><path d="M8 16v-4M12 16V8M16 16v-6" /></>),
  user: (<><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></>),
  team: (<><circle cx="9" cy="8" r="3.5" /><path d="M2 20a7 7 0 0 1 14 0M16 4.5a3.5 3.5 0 0 1 0 7M18 14a7 7 0 0 1 4 6" /></>),
  check: (<><circle cx="12" cy="12" r="9" /><path d="m8 12 3 3 5-6" /></>),
  bolt: <path d="M13 2 4 14h7l-1 8 9-12h-7Z" />,
  money: (<><rect x="2" y="6" width="20" height="12" rx="2" /><circle cx="12" cy="12" r="3" /><path d="M6 12h.01M18 12h.01" /></>),
  chat: <path d="M21 12a8 8 0 0 1-11.6 7.1L4 21l1.9-5.4A8 8 0 1 1 21 12Z" />,
  calendar: (<><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M3 10h18M8 3v4M16 3v4" /></>),
  map: (<><path d="M12 21s7-6.2 7-12a7 7 0 0 0-14 0c0 5.8 7 12 7 12Z" /><circle cx="12" cy="9" r="2.5" /></>),
  store: (<><path d="M3 4h18l-1.5 6h-15Z" /><path d="M4 10v10h16V10M10 20v-5h4v5" /></>),
  ai: (<><path d="m12 3 1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8Z" /><path d="m19 15 .8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8Z" /></>),
};

const Icon: React.FC<{ name: IconName; size: number; color: string }> = ({ name, size, color }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
    {ICONS[name]}
  </svg>
);


const W = 1280;
const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

/** 카드 오른쪽 위에 찍히는 도장(✕·✓). 크게 찍혔다가 제자리로 줄어든다 */
const Stamp: React.FC<{ p: number; bg: string; mark: "x" | "check" }> = ({ p, bg, mark }) => (
  <div
    style={{
      position: "absolute",
      right: -14,
      top: -14,
      width: 52,
      height: 52,
      borderRadius: "50%",
      background: bg,
      border: "4px solid white",
      boxShadow: "0 8px 20px rgba(0,0,0,0.25)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      opacity: interpolate(p, [0, 0.25], [0, 1], clamp),
      transform: `scale(${interpolate(p, [0, 1], [2.2, 1])}) rotate(${interpolate(p, [0, 1], [-30, 0])}deg)`,
    }}
  >
    <svg width={26} height={26} viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth={3.4} strokeLinecap="round" strokeLinejoin="round">
      {mark === "x" ? <path d="M6 6l12 12M18 6 6 18" /> : <path d="m5 12 5 5 9-10" />}
    </svg>
  </div>
);

/**
 * 소개 모션 그래픽 — 큰 카드에 아이콘과 키워드, 움직임이 이야기한다(#34, 11/24 "잘 보이게").
 * - "문제": 어두운 배경. 카드가 떨어지듯 들어와 흔들리고, 빨간 ✕가 찍히며 키워드에 취소선이 그어진다
 * - 그 외("해결"): 밝은 배경. 카드가 차례로 솟아오르고, 뒤로 주황 선이 이어지며 ✓가 찍히고 빛이 훑고 지나간다
 */
export const PointsScene: React.FC<Props> = (props) =>
  props.scene.kicker === "문제" ? <ProblemStory scene={props.scene} durationInFrames={props.durationInFrames} /> : <SolutionCards {...props} />;

/** 해결 카드 장면(문제 장면은 ProblemStory가 가상 인터넷 화면으로 그린다). */
const SolutionCards: React.FC<Props> = ({ scene, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = (sec: number) => sec * fps;
  const problem = scene.kicker === "문제";
  const items = scene.items.slice(0, 4);
  const n = items.length;
  const cardW = n >= 4 ? 236 : 268;
  const gap = n >= 4 ? 34 : 48;
  const rowW = n * cardW + (n - 1) * gap;
  const left0 = (W - rowW) / 2;
  const color = problem ? theme.red : theme.accent;
  const settle = 0.5 + 0.14 * n; // 카드가 다 들어오는 시각
  const line = interpolate(frame, [t(settle), t(settle + 0.6)], [0, 1], { ...clamp, easing: Easing.inOut(Easing.cubic) });
  const sweepX = interpolate(frame, [t(settle + 1.0), t(settle + 2.0)], [left0 - 200, left0 + rowW + 200], clamp);
  const drift = interpolate(frame, [0, durationInFrames], [1, 1.035]);

  return (
    <AbsoluteFill style={{ fontFamily: theme.font, color: problem ? "white" : theme.ink, ...theme.keepAll }}>
      <Backdrop seed={problem ? 3 : 1} dark={problem} />
      <AbsoluteFill style={{ transform: `scale(${drift})` }}>
        <div style={{ position: "absolute", top: 92, left: 0, right: 0, display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center" }}>
          {scene.kicker && <Pill text={scene.kicker} color={color} light={problem} />}
          <Words text={scene.heading} delay={0.15} style={{ marginTop: 24, fontSize: fitFont(scene.heading, 1000, 50), fontWeight: 700, letterSpacing: "-0.03em", justifyContent: "center", maxWidth: 1080 }} />
        </div>

        {!problem && n > 1 && (
          <div
            style={{
              position: "absolute",
              left: left0 + cardW / 2,
              top: 462,
              width: (rowW - cardW) * line,
              height: 6,
              borderRadius: 3,
              background: `linear-gradient(90deg, ${theme.accent}, #ffb37a)`,
            }}
          />
        )}

        {items.map((item, i) => {
          const x = left0 + i * (cardW + gap);
          const enter = spring({ frame, fps, delay: t(0.35 + 0.14 * i), config: { damping: problem ? 11 : 16, mass: 0.8 } });
          const stamp = spring({ frame, fps, delay: t(settle + 0.3 + 0.18 * i), config: { damping: 11 } });
          const strike = interpolate(frame, [t(settle + 0.45 + 0.18 * i), t(settle + 0.75 + 0.18 * i)], [0, 1], clamp);
          const jitter = problem ? Math.sin(frame / 4 + i * 2.3) * 2.2 * stamp : 0;
          const glow = problem ? 0 : Math.max(0, 1 - Math.abs(sweepX - (x + cardW / 2)) / 220);
          const float = Math.sin(frame / 22 + i * 1.4) * 4;
          return (
            <div
              key={i}
              style={{
                position: "absolute",
                left: x,
                top: 330,
                width: cardW,
                height: 264,
                borderRadius: 30,
                background: problem ? "rgba(255,255,255,0.06)" : "white",
                border: problem ? "1.5px solid rgba(255,255,255,0.14)" : "1.5px solid rgba(242,107,29,0.14)",
                boxShadow: problem
                  ? "0 20px 50px rgba(0,0,0,0.35)"
                  : `0 20px 50px rgba(0,0,0,0.08), 0 0 ${60 * glow}px rgba(242,107,29,${0.55 * glow})`,
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                gap: 26,
                opacity: interpolate(enter, [0, 0.3], [0, 1], clamp),
                transform: `perspective(900px) translateY(${interpolate(enter, [0, 1], [problem ? -120 : 140, 0]) + float}px) rotateX(${interpolate(enter, [0, 1], [problem ? -35 : 35, 0])}deg) rotate(${jitter}deg) scale(${1 + glow * 0.04})`,
              }}
            >
              <div style={{ position: "absolute", left: 22, top: 18, fontSize: 18, fontWeight: 700, color: problem ? "rgba(255,255,255,0.35)" : "rgba(242,107,29,0.55)" }}>
                {String(i + 1).padStart(2, "0")}
              </div>
              <div
                style={{
                  width: 112,
                  height: 112,
                  borderRadius: "50%",
                  background: problem ? "rgba(224,72,62,0.16)" : "linear-gradient(135deg, #fde3d2, #fff1e7)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <Icon name={item.icon} size={56} color={problem ? "#ff8a7a" : theme.accent} />
              </div>
              <div style={{ position: "relative", fontSize: fitFont(item.text, cardW - 40, 30), fontWeight: 700, textAlign: "center", lineHeight: 1.25, padding: "0 18px", maxWidth: cardW, overflowWrap: "anywhere", opacity: problem ? interpolate(strike, [0, 1], [1, 0.6]) : 1 }}>
                {item.text}
                {problem && (
                  <div style={{ position: "absolute", left: 14, top: "52%", height: 4, borderRadius: 2, width: `calc(${strike * 100}% - 28px)`, background: theme.red }} />
                )}
              </div>
              <Stamp p={stamp} bg={problem ? theme.red : theme.green} mark={problem ? "x" : "check"} />
            </div>
          );
        })}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
