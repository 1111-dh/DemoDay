import { AbsoluteFill, Easing, Freeze, getStaticFiles, Img, interpolate, OffthreadVideo, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import type { ScreenScene as T } from "@demoday/contracts";
import { theme } from "../theme";

const W = 1280;
const H = 720;
/** 브라우저 카드 안 화면 배율. 화면 내부는 캡처 좌표(1280x720) 그대로 그리고 통째로 줄인다. */
const S = 0.86;
const BAR = 36;

/** 녹화 구간을 장면 길이에 맞추는 재생 속도 범위. 벗어나면 마지막 프레임에서 멈춘다. */
const RATE_MIN = 0.5;
const RATE_MAX = 2;

type Props = { scene: T; domain?: string; durationInFrames: number };
type Media = { src: string; trimBefore: number; rate: number; playFrames: number };

/** 재생할 녹화 구간. 파일이 없거나 구간이 잘못됐으면 null → 정지 화면(image). */
function media(scene: T, sceneFrames: number, fps: number): Media | null {
  const v = scene.video;
  if (!v || v.endMs <= v.startMs) return null;
  if (!getStaticFiles().some((f) => f.name === `run/${v.src}`)) return null;
  const clipFrames = ((v.endMs - v.startMs) / 1000) * fps;
  const rate = Math.min(RATE_MAX, Math.max(RATE_MIN, clipFrames / sceneFrames));
  return {
    src: staticFile(`run/${v.src}`),
    trimBefore: Math.round((v.startMs / 1000) * fps),
    rate,
    playFrames: Math.max(1, Math.floor(clipFrames / rate)),
  };
}

/**
 * 밝은 배경 위 브라우저 카드 + 커서 이동 → 클릭 하이라이트 → 줌 인 + 좌하단 자막.
 * 좌표는 캡처 viewport(1280x720) 기준 px.
 */
export const ScreenScene: React.FC<Props> = ({ scene, domain, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const m = media(scene, durationInFrames, fps);
  const enter = spring({ frame, fps, config: { damping: 200 }, durationInFrames: 0.6 * fps });

  return (
    <AbsoluteFill style={{ background: theme.bg, fontFamily: theme.font }}>
      <div
        style={{
          position: "absolute",
          left: (W - W * S) / 2,
          top: (H - (H * S + BAR)) / 2 - 12,
          width: W * S,
          height: H * S + BAR,
          borderRadius: 14,
          overflow: "hidden",
          background: "white",
          boxShadow: "0 24px 60px rgba(0,0,0,0.16), 0 2px 8px rgba(0,0,0,0.08)",
          transform: `translateY(${interpolate(enter, [0, 1], [16, 0])}px)`,
        }}
      >
        <AddressBar domain={domain} />
        <div style={{ width: W * S, height: H * S, overflow: "hidden", position: "relative" }}>
          <div style={{ width: W, height: H, transform: `scale(${S})`, transformOrigin: "0 0" }}>
            <Screen scene={scene} media={m} total={durationInFrames} />
          </div>
        </div>
      </div>
      {scene.caption && <Caption text={scene.caption} highlight={scene.highlight} />}
    </AbsoluteFill>
  );
};

/**
 * 캡처 좌표계(1280x720) 안: 화면(녹화 구간 또는 정지 화면) + 커서 + 클릭 하이라이트 + 줌.
 * 녹화를 빠르게/느리게 재생하면 클릭 시각도 같이 움직이므로 커서 박자를 재생 속도로 나눈다.
 */
const Screen: React.FC<{ scene: T; media: Media | null; total: number }> = ({ scene, media: m, total }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = (sec: number) => (sec * fps) / (m?.rate ?? 1);

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
  // 녹화가 있으면 끝 1.2초(결과 화면)는 다시 전체로 — 확대한 채면 결과가 화면 가장자리에서 잘린다(#34, nuxt 검색 결과)
  const out = zoom && m ? spring({ frame, fps, delay: total - s(1.2), config: { damping: 200 }, durationInFrames: s(0.7) }) : 0;
  const scale = zoom ? 1 + (zoom.scale - 1) * z * (1 - out) : 1;

  return (
    // 줌 기준점을 원점으로 잡으면 scale ≥ 1에서도 화면이 비지 않는다
    <AbsoluteFill style={{ transform: `scale(${scale})`, transformOrigin: zoom ? `${zoom.x}px ${zoom.y}px` : "center" }}>
      {m ? (
        // 구간이 장면보다 짧으면(속도 하한) 마지막 프레임에서 멈춘다
        <Freeze frame={m.playFrames - 1} active={frame >= m.playFrames}>
          <OffthreadVideo src={m.src} trimBefore={m.trimBefore} playbackRate={m.rate} muted style={{ width: W, height: H }} />
        </Freeze>
      ) : (
        <Img src={staticFile(`run/${scene.image}`)} style={{ width: W, height: H }} />
      )}
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
              border: `4px solid ${theme.accent}`,
              background: "rgba(242, 107, 29, 0.18)",
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
  );
};

const AddressBar: React.FC<{ domain?: string }> = ({ domain }) => (
  <div style={{ height: BAR, display: "flex", alignItems: "center", gap: 8, padding: "0 14px", background: "#ecebe7", borderBottom: "1px solid #dddcd6" }}>
    {["#ff5f57", "#febc2e", "#28c840"].map((c) => (
      <div key={c} style={{ width: 11, height: 11, borderRadius: "50%", background: c }} />
    ))}
    {domain && (
      <div style={{ marginLeft: 16, flex: 1, maxWidth: 420, height: 22, borderRadius: 6, background: "white", color: theme.sub, fontSize: 13, display: "flex", alignItems: "center", padding: "0 12px" }}>
        {domain}
      </div>
    )}
  </div>
);

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

/** caption 안의 highlight 단어를 주황으로. */
function emphasize(text: string, words: string[] = []) {
  const ws = words.filter(Boolean);
  if (!ws.length) return text;
  const re = new RegExp(`(${ws.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "g");
  return text.split(re).map((part, i) => (ws.includes(part) ? <span key={i} style={{ color: theme.accent }}>{part}</span> : part));
}

const Caption: React.FC<{ text: string; highlight?: string[] }> = ({ text, highlight }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = spring({ frame, fps, delay: 0.3 * fps, config: { damping: 200 } });
  return (
    <div
      style={{
        position: "absolute",
        left: 56,
        bottom: 34,
        maxWidth: W * 0.62,
        padding: "14px 24px",
        borderRadius: 10,
        background: theme.label,
        color: "white",
        fontSize: 30,
        fontWeight: 600,
        lineHeight: 1.35,
        ...theme.keepAll,
        boxShadow: "0 10px 30px rgba(0,0,0,0.25)",
        opacity: p,
        transform: `translateY(${interpolate(p, [0, 1], [20, 0])}px)`,
      }}
    >
      {emphasize(text, highlight)}
    </div>
  );
};
