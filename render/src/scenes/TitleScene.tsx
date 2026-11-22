import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { TitleScene as T } from "@demoday/contracts";
import { theme } from "../theme";

// TODO(계약 머지 후): kicker가 스키마에 들어오면 캐스트를 지운다 (이슈 #8)
type Props = { scene: T & { kicker?: string } };

/** kicker가 있으면 장 구분 카드(작은 번호 + 큰 문장, 왼쪽 정렬), 없으면 가운데 타이틀. */
export const TitleScene: React.FC<Props> = ({ scene }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = spring({ frame, fps, config: { damping: 200 } });
  const sub = spring({ frame, fps, delay: 0.35 * fps, config: { damping: 200 } });
  const bar = spring({ frame, fps, delay: 0.15 * fps, config: { damping: 200 } });
  const rise = (p: number) => `translateY(${interpolate(p, [0, 1], [24, 0])}px)`;
  const chapter = Boolean(scene.kicker);

  return (
    <AbsoluteFill
      style={{
        background: theme.bg,
        color: theme.ink,
        fontFamily: theme.font,
        ...theme.keepAll,
        justifyContent: "center",
        alignItems: chapter ? "flex-start" : "center",
        textAlign: chapter ? "left" : "center",
        padding: chapter ? "0 140px" : 0,
      }}
    >
      {chapter && (
        <div style={{ fontSize: 30, fontWeight: 700, color: theme.accent, letterSpacing: 2, opacity: bar, marginBottom: 18 }}>
          {scene.kicker}
        </div>
      )}
      <div style={{ fontSize: chapter ? 64 : 84, fontWeight: 800, letterSpacing: -1.5, lineHeight: 1.2, maxWidth: 1000, opacity: t, transform: rise(t) }}>
        {scene.text}
      </div>
      {!chapter && <div style={{ width: 120 * bar, height: 6, borderRadius: 3, background: theme.accent, margin: "28px 0" }} />}
      {scene.subtitle && (
        <div style={{ fontSize: 34, color: theme.sub, marginTop: chapter ? 24 : 0, opacity: sub, transform: rise(sub) }}>{scene.subtitle}</div>
      )}
    </AbsoluteFill>
  );
};
