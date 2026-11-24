import { AbsoluteFill, Easing, Freeze, getStaticFiles, Img, interpolate, OffthreadVideo, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import type { ScreenScene as T } from "@demoday/contracts";
import { theme } from "../theme";
import { Backdrop, fitFont, Words } from "../motion";

const W = 1280;
const H = 720;
const BAR = 36;

/** 녹화 구간을 장면 길이에 맞추는 재생 속도 범위. 벗어나면 마지막 프레임에서 멈춘다. */
const RATE_MIN = 0.5;
const RATE_MAX = 2;

type Props = { scene: T; domain?: string; durationInFrames: number; index?: number; count?: number; layout?: Layout };

/** 화면 연출. 화면 내용에 맞춰 고른다(pickLayouts) — 같은 '보여주고 → 확대'가 반복되지 않게(11/24 피드백). */
export type Layout = "center" | "split" | "tilt" | "wide";

/**
 * 화면 장면마다 내용에 맞는 연출을 고른다(결정적).
 * - 클릭·입력(cursor): 동작에 다가가는 클로즈업 — center, 연달아 나오면 split(왼쪽 큰 자막)
 * - 핵심 영역(zoom만): 그 영역을 3D로 기울여 보여주는 tilt, 연달아면 center
 * - 동작·핵심 영역 없음(둘러보기·스크롤): 꽉 찬 화면을 옆으로 훑는 wide, 연달아면 split
 * - 첫 화면이 동작이 아니면 split — 큰 자막과 함께 물러나며 서비스 전체를 소개한다
 */
export function pickLayouts(screens: T[]): Layout[] {
  const out: Layout[] = [];
  screens.forEach((s, i) => {
    const kind = s.cursor ? "act" : s.zoom ? "focus" : "view";
    const options: Layout[] =
      i === 0 && kind !== "act" ? ["split", "wide"] : kind === "act" ? ["center", "split"] : kind === "focus" ? ["tilt", "center"] : ["wide", "split"];
    out.push(options.find((o) => o !== out[i - 1]) ?? options[0]);
  });
  return out;
}
/** 레이아웃별 카메라(클릭이 없는 화면): 다가가기 / 물러나며 전체 보여주기 / 옆으로 훑기 */
const CAMERA: Record<Layout, "push" | "pull" | "pan"> = { center: "push", split: "pull", tilt: "push", wide: "pan" };
/** 브라우저 카드 배율 */
const SCALE: Record<Layout, number> = { center: 0.84, split: 0.64, tilt: 0.8, wide: 0.9 };
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
 * 배경 위 브라우저 카드 + 커서 이동 → 클릭 하이라이트 → 카메라 + 자막. 좌표는 캡처 viewport(1280x720) 기준 px.
 * layout은 Demo가 pickLayouts로 화면 내용에 맞춰 정한다: center · split(왼쪽 큰 자막) · tilt(3D 기울기) · wide(꽉 찬 화면).
 */
export const ScreenScene: React.FC<Props> = ({ scene, domain, durationInFrames, index = 0, count = 0, layout = "center" }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const m = media(scene, durationInFrames, fps);
  const S = SCALE[layout];
  const enter = spring({ frame, fps, config: { damping: 200 }, durationInFrames: 0.7 * fps });
  const cardW = W * S;
  const cardH = H * S + BAR;
  const left = layout === "split" ? W - cardW - 56 : (W - cardW) / 2;
  const top = (H - cardH) / 2 - (layout === "center" ? 10 : 0);
  const tilt = interpolate(frame, [0, durationInFrames], [0, 1]);
  const transform = {
    center: `translateY(${interpolate(enter, [0, 1], [40, 0])}px) scale(${interpolate(enter, [0, 1], [0.96, 1])})`,
    split: `translateX(${interpolate(enter, [0, 1], [120, 0])}px)`,
    tilt: `perspective(1800px) rotateY(${interpolate(enter, [0, 1], [-28, -9]) + tilt * 5}deg) rotateX(${interpolate(enter, [0, 1], [10, 4])}deg) translateX(${interpolate(enter, [0, 1], [60, 0])}px)`,
    wide: `scale(${interpolate(enter, [0, 1], [1.06, 1])})`,
  }[layout];
  const step = count > 1 ? `${String(index + 1).padStart(2, "0")}` : undefined;

  return (
    <AbsoluteFill style={{ fontFamily: theme.font }}>
      <Backdrop seed={index + 4} />
      <div
        style={{
          position: "absolute",
          left,
          top,
          width: cardW,
          height: cardH,
          borderRadius: 16,
          overflow: "hidden",
          background: "white",
          boxShadow: "0 30px 80px rgba(0,0,0,0.20), 0 2px 8px rgba(0,0,0,0.08)",
          transform,
          transformOrigin: layout === "tilt" ? "60% 50%" : "50% 50%",
          opacity: interpolate(enter, [0, 0.4], [0, 1], { extrapolateRight: "clamp" }),
        }}
      >
        <AddressBar domain={domain} />
        <div style={{ width: cardW, height: H * S, overflow: "hidden", position: "relative" }}>
          <div style={{ width: W, height: H, transform: `scale(${S})`, transformOrigin: "0 0" }}>
            <Screen scene={scene} media={m} total={durationInFrames} mode={CAMERA[layout]} />
          </div>
        </div>
      </div>
      {scene.caption &&
        (layout === "split" ? (
          <SideCaption text={scene.caption} highlight={scene.highlight} step={step} count={count} width={left - 100} />
        ) : (
          <Caption text={scene.caption} highlight={scene.highlight} step={step} place={layout === "wide" ? "middle" : layout === "tilt" ? "right" : "left"} />
        ))}
    </AbsoluteFill>
  );
};

const ease = { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.inOut(Easing.cubic) } as const;

/**
 * 카메라: 확대할수록 zoom 지점을 화면 가운데로 끌어오되, 확대한 영역이 화면 밖으로 나가지 않게 중심을 clamp 한다
 * (기준점 확대는 가장자리 지점에서 화면이 한쪽으로 쏠리고 잘렸다).
 * - 클릭(cursor 있음): 클릭(0.8초) 직후 0.8초 동안 확대. 녹화가 있고 장면이 충분히 길면 끝 1초 동안 전체로 돌아와 결과를 보여준다
 * - 핵심 영역(cursor 없음): 0.3초부터 장면 끝까지 천천히 다가간다 — 설명하는 곳에 시선이 머물게
 */
type Mode = "push" | "pull" | "pan";

function zoom(scene: T, frame: number, total: number, s: (sec: number) => number, video: boolean, mode: Mode): string | undefined {
  // 줌 지점이 없는 화면도 멈춰 있지 않게 가운데를 기준으로 약하게 움직인다
  const z = scene.zoom ?? { x: W / 2, y: H / 2, scale: 1.12 };
  let p: number;
  let k: number;
  let tx = z.x;
  let ty = z.y;
  if (scene.cursor) {
    const inEnd = s(1.6);
    p = interpolate(frame, [s(0.8), inEnd], [0, 1], ease);
    const outStart = total - s(1);
    if (video && outStart > inEnd + s(0.6)) p *= 1 - interpolate(frame, [outStart, total - s(0.2)], [0, 1], ease);
    k = 1 + (z.scale - 1) * p;
  } else if (mode === "pull") {
    // 핵심 영역에 붙어 있다가 물러나며 전체를 보여준다
    p = 1 - interpolate(frame, [s(0.2), Math.max(s(0.2) + 1, total - s(0.4))], [0, 1], ease);
    k = 1 + (Math.max(z.scale, 1.25) - 1) * p;
  } else if (mode === "pan") {
    // 살짝 확대한 채 왼쪽에서 핵심 영역 쪽으로 훑는다
    const q = interpolate(frame, [0, total], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.inOut(Easing.sin) });
    k = Math.max(1.18, Math.min(z.scale, 1.3));
    p = 1;
    tx = interpolate(q, [0, 1], [W * 0.3, Math.max(W * 0.55, z.x)]);
    ty = interpolate(q, [0, 1], [H * 0.4, z.y]);
  } else {
    p = interpolate(frame, [s(0.3), Math.max(s(0.3) + 1, total - s(0.3))], [0, 1], ease);
    k = 1 + (z.scale - 1) * p;
  }
  const fit = (c: number, size: number) => Math.min(size - size / (2 * k), Math.max(size / (2 * k), c));
  const cx = fit(interpolate(p, [0, 1], [W / 2, tx]), W);
  const cy = fit(interpolate(p, [0, 1], [H / 2, ty]), H);
  return `translate(${W / 2 - cx * k}px, ${H / 2 - cy * k}px) scale(${k})`;
}

/**
 * 캡처 좌표계(1280x720) 안: 화면(녹화 구간 또는 정지 화면) + 커서 + 클릭 하이라이트 + 줌.
 * 녹화를 빠르게/느리게 재생하면 클릭 시각도 같이 움직이므로 커서 박자를 재생 속도로 나눈다.
 */
const Screen: React.FC<{ scene: T; media: Media | null; total: number; mode: Mode }> = ({ scene, media: m, total, mode }) => {
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

  const camera = zoom(scene, frame, total, s, Boolean(m), mode);

  return (
    <AbsoluteFill style={{ transform: camera, transformOrigin: "0 0" }}>
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

/** 자막 상자. place: left(왼쪽 아래) · right(오른쪽 아래) · middle(가운데 아래). step이 있으면 앞에 주황 순번. */
const Caption: React.FC<{ text: string; highlight?: string[]; step?: string; place: "left" | "right" | "middle" }> = ({ text, highlight, step, place }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = spring({ frame, fps, delay: 0.3 * fps, config: { damping: 18, mass: 0.7 } });
  const pos: React.CSSProperties =
    place === "middle" ? { left: "50%", bottom: 34 } : place === "right" ? { right: 56, bottom: 34 } : { left: 56, bottom: 34 };
  return (
    <div
      style={{
        position: "absolute",
        ...pos,
        maxWidth: W * 0.62,
        display: "flex",
        alignItems: "center",
        gap: 16,
        padding: "14px 26px 14px 16px",
        borderRadius: 14,
        background: "rgba(17,17,19,0.92)",
        color: "white",
        fontSize: 32,
        fontWeight: 700,
        lineHeight: 1.3,
        letterSpacing: "-0.01em",
        ...theme.keepAll,
        boxShadow: "0 14px 36px rgba(0,0,0,0.28)",
        opacity: interpolate(p, [0, 0.4], [0, 1], { extrapolateRight: "clamp" }),
        transform: `${place === "middle" ? "translateX(-50%) " : ""}translateY(${interpolate(p, [0, 1], [24, 0])}px)`,
        clipPath: `inset(0 ${interpolate(p, [0, 1], [100, 0], { extrapolateRight: "clamp" })}% 0 0 round 14px)`,
      }}
    >
      {step && (
        <span style={{ flexShrink: 0, padding: "4px 10px", borderRadius: 8, background: theme.accent, fontSize: 20, fontWeight: 700 }}>{step}</span>
      )}
      <span>{emphasize(text, highlight)}</span>
    </div>
  );
};

/** split 레이아웃: 왼쪽 빈 공간에 큰 순번 + 단어별로 올라오는 큰 자막. */
const SideCaption: React.FC<{ text: string; highlight?: string[]; step?: string; count: number; width: number }> = ({ text, highlight, step, count, width }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const bar = spring({ frame, fps, delay: 0.5 * fps, config: { damping: 200 } });
  return (
    <div style={{ position: "absolute", left: 64, top: 0, bottom: 0, width, display: "flex", flexDirection: "column", justifyContent: "center", color: theme.ink, ...theme.keepAll }}>
      {step && (
        <div style={{ fontSize: 22, fontWeight: 700, color: theme.accent, marginBottom: 18, opacity: bar }}>
          {step}
          <span style={{ color: theme.sub, fontWeight: 600 }}> / {String(count).padStart(2, "0")}</span>
        </div>
      )}
      <Words text={text} delay={0.25} accent={highlight} style={{ fontSize: fitFont(text, width - 8, 44), fontWeight: 700, lineHeight: 1.22, letterSpacing: "-0.03em", maxWidth: width }} />
      <div style={{ marginTop: 26, width: 64 * bar, height: 6, borderRadius: 3, background: theme.accent }} />
    </div>
  );
};
