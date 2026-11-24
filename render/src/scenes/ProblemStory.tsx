import { AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { PointsScene as T } from "@demoday/contracts";
import { theme } from "../theme";
import { Backdrop, fitFont, Pill, Words } from "../motion";

type IconName = T["items"][number]["icon"];
type Kind = "pileup" | "waiting" | "lost" | "decline" | "tangled";

/**
 * 불편 항목의 아이콘 → 그 불편을 보여줄 가상의 인터넷 화면.
 * 레포마다 LLM이 상황 문장과 아이콘을 고르므로(prompts/scene.md) 어떤 서비스든 다섯 화면 중 하나로 그려진다.
 */
const KIND: Record<IconName, Kind> = {
  document: "pileup",
  chat: "pileup",
  clock: "waiting",
  calendar: "waiting",
  search: "lost",
  map: "lost",
  user: "lost",
  ai: "lost",
  chart: "decline",
  money: "decline",
  store: "decline",
  alert: "decline",
  bolt: "decline",
  check: "decline",
  team: "tangled",
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const INTRO = 1.4; // 처음 제목만 보이는 시간(초)
const RED = theme.red;
const WIN = { x: 260, y: 140, w: 760, h: 390 }; // 가상 브라우저 창
const LINE = "#e7e5df";
const SOFT = "#f3f2ee";
const AVATAR = ["#c9d2ff", "#cdeedd", "#ffe1c2", "#f6d0e0"];

type V = { f: number; fps: number };

/** 가상 브라우저 창(주소창 + 오른쪽 위 빨간 배지). children은 창 안쪽(760x354) 좌표로 그린다 */
const Window: React.FC<V & { url: string; badge?: string; children: React.ReactNode }> = ({ f, fps, url, badge, children }) => {
  const p = spring({ frame: f, fps, config: { damping: 16 } });
  return (
    <div
      style={{
        position: "absolute",
        left: WIN.x,
        top: WIN.y,
        width: WIN.w,
        height: WIN.h,
        borderRadius: 14,
        overflow: "hidden",
        background: "white",
        color: theme.ink,
        boxShadow: "0 30px 80px rgba(0,0,0,0.5)",
        transform: `translateY(${interpolate(p, [0, 1], [40, 0])}px) scale(${interpolate(p, [0, 1], [0.94, 1])})`,
        opacity: interpolate(p, [0, 0.3], [0, 1], clamp),
      }}
    >
      <div style={{ height: 36, display: "flex", alignItems: "center", gap: 8, padding: "0 14px", background: "#ecebe7", borderBottom: "1px solid #dddcd6" }}>
        {["#ff5f57", "#febc2e", "#28c840"].map((c) => (
          <div key={c} style={{ width: 11, height: 11, borderRadius: "50%", background: c }} />
        ))}
        <div style={{ marginLeft: 14, flex: 1, maxWidth: 380, height: 22, borderRadius: 6, background: "white", color: theme.sub, fontSize: 13, display: "flex", alignItems: "center", padding: "0 12px" }}>{url}</div>
        {badge && <div style={{ marginLeft: "auto", padding: "2px 10px", borderRadius: 11, background: RED, color: "white", fontSize: 14, fontWeight: 700 }}>{badge}</div>}
      </div>
      <div style={{ position: "relative", width: WIN.w, height: WIN.h - 36, fontFamily: theme.font }}>{children}</div>
    </div>
  );
};

const Bar: React.FC<{ w: number | string; h?: number; style?: React.CSSProperties }> = ({ w, h = 10, style }) => (
  <div style={{ width: w, height: h, borderRadius: h / 2, background: LINE, ...style }} />
);

/** 메신저: 안 읽은 대화가 쏟아져 목록이 밀려 내려가고, 창 밖 알림이 쌓이며 숫자가 99+가 된다 */
const Pileup: React.FC<V> = ({ f, fps }) => {
  const names = ["팀장님", "고객 문의", "자료 요청", "공지", "단톡방", "거래처", "회의 알림", "재요청"];
  const count = Math.round(interpolate(f, [0.3 * fps, 1.8 * fps], [3, 99], clamp));
  const shown = Math.floor(interpolate(f, [0.1 * fps, 1.7 * fps], [1, names.length], clamp));
  return (
    <>
      <Window f={f} fps={fps} url="messenger.app/inbox" badge={count >= 99 ? "99+" : String(count)}>
        <div style={{ padding: "14px 22px", fontSize: 20, fontWeight: 700 }}>받은 메시지</div>
        {names
          .slice(0, shown)
          .map((n, i) => ({ n, i }))
          .reverse()
          .map(({ n, i }, k) => {
            const p = spring({ frame: f, fps, delay: (0.1 + i * 0.2) * fps, config: { damping: 16 } });
            return (
              <div
                key={n}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 14,
                  padding: "9px 22px",
                  borderTop: `1px solid ${LINE}`,
                  background: k === 0 ? "#fff4ee" : "white",
                  transform: `translateY(${interpolate(p, [0, 1], [-30, 0])}px)`,
                  opacity: p,
                }}
              >
                <div style={{ width: 34, height: 34, borderRadius: "50%", background: AVATAR[i % 4] }} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 16, fontWeight: 700 }}>{n}</div>
                  <Bar w={`${55 + ((i * 17) % 35)}%`} h={8} style={{ marginTop: 6 }} />
                </div>
                <div style={{ minWidth: 26, height: 22, borderRadius: 11, background: RED, color: "white", fontSize: 13, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center" }}>
                  {((i * 7) % 20) + 3}
                </div>
              </div>
            );
          })}
      </Window>
      {[0, 1, 2].map((i) => {
        const p = spring({ frame: f, fps, delay: (0.7 + i * 0.35) * fps, config: { damping: 14 } });
        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: 940,
              top: 170 + i * 74,
              width: 250,
              padding: "12px 16px",
              borderRadius: 14,
              background: "white",
              color: theme.ink,
              boxShadow: "0 14px 30px rgba(0,0,0,0.4)",
              transform: `translateX(${interpolate(p, [0, 1], [320, 0])}px) rotate(${(i - 1) * 2}deg)`,
              opacity: p,
            }}
          >
            <div style={{ fontSize: 14, fontWeight: 700, color: RED }}>새 알림</div>
            <Bar w="90%" h={8} style={{ marginTop: 8 }} />
          </div>
        );
      })}
    </>
  );
};

/** 로딩: 뼈대 화면이 반짝이고 진행 막대가 87%에서 멈춘 뒤 '응답 없음' 창이 뜬다 */
const Waiting: React.FC<V> = ({ f, fps }) => {
  const prog = interpolate(f, [0.2 * fps, 1.1 * fps], [0, 0.87], { ...clamp, easing: Easing.out(Easing.cubic) });
  const shimmer = ((f * 18) % 1200) - 300;
  const dialog = spring({ frame: f, fps, delay: 1.4 * fps, config: { damping: 13 } });
  return (
    <Window f={f} fps={fps} url="service.com/loading">
      <div style={{ height: 4, width: `${prog * 100}%`, background: theme.accent }} />
      <div style={{ padding: 26, display: "flex", flexDirection: "column", gap: 16 }}>
        <Bar w="40%" h={22} />
        <Bar w="85%" />
        <Bar w="70%" />
        <div style={{ display: "flex", gap: 16, marginTop: 8 }}>
          {[0, 1, 2].map((i) => (
            <div key={i} style={{ flex: 1, height: 150, borderRadius: 12, background: SOFT }} />
          ))}
        </div>
      </div>
      <div style={{ position: "absolute", inset: 0, background: `linear-gradient(100deg, transparent ${shimmer}px, rgba(255,255,255,0.75) ${shimmer + 80}px, transparent ${shimmer + 160}px)` }} />
      <svg width={64} height={64} viewBox="0 0 50 50" style={{ position: "absolute", left: 348, top: 130, transform: `rotate(${f * 12}deg)` }}>
        <circle cx={25} cy={25} r={20} fill="none" stroke={LINE} strokeWidth={5} />
        <path d="M25 5 A20 20 0 0 1 45 25" fill="none" stroke={theme.accent} strokeWidth={5} strokeLinecap="round" />
      </svg>
      <div style={{ position: "absolute", left: 0, right: 0, top: 204, textAlign: "center", fontSize: 18, fontWeight: 700, color: theme.sub }}>{Math.round(prog * 100)}%</div>
      <div style={{ position: "absolute", inset: 0, background: `rgba(0,0,0,${0.35 * dialog})` }} />
      <div
        style={{
          position: "absolute",
          left: 200,
          top: 100,
          width: 360,
          padding: "22px 24px",
          borderRadius: 16,
          background: "white",
          boxShadow: "0 20px 50px rgba(0,0,0,0.35)",
          transform: `scale(${dialog})`,
          opacity: dialog,
        }}
      >
        <div style={{ fontSize: 20, fontWeight: 700 }}>페이지가 응답하지 않아요</div>
        <div style={{ fontSize: 15, color: theme.sub, marginTop: 8 }}>계속 기다리거나 페이지를 닫을 수 있어요.</div>
        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end", marginTop: 18 }}>
          <div style={{ padding: "8px 16px", borderRadius: 8, background: SOFT, fontSize: 15, fontWeight: 600 }}>페이지 닫기</div>
          <div style={{ padding: "8px 16px", borderRadius: 8, background: theme.ink, color: "white", fontSize: 15, fontWeight: 600 }}>기다리기</div>
        </div>
      </div>
    </Window>
  );
};

/** 검색: 검색어를 치고 결과를 기다리다 '검색 결과가 없어요'가 뜨고, 다른 곳을 찾느라 탭이 늘어난다 */
const Lost: React.FC<V> = ({ f, fps }) => {
  const query = "필요한 정보 찾기";
  const typed = Math.floor(interpolate(f, [0.15 * fps, 0.8 * fps], [0, query.length], clamp));
  const loading = f > 0.85 * fps && f < 1.25 * fps;
  const empty = spring({ frame: f, fps, delay: 1.25 * fps, config: { damping: 14 } });
  const tabs = Math.floor(interpolate(f, [1.5 * fps, 2.2 * fps], [1, 7], clamp));
  return (
    <Window f={f} fps={fps} url="search.com/?q=…" badge={tabs > 1 ? `탭 ${tabs}개` : undefined}>
      <div style={{ padding: "22px 30px" }}>
        <div style={{ height: 48, borderRadius: 24, border: `2px solid ${theme.accent}`, display: "flex", alignItems: "center", padding: "0 20px", fontSize: 19, fontWeight: 600 }}>
          {query.slice(0, typed)}
          <span style={{ width: 2, height: 22, background: theme.ink, marginLeft: 2, opacity: Math.floor(f / 8) % 2 ? 0 : 1 }} />
        </div>
        {loading && (
          <div style={{ marginTop: 22, display: "flex", flexDirection: "column", gap: 14 }}>
            {[0, 1, 2].map((i) => (
              <Bar key={i} w={`${80 - i * 12}%`} h={14} />
            ))}
          </div>
        )}
        <div style={{ marginTop: 26, display: "flex", flexDirection: "column", alignItems: "center", opacity: empty, transform: `scale(${interpolate(empty, [0, 1], [0.9, 1])})` }}>
          <svg width={86} height={86} viewBox="0 0 24 24" fill="none" stroke="#c4c2bb" strokeWidth={1.6} strokeLinecap="round">
            <circle cx={10.5} cy={10.5} r={6.5} />
            <path d="m15.5 15.5 5 5M8.5 8.5l4 4M12.5 8.5l-4 4" />
          </svg>
          <div style={{ marginTop: 12, fontSize: 24, fontWeight: 700 }}>검색 결과가 없어요</div>
          <div style={{ marginTop: 6, fontSize: 16, color: theme.sub }}>다른 검색어로 다시 찾아보세요</div>
        </div>
      </div>
    </Window>
  );
};

/** 대시보드: 그래프가 오르다 꺾여 떨어지고, 숫자가 빨갛게 줄며 경고가 뜬다 */
const Decline: React.FC<V> = ({ f, fps }) => {
  const draw = interpolate(f, [0.2 * fps, 1.4 * fps], [0, 1], { ...clamp, easing: Easing.inOut(Easing.cubic) });
  const drop = interpolate(f, [0.8 * fps, 1.6 * fps], [0, 1], clamp);
  const toast = spring({ frame: f, fps, delay: 1.5 * fps, config: { damping: 13 } });
  const down = drop > 0.2;
  const cards = [
    { k: "이번 달 성과", v: Math.round(interpolate(drop, [0, 1], [128, 87])), d: Math.round(32 * drop) },
    { k: "방문", v: Math.round(interpolate(drop, [0, 1], [2400, 1310])), d: Math.round(45 * drop) },
  ];
  return (
    <Window f={f} fps={fps} url="dashboard.app/report">
      <div style={{ display: "flex", gap: 16, padding: "20px 24px 0" }}>
        {cards.map((c) => (
          <div key={c.k} style={{ flex: 1, padding: "14px 18px", borderRadius: 12, background: SOFT }}>
            <div style={{ fontSize: 14, color: theme.sub, fontWeight: 600 }}>{c.k}</div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginTop: 4 }}>
              <span style={{ fontSize: 30, fontWeight: 700 }}>{c.v.toLocaleString("ko-KR")}</span>
              <span style={{ fontSize: 16, fontWeight: 700, color: down ? RED : theme.green }}>{down ? `▼ ${c.d}%` : "▲ 3%"}</span>
            </div>
          </div>
        ))}
      </div>
      <svg width={712} height={200} style={{ position: "absolute", left: 24, top: 130 }} fill="none">
        {[0, 1, 2, 3].map((i) => (
          <line key={i} x1={0} x2={712} y1={20 + i * 55} y2={20 + i * 55} stroke={LINE} strokeWidth={1.5} />
        ))}
        <path
          d="M0 150 L120 120 L240 132 L360 70 L420 52"
          stroke={theme.green}
          strokeWidth={5}
          strokeLinecap="round"
          strokeLinejoin="round"
          pathLength={1}
          strokeDasharray="1 1"
          strokeDashoffset={1 - Math.min(1, draw * 1.7)}
        />
        <path
          d="M420 52 L520 120 L610 150 L712 190"
          stroke={RED}
          strokeWidth={5}
          strokeLinecap="round"
          strokeLinejoin="round"
          pathLength={1}
          strokeDasharray="1 1"
          strokeDashoffset={1 - interpolate(draw, [0.6, 1], [0, 1], clamp)}
        />
      </svg>
      <div
        style={{
          position: "absolute",
          right: 22,
          bottom: 18,
          padding: "12px 18px",
          borderRadius: 12,
          background: "#fff0ee",
          border: `1.5px solid ${RED}`,
          color: RED,
          fontSize: 17,
          fontWeight: 700,
          transform: `translateY(${interpolate(toast, [0, 1], [60, 0])}px)`,
          opacity: toast,
        }}
      >
        ⚠ 목표보다 크게 낮아요
      </div>
    </Window>
  );
};

/** 팀 단톡방: 서로 엇갈리는 말이 빠르게 오간다 */
const Tangled: React.FC<V> = ({ f, fps }) => {
  const msgs = [
    { me: false, who: "민수", t: "그거 누가 하기로 했죠?" },
    { me: true, who: "", t: "제가 한 줄 알았는데요" },
    { me: false, who: "지은", t: "저도 어제 했어요…" },
    { me: false, who: "현우", t: "최신 파일이 뭐예요?" },
    { me: true, who: "", t: "??" },
  ];
  return (
    <Window f={f} fps={fps} url="chat.app/team-room" badge="참여자 4">
      <div style={{ padding: "14px 24px", display: "flex", flexDirection: "column", gap: 8 }}>
        {msgs.map((m, i) => {
          const p = spring({ frame: f, fps, delay: (0.15 + i * 0.34) * fps, config: { damping: 15 } });
          return (
            <div
              key={i}
              style={{ alignSelf: m.me ? "flex-end" : "flex-start", display: "flex", alignItems: "flex-end", gap: 10, opacity: p, transform: `translateY(${interpolate(p, [0, 1], [24, 0])}px)` }}
            >
              {!m.me && <div style={{ width: 32, height: 32, borderRadius: "50%", background: AVATAR[i % 4] }} />}
              <div>
                {!m.me && <div style={{ fontSize: 13, color: theme.sub, marginBottom: 3 }}>{m.who}</div>}
                <div style={{ padding: "8px 16px", borderRadius: 16, background: m.me ? theme.accent : SOFT, color: m.me ? "white" : theme.ink, fontSize: 17, fontWeight: 600 }}>{m.t}</div>
              </div>
            </div>
          );
        })}
      </div>
    </Window>
  );
};

const VIGNETTE: Record<Kind, React.FC<V>> = { pileup: Pileup, waiting: Waiting, lost: Lost, decline: Decline, tangled: Tangled };

/**
 * 문제 장면: 처음 INTRO초는 큰 제목, 그다음 불편 하나마다 그 상황을 가상의 인터넷 화면(메신저·로딩·검색·대시보드·단톡방)으로
 * 보여주고 아래에 상황 문장을 띄운다(11/24 피드백). 장면 길이는 backend가 1.4초 + 상황당 2.4초로 잡는다(scene.py STORY_BASE·STORY_SEC).
 */
export const ProblemStory: React.FC<{ scene: T; durationInFrames: number }> = ({ scene, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const items = scene.items.slice(0, 4);
  const n = items.length;
  const intro = Math.min(INTRO * fps, durationInFrames * 0.3);
  const seg = Math.max(1, (durationInFrames - intro) / n);
  const i = frame < intro ? -1 : Math.min(n - 1, Math.floor((frame - intro) / seg));
  const f = i < 0 ? 0 : frame - intro - i * seg;
  const headIn = spring({ frame, fps, config: { damping: 200 } });
  // 제목은 처음엔 가운데 크게, 상황이 시작되면 위로 작게 올라간다
  const lift = interpolate(frame, [intro - 0.35 * fps, intro], [0, 1], { ...clamp, easing: Easing.inOut(Easing.cubic) });
  const item = i >= 0 ? items[i] : undefined;
  const fadeIn = interpolate(f, [0, 0.2 * fps], [0, 1], clamp);
  const fadeOut = i < n - 1 ? interpolate(f, [seg - 0.2 * fps, seg], [1, 0], clamp) : 1;
  const Vignette = item ? VIGNETTE[KIND[item.icon]] : undefined;
  const say = spring({ frame: f, fps, delay: 0.3 * fps, config: { damping: 18 } });

  return (
    <AbsoluteFill style={{ fontFamily: theme.font, color: "white", ...theme.keepAll }}>
      <Backdrop seed={3} dark />
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          top: interpolate(lift, [0, 1], [250, 30]),
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          textAlign: "center",
          opacity: headIn,
          transform: `scale(${interpolate(lift, [0, 1], [1, 0.6])})`,
          transformOrigin: "50% 0",
        }}
      >
        <Pill text={scene.kicker ?? "문제"} color={RED} light />
        <Words
          text={scene.heading}
          delay={0.1}
          style={{ marginTop: 24, fontSize: fitFont(scene.heading, 1060, 60), fontWeight: 700, letterSpacing: "-0.03em", justifyContent: "center", maxWidth: 1100 }}
        />
      </div>
      {item && Vignette && (
        <AbsoluteFill key={i} style={{ opacity: fadeIn * fadeOut }}>
          <Vignette f={f} fps={fps} />
          <div
            style={{
              position: "absolute",
              left: 0,
              right: 0,
              top: 562,
              display: "flex",
              justifyContent: "center",
              alignItems: "center",
              gap: 16,
              opacity: say,
              transform: `translateY(${interpolate(say, [0, 1], [18, 0])}px)`,
            }}
          >
            <span style={{ padding: "4px 12px", borderRadius: 8, background: RED, fontSize: 22, fontWeight: 700 }}>{String(i + 1).padStart(2, "0")}</span>
            <span style={{ fontSize: fitFont(item.text, 960, 46), fontWeight: 700, letterSpacing: "-0.02em" }}>{item.text}</span>
          </div>
        </AbsoluteFill>
      )}
    </AbsoluteFill>
  );
};
