import { AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { PointsScene as T } from "@demoday/contracts";
import { theme } from "../theme";

type Props = { scene: T };
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
const H = 720;
const CIRCLE = 104;
const GAP = 250; // 해결 줄의 아이콘 간격
const RED = "#e0483e";
/** 문제의 흩어진 자리(가운데 기준 px). 결정적 — 해결은 같은 자리에서 출발해 한 줄로 모인다 */
const SCATTER = [
  { x: -330, y: -95 },
  { x: 250, y: -125 },
  { x: -110, y: 135 },
  { x: 360, y: 125 },
];

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

/** 동그라미 안 아이콘 + 아래 키워드. (x, y)는 동그라미 중심 */
const Node: React.FC<{ x: number; y: number; icon: IconName; text: string; color: string; bg: string; scale: number; opacity: number; rotate?: number; blur?: number; label: number }> = (p) => (
  <div style={{ position: "absolute", left: p.x - 130, top: p.y - CIRCLE / 2, width: 260, display: "flex", flexDirection: "column", alignItems: "center", opacity: p.opacity }}>
    <div
      style={{
        width: CIRCLE,
        height: CIRCLE,
        borderRadius: "50%",
        background: p.bg,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        transform: `scale(${p.scale}) rotate(${p.rotate ?? 0}deg)`,
        filter: p.blur ? `blur(${p.blur}px)` : undefined,
        boxShadow: "0 6px 20px rgba(0,0,0,0.06)",
      }}
    >
      <Icon name={p.icon} size={50} color={p.color} />
    </div>
    <div style={{ marginTop: 18, fontSize: 24, fontWeight: 600, textAlign: "center", lineHeight: 1.3, opacity: p.label }}>{p.text}</div>
  </div>
);

/** 동그라미 오른쪽 위에 찍히는 도장(✕·?·✓). 커졌다 줄어들며 찍힌다 */
const Stamp: React.FC<{ x: number; y: number; p: number; bg: string; mark: "x" | "?" | "check" }> = ({ x, y, p, bg, mark }) => (
  <div
    style={{
      position: "absolute",
      left: x + CIRCLE / 2 - 30,
      top: y - CIRCLE / 2 - 8,
      width: 38,
      height: 38,
      borderRadius: "50%",
      background: bg,
      border: "3px solid #fff",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      opacity: interpolate(p, [0, 0.3], [0, 1], clamp),
      transform: `scale(${interpolate(p, [0, 1], [1.8, 1])})`,
    }}
  >
    <svg width={20} height={20} viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth={3.2} strokeLinecap="round" strokeLinejoin="round">
      {mark === "x" ? <path d="M6 6l12 12M18 6 6 18" /> : mark === "check" ? <path d="m5 12 5 5 9-10" /> : <path d="M9 9a3 3 0 1 1 4 2.8c-.7.3-1 .9-1 1.6V14M12 18h.01" />}
    </svg>
  </div>
);

/**
 * 소개 모션 그래픽 — 글은 최소로, 움직임과 아이콘이 이야기한다(#34).
 * - "문제": 흩어진 회색 아이콘이 흔들리며 흐려지고 빨간 ✕·?가 찍힌다 (막힌 상태)
 * - 그 외("해결"·없음): 같은 흩어진 자리에서 한 줄로 정렬되고, 선으로 이어진 뒤 체크가 찍힌다
 * heading은 왼쪽 위 작은 한 줄, 키워드는 아이콘 아래 작게.
 */
export const PointsScene: React.FC<Props> = ({ scene }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = (sec: number) => sec * fps;
  const problem = scene.kicker === "문제";
  const items = scene.items.slice(0, SCATTER.length);
  const n = items.length;
  const head = spring({ frame, fps, config: { damping: 200 } });
  const row = (i: number) => ({ x: W / 2 + (i - (n - 1) / 2) * GAP, y: H / 2 + 10 });
  const scatter = (i: number) => ({ x: W / 2 + SCATTER[i].x, y: H / 2 + 20 + SCATTER[i].y });

  // 해결: 줄 정렬이 끝나면 선이 왼쪽부터 그어진다
  const line = interpolate(frame, [t(1.0), t(1.6)], [0, 1], { ...clamp, easing: Easing.inOut(Easing.cubic) });
  const first = row(0);
  const last = row(n - 1);

  return (
    <AbsoluteFill style={{ background: theme.bg, color: theme.ink, fontFamily: theme.font, ...theme.keepAll }}>
      <div style={{ position: "absolute", left: 80, top: 64, display: "flex", alignItems: "baseline", gap: 16, opacity: head }}>
        {scene.kicker && <span style={{ fontSize: 22, fontWeight: 700, color: problem ? RED : theme.accent }}>{scene.kicker}</span>}
        <span style={{ fontSize: 26, fontWeight: 600, color: theme.sub }}>{scene.heading}</span>
      </div>

      {!problem && n > 1 && (
        <div
          style={{
            position: "absolute",
            left: first.x,
            top: first.y - 2,
            width: (last.x - first.x) * line,
            height: 4,
            borderRadius: 2,
            background: theme.accent,
            opacity: 0.5,
          }}
        />
      )}

      {items.map((item, i) => {
        const pop = spring({ frame, fps, delay: t(0.1 + 0.12 * i), config: { damping: 14 } });
        if (problem) {
          const { x, y } = scatter(i);
          // 흔들림: 프레임 기반 사인 — 결정적
          const dx = Math.sin(frame / 5 + i * 2.1) * 5;
          const dy = Math.cos(frame / 7 + i * 1.3) * 4;
          const fade = interpolate(frame, [t(1.2), t(2.6)], [0, 1], clamp);
          const stamp = spring({ frame, fps, delay: t(0.9 + 0.25 * i), config: { damping: 12 } });
          return (
            <div key={i}>
              <Node
                x={x + dx}
                y={y + dy}
                icon={item.icon}
                text={item.text}
                color={theme.sub}
                bg="#e7e6e1"
                scale={pop}
                opacity={interpolate(fade, [0, 1], [1, 0.55])}
                rotate={Math.sin(frame / 9 + i) * 7}
                blur={fade * 1.5}
                label={pop}
              />
              <Stamp x={x + dx} y={y + dy} p={stamp} bg={RED} mark={i % 2 ? "?" : "x"} />
            </div>
          );
        }
        const from = scatter(i);
        const to = row(i);
        const go = spring({ frame, fps, delay: t(0.25 + 0.06 * i), config: { damping: 200 }, durationInFrames: t(0.8) });
        const x = interpolate(go, [0, 1], [from.x, to.x]);
        const y = interpolate(go, [0, 1], [from.y, to.y]);
        const check = spring({ frame, fps, delay: t(1.5 + 0.15 * i), config: { damping: 12 } });
        return (
          <div key={i}>
            <Node x={x} y={y} icon={item.icon} text={item.text} color={theme.accent} bg="#fde9dc" scale={pop} opacity={1} label={go} />
            <Stamp x={x} y={y} p={check} bg="#2f9e5b" mark="check" />
          </div>
        );
      })}
    </AbsoluteFill>
  );
};
