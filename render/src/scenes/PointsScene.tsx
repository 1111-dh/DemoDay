import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
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

/**
 * 소개 그래픽. kicker "해결"이면 주황 강조 카드를 가로로, 그 외("문제"·없음)는 카드를 세로로 나열한다.
 * "문제"는 회색 아이콘으로 톤을 낮춘다. 카드는 0.3초 뒤부터 0.15초 간격으로 하나씩 들어온다.
 */
export const PointsScene: React.FC<Props> = ({ scene }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const solution = scene.kicker === "해결";
  const problem = scene.kicker === "문제";
  const iconColor = problem ? theme.sub : theme.accent;
  const iconBg = problem ? "#e7e6e1" : "#fde9dc";
  const head = spring({ frame, fps, config: { damping: 200 } });
  const rise = (p: number, px = 20) => `translateY(${interpolate(p, [0, 1], [px, 0])}px)`;

  return (
    <AbsoluteFill
      style={{
        background: theme.bg,
        color: theme.ink,
        fontFamily: theme.font,
        ...theme.keepAll,
        justifyContent: "center",
        padding: "0 140px",
      }}
    >
      {scene.kicker && (
        <div style={{ fontSize: 22, fontWeight: 600, color: problem ? theme.sub : theme.accent, opacity: head, marginBottom: 16 }}>
          {scene.kicker}
        </div>
      )}
      <div style={{ fontSize: 52, fontWeight: 700, letterSpacing: "-0.02em", lineHeight: 1.25, opacity: head, transform: rise(head) }}>
        {scene.heading}
      </div>
      <div style={{ display: "flex", flexDirection: solution ? "row" : "column", gap: solution ? 24 : 16, marginTop: 44, maxWidth: solution ? undefined : 820 }}>
        {scene.items.map((item, i) => {
          const p = spring({ frame, fps, delay: (0.3 + 0.15 * i) * fps, config: { damping: 200 } });
          return (
            <div
              key={i}
              style={{
                flex: solution ? 1 : undefined,
                display: "flex",
                flexDirection: solution ? "column" : "row",
                alignItems: solution ? "flex-start" : "center",
                gap: solution ? 20 : 22,
                padding: solution ? "28px 28px 32px" : "18px 24px",
                background: "#fff",
                borderRadius: 16,
                boxShadow: "0 1px 2px rgba(0,0,0,0.04), 0 6px 20px rgba(0,0,0,0.05)",
                opacity: p,
                transform: rise(p, 28),
              }}
            >
              <div style={{ width: 56, height: 56, borderRadius: 14, background: iconBg, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                <Icon name={item.icon} size={30} color={iconColor} />
              </div>
              <div style={{ fontSize: solution ? 28 : 30, fontWeight: 600, lineHeight: 1.35 }}>{item.text}</div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
