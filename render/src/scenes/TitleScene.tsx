import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { TitleScene as T } from "@demoday/contracts";
import { theme } from "../theme";

type Props = { scene: T };

/**
 * 왼쪽 정렬 편집 레이아웃. kicker가 있으면 장 구분 카드(작은 주황 라벨 + 문장),
 * 없으면 오프닝 타이틀(짧은 주황 막대 + 큰 제목 + 부제).
 */
export const TitleScene: React.FC<Props> = ({ scene }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = spring({ frame, fps, config: { damping: 200 } });
  const sub = spring({ frame, fps, delay: 0.3 * fps, config: { damping: 200 } });
  const mark = spring({ frame, fps, delay: 0.1 * fps, config: { damping: 200 } });
  const rise = (p: number) => `translateY(${interpolate(p, [0, 1], [20, 0])}px)`;
  const chapter = Boolean(scene.kicker);

  return (
    <AbsoluteFill
      style={{
        background: theme.bg,
        color: theme.ink,
        fontFamily: theme.font,
        ...theme.keepAll,
        justifyContent: "center",
        alignItems: "flex-start",
        padding: "0 140px",
      }}
    >
      {chapter ? (
        <div style={{ fontSize: 22, fontWeight: 600, color: theme.accent, opacity: mark, marginBottom: 20 }}>{scene.kicker}</div>
      ) : (
        <div style={{ width: 56 * mark, height: 6, borderRadius: 3, background: theme.accent, marginBottom: 32 }} />
      )}
      <div
        style={{
          fontSize: chapter ? 64 : 72,
          fontWeight: 700,
          letterSpacing: "-0.02em",
          lineHeight: 1.25,
          maxWidth: 1000,
          opacity: t,
          transform: rise(t),
        }}
      >
        {scene.text}
      </div>
      {scene.subtitle && (
        <div style={{ fontSize: 30, fontWeight: 500, lineHeight: 1.35, color: theme.sub, marginTop: 28, maxWidth: 1000, opacity: sub, transform: rise(sub) }}>
          {scene.subtitle}
        </div>
      )}
    </AbsoluteFill>
  );
};
