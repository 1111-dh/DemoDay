import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { theme } from "./theme";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

/**
 * 모든 장면 공통 배경: 회백색 위에 천천히 떠다니는 주황·살구색 빛 번짐 + 옅은 점 격자.
 * seed로 장면마다 빛 위치를 다르게 해서, 같은 배경이 반복돼 보이지 않게 한다. 프레임 기반이라 결정적이다.
 */
export const Backdrop: React.FC<{ seed?: number; dark?: boolean }> = ({ seed = 0, dark = false }) => {
  const frame = useCurrentFrame();
  const a = frame / 90 + seed * 1.7;
  const blob = (x: number, y: number, size: number, color: string) => (
    <div
      style={{
        position: "absolute",
        left: x - size / 2,
        top: y - size / 2,
        width: size,
        height: size,
        borderRadius: "50%",
        background: `radial-gradient(circle, ${color} 0%, rgba(255,255,255,0) 68%)`,
      }}
    />
  );
  return (
    <AbsoluteFill style={{ background: dark ? theme.night : theme.bg, overflow: "hidden" }}>
      {blob(260 + Math.sin(a) * 90 + seed * 140, 160 + Math.cos(a * 0.8) * 60, 760, dark ? "rgba(242,107,29,0.30)" : "rgba(242,107,29,0.16)")}
      {blob(1040 - Math.cos(a * 0.7) * 110 - seed * 90, 560 + Math.sin(a * 0.9) * 70, 820, dark ? "rgba(255,170,120,0.16)" : "rgba(255,190,140,0.22)")}
      <AbsoluteFill
        style={{
          backgroundImage: `radial-gradient(${dark ? "rgba(255,255,255,0.07)" : "rgba(28,28,30,0.07)"} 1.2px, transparent 1.2px)`,
          backgroundSize: "28px 28px",
          backgroundPosition: `${(frame * 0.15) % 28}px 0px`,
        }}
      />
    </AbsoluteFill>
  );
};

/** 굵은 글꼴 기준 글자 폭 추정(em): 한글·한자 1, 영문 대문자 0.74, 소문자·숫자 0.62, 기호 0.4. */
function units(word: string): number {
  return [...word].reduce((n, c) => n + (/[\u3131-\uD79D\u4E00-\u9FFF]/.test(c) ? 1 : /[A-Z]/.test(c) ? 0.74 : /[a-z0-9]/.test(c) ? 0.62 : 0.4), 0);
}

/**
 * 가장 긴 단어가 maxWidth 안에 들어가는 글자 크기(base 이하, base의 45% 이상).
 * 단어는 마스크 애니메이션 때문에 통째로 움직이므로 단어 안에서 줄이 바뀌지 않는다 — 긴 레포 이름이 넘치지 않게.
 */
export function fitFont(text: string, maxWidth: number, base: number): number {
  const longest = Math.max(1, ...text.split(/\s+/).map(units));
  return Math.max(base * 0.45, Math.min(base, Math.floor(maxWidth / longest)));
}

/**
 * 키네틱 타이포: 단어마다 아래에서 가려진 채로 올라오며(마스크) 흐림이 걷힌다.
 * accent에 든 단어는 주황. delay·stagger는 초.
 */
export const Words: React.FC<{
  text: string;
  delay?: number;
  stagger?: number;
  accent?: string[];
  style?: React.CSSProperties;
  accentColor?: string;
}> = ({ text, delay = 0, stagger = 0.07, accent = [], style, accentColor = theme.accent }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const words = text.split(/\s+/).filter(Boolean);
  return (
    <div style={{ display: "flex", flexWrap: "wrap", columnGap: "0.28em", ...style }}>
      {words.map((w, i) => {
        const p = spring({ frame, fps, delay: (delay + i * stagger) * fps, config: { damping: 18, mass: 0.7 } });
        const hit = accent.some((a) => a && (w.includes(a) || a.includes(w)));
        return (
          <span key={i} style={{ display: "inline-block", maxWidth: "100%", overflow: "hidden", paddingBottom: "0.12em", marginBottom: "-0.12em" }}>
            <span
              style={{
                display: "inline-block",
                maxWidth: "100%",
                overflowWrap: "anywhere", // 최소 크기로도 넘치면 단어 안에서라도 줄을 바꾼다
                transform: `translateY(${interpolate(p, [0, 1], [105, 0])}%)`,
                filter: `blur(${interpolate(p, [0, 1], [6, 0], clamp)}px)`,
                opacity: interpolate(p, [0, 0.4], [0, 1], clamp),
                color: hit ? accentColor : undefined,
              }}
            >
              {w}
            </span>
          </span>
        );
      })}
    </div>
  );
};

/** 작은 라벨 알약(kicker): 왼쪽부터 펼쳐지며 나타난다. */
export const Pill: React.FC<{ text: string; color: string; delay?: number; light?: boolean }> = ({ text, color, delay = 0, light }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = spring({ frame, fps, delay: delay * fps, config: { damping: 200 } });
  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 10,
        padding: "8px 18px 8px 14px",
        borderRadius: 999,
        background: light ? "rgba(255,255,255,0.08)" : "white",
        border: `1.5px solid ${color}33`,
        boxShadow: light ? undefined : "0 6px 18px rgba(0,0,0,0.06)",
        fontSize: 22,
        fontWeight: 700,
        color,
        opacity: p,
        transform: `translateX(${interpolate(p, [0, 1], [-24, 0])}px)`,
        clipPath: `inset(0 ${interpolate(p, [0, 1], [100, 0])}% 0 0 round 999px)`,
      }}
    >
      <span style={{ width: 10, height: 10, borderRadius: "50%", background: color }} />
      {text}
    </div>
  );
};

/** 장면 끝 0.4초 동안 살짝 흐려지며 물러난다 — 전환이 부드럽게 이어지게. */
export function exitStyle(frame: number, total: number, fps: number): React.CSSProperties {
  const out = interpolate(frame, [total - 0.4 * fps, total], [0, 1], clamp);
  return { opacity: 1 - out * 0.6, transform: `scale(${1 - out * 0.02})` };
}
