import { useState } from "react";
import { AbsoluteFill, Easing, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import type { TitleScene as T } from "@demoday/contracts";
import { theme } from "../theme";
import { Backdrop, fitFont, Pill, Words } from "../motion";

type Props = { scene: T; durationInFrames: number; logo?: string };

/**
 * 로고 이미지. 못 읽으면(깨진 파일·HTML) 렌더를 멈추지 않고 fallback 을 그린다 —
 * Img 는 onError 가 없으면 재시도 뒤 렌더 전체를 취소한다(리뷰 #84).
 */
const LogoImg: React.FC<{ src: string; size: number; fallback?: React.ReactNode }> = ({ src, size, fallback = null }) => {
  const [broken, setBroken] = useState(false);
  if (broken) return <>{fallback}</>;
  return <Img src={staticFile(src)} maxRetries={0} onError={() => setBroken(true)} style={{ width: size, height: size, objectFit: "contain" }} />;
};

/** 서비스 로고 배지: 흰 둥근 사각형 안에 로고, 튀어 오르며 나타난다 */
const Logo: React.FC<{ src: string; size: number; delay?: number }> = ({ src, size, delay = 0 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = spring({ frame, fps, delay: delay * fps, config: { damping: 12 } });
  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: size * 0.26,
        background: "white",
        boxShadow: "0 20px 50px rgba(0,0,0,0.18)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        transform: `scale(${p}) rotate(${interpolate(p, [0, 1], [-12, 0])}deg)`,
        opacity: interpolate(p, [0, 0.3], [0, 1], clamp),
      }}
    >
      <LogoImg src={src} size={size * 0.7} />
    </div>
  );
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

/** 오른쪽 장식: 선이 그려지며 도는 동심원 호 + 가운데 이니셜 배지. */
const Rings: React.FC<{ letter: string; logo?: string }> = ({ letter, logo }) => {
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
          background: logo ? "white" : `linear-gradient(135deg, ${theme.accent}, #ff9a52)`,
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
        {logo ? <LogoImg src={logo} size={110} fallback={letter} /> : letter}
      </div>
    </div>
  );
};

/**
 * 엔딩(kicker "정리" + subtitle=서비스 이름): [로고][서비스 이름]이 한 줄로 튀어 오르고,
 * 아래에 "이제, ~하세요" 한 문장이 단어별로 올라온다(11/24 피드백 — 예: managers manager "이제, 회의에만 집중하세요").
 * 로고가 없거나 깨지면 이름 첫 글자 배지.
 */
const Ending: React.FC<{ name: string; line: string; logo?: string; durationInFrames: number }> = ({ name, line, logo, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const brand = spring({ frame, fps, delay: 0.05 * fps, config: { damping: 14 } });
  const nameIn = spring({ frame, fps, delay: 0.25 * fps, config: { damping: 200 } });
  const words = line.split(/\s+/).length;
  const underline = interpolate(frame, [(0.9 + words * 0.07) * fps, (1.5 + words * 0.07) * fps], [0, 1], { ...clamp, easing: Easing.inOut(Easing.cubic) });
  const drift = interpolate(frame, [0, durationInFrames], [1, 1.03]);
  const size = 112;
  const letter = [...name.trim()][0] ?? "D";
  const initial = (
    <div style={{ width: size, height: size, borderRadius: size * 0.26, background: `linear-gradient(135deg, ${theme.accent}, #ff9a52)`, color: "white", fontSize: 60, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center" }}>
      {letter}
    </div>
  );
  return (
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", textAlign: "center", padding: "0 120px", transform: `scale(${drift})` }}>
      <div style={{ display: "flex", alignItems: "center", gap: 30, transform: `translateY(${interpolate(brand, [0, 1], [30, 0])}px)`, opacity: interpolate(brand, [0, 0.3], [0, 1], clamp) }}>
        <div
          style={{
            width: size,
            height: size,
            borderRadius: size * 0.26,
            background: "white",
            boxShadow: "0 20px 50px rgba(0,0,0,0.16)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            overflow: "hidden",
            transform: `scale(${brand}) rotate(${interpolate(brand, [0, 1], [-12, 0])}deg)`,
          }}
        >
          {logo ? <LogoImg src={logo} size={size * 0.72} fallback={initial} /> : initial}
        </div>
        <div style={{ fontSize: fitFont(name, 760, 96), fontWeight: 700, letterSpacing: "-0.04em", opacity: nameIn, transform: `translateX(${interpolate(nameIn, [0, 1], [-24, 0])}px)` }}>{name}</div>
      </div>
      <Words text={line} delay={0.75} stagger={0.08} style={{ marginTop: 46, fontSize: fitFont(line, 1000, 54), fontWeight: 600, color: theme.ink, letterSpacing: "-0.02em", justifyContent: "center", maxWidth: 1040 }} />
      <div style={{ marginTop: 22, width: 200 * underline, height: 7, borderRadius: 4, background: `linear-gradient(90deg, ${theme.accent}, #ffb37a)` }} />
    </AbsoluteFill>
  );
};

/**
 * 오프닝 타이틀: 큰 서비스 이름이 단어별로 솟아오르고, 오른쪽에 선이 그려지는 원 장식.
 * kicker가 있으면 장 구분 카드(문제·정리): 라벨 알약 + 큰 문장 + 밑줄이 그어진다.
 * 장면 내내 아주 천천히 다가가 정지 화면처럼 보이지 않게 한다.
 */
export const TitleScene: React.FC<Props> = ({ scene, durationInFrames, logo }) => {
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
  // 레포 이름이 길어 600px에 큰 글씨로 안 들어가면 오른쪽 장식을 빼고 넓게 쓴다
  const narrow = fitFont(scene.text, 600, 92);
  const roomy = narrow >= 60;
  const titleSize = roomy ? narrow : fitFont(scene.text, 1040, 92);

  if (scene.kicker === "정리" && scene.subtitle) {
    return (
      <AbsoluteFill style={{ fontFamily: theme.font, color: theme.ink, ...theme.keepAll }}>
        <Backdrop seed={2} />
        <Ending name={scene.subtitle} line={scene.text} logo={logo} durationInFrames={durationInFrames} />
      </AbsoluteFill>
    );
  }

  return (
    <AbsoluteFill style={{ fontFamily: theme.font, color: problem ? "white" : theme.ink, ...theme.keepAll }}>
      <Backdrop seed={chapter ? 2 : 0} dark={problem} />
      <AbsoluteFill style={{ transform: `scale(${drift})`, transformOrigin: "30% 50%" }}>
        {chapter ? (
          <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", padding: "0 140px", textAlign: "center" }}>
            {logo && !problem && (
              <div style={{ marginBottom: 30 }}>
                <Logo src={logo} size={scene.kicker === "정리" ? 132 : 112} />
              </div>
            )}
            <Pill text={scene.kicker ?? ""} color={color} light={problem} />
            <div style={{ position: "relative", marginTop: 34 }}>
              <Words text={scene.text} delay={0.2} style={{ fontSize: fitFont(scene.text, 960, 70), fontWeight: 700, letterSpacing: "-0.03em", lineHeight: 1.22, justifyContent: "center", maxWidth: 1000 }} />
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
            <Words text={scene.text} delay={0.1} stagger={0.09} style={{ fontSize: titleSize, fontWeight: 700, letterSpacing: "-0.035em", lineHeight: 1.12, maxWidth: roomy ? 640 : 1040 }} />
            {scene.subtitle && (
              <Words text={scene.subtitle} delay={0.6} stagger={0.05} style={{ fontSize: 32, fontWeight: 500, color: theme.sub, marginTop: 30, maxWidth: 600, lineHeight: 1.4 }} />
            )}
            {roomy && <Rings letter={[...scene.text.trim()][0] ?? "D"} logo={logo} />}
          </AbsoluteFill>
        )}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
