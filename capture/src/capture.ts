/**
 * scenario.json → <runDir>/capture.json + shots/*.png + capture.webm   (B 담당)
 *
 *   pnpm --filter @demoday/capture capture <scenario.json> <runDir>
 *
 * 규칙
 * - 스크린샷 경로는 runDir 기준 상대경로로 기록 (예: "shots/2.png")
 * - 셀렉터를 못 찾은 단계도 건너뛰지 말고 현재 화면을 찍어 status: "fallback" 으로 기록
 * - 종료 코드: 0 = capture.json 생성됨(fallback 포함), 0 아님 = 생성 실패
 *
 * 녹화
 * - auth는 녹화하지 않는 컨텍스트에서 실행하고, 로그인 상태(storageState + sessionStorage)만 녹화 컨텍스트로 넘긴다.
 *   비밀번호 입력·secret URL이 녹화 파일에 남지 않게 하는 핵심 장치다.
 * - 녹화는 viewport와 같은 1280x720. (Playwright는 CSS 픽셀로 녹화해서 deviceScaleFactor·큰 size로는 선명해지지 않고 여백만 생긴다)
 * - 녹화가 실패하면 video·clip 없이 지금처럼 정지 화면만 낸다(영상은 반드시 나와야 한다).
 * - clip 기준점(0)은 녹화 페이지를 연 직후. 녹화 시작 시각 API가 없어 ±0.2초 오차가 있다.
 *   click·type 단계는 clip.startMs + CLICK_AT_MS에 클릭한다 — 렌더의 커서 애니메이션과 같은 박자.
 */
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import { agentSteps } from "./agent";
import { chromium, type Browser, type BrowserContext, type Locator, type Page } from "playwright";
import type { Capture, Scenario } from "@demoday/contracts";

const VIEWPORT = { w: 1280, h: 720 };
const STEP_TIMEOUT = 5000;
const VIDEO_FILE = "capture.webm";
/** 렌더 ScreenScene: 0.1~0.8초 커서 이동, 0.8초 클릭. 바꾸면 둘 다 바꾼다. */
const CURSOR_FROM_MS = 100;
const CLICK_AT_MS = 800;
/** 기준점 오차를 덮는 clip 앞 여유 (click은 박자를 지키려고 두지 않는다). 앞 clip과는 겹치지 않게 자른다 */
const CLIP_PAD_MS = 300;
/** 단계 뒤 결과 화면을 이만큼 더 녹화해 clip에 넣는다 — 장면이 늘어나도 0.5배속·정지가 덜 생긴다 */
const HOLD_MS = 1500;
/** 스크린샷이 끝내 실패한 단계에 쓰는 1x1 회색 PNG(렌더가 1280x720로 늘린다). 파일이 없으면 렌더가 깨진다 */
const BLANK_PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4/OkdAAWvAtR7z8HDAAAAAElFTkSuQmCC", "base64");
const TYPE_DELAY_MS = 60;
/** 스크롤 한 번(화면 0.8배)을 이 시간 동안 이만큼 나눠 굴린다 */
const SCROLL_MS = 1200;
const SCROLL_STEPS = 24;

type Step = Scenario["steps"][number];
type Shot = Capture["shots"][number];
type Point = { x: number; y: number };

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const msg = (e: unknown) => (e instanceof Error ? e.message.split("\n")[0] : String(e));

async function center(loc: Locator): Promise<Point | null> {
  const box = await loc.boundingBox();
  return box ? { x: Math.round(box.x + box.width / 2), y: Math.round(box.y + box.height / 2) } : null;
}

/**
 * Flutter web은 canvas라 셀렉터가 없다. semantics를 켜면 role=button[name="…"] 등이 동작한다.
 * 해시 라우팅으로 같은 문서에 머물면 이미 켜져 있으므로(placeholder 없음) flt-semantics 노드로도 기다림을 끝낸다.
 */
async function enableFlutterSemantics(page: Page) {
  // load 시점엔 엔진이 아직 flutter-view를 안 만들었을 수 있어 로더 전역(_flutter)으로 먼저 판별한다
  const isFlutter =
    (await page.evaluate("'_flutter' in window").catch(() => false)) ||
    (await page.locator("flutter-view, flt-glass-pane").count()) > 0;
  if (!isFlutter) return;
  await page.locator("flt-semantics-placeholder, flt-semantics").first().waitFor({ state: "attached", timeout: 10_000 }).catch(() => {});
  await page.locator("flt-semantics-placeholder").first().dispatchEvent("click", undefined, { timeout: 1000 }).catch(() => {});
}

/** 로딩 뼈대(skeleton)가 이만큼 기다려도 남아 있으면 빈 화면으로 보고 fallback — 영상에서 빠진다 */
const LOADING_WAIT_MS = 3000;
const LOGIN_PATH = /\/(login|signin|sign-in)\b/i;
const SKELETON = '[class*="skeleton" i], [class*="animate-pulse"], [class*="shimmer" i], [aria-busy="true"]';

/**
 * 화면 안에 로딩 뼈대가 보이는 동안 기다리고, 끝까지 남으면 true.
 * 상태가 필요한 페이지(/report 등)를 URL로 바로 열면 데이터가 없어 뼈대만 남는다(채움 11/23 실측).
 * ponytail: 클래스 이름 휴리스틱 — 일부 카드만 로딩 중인 정상 화면도 빠질 수 있다. 오탐이 보이면 화면 대비 뼈대 면적으로 바꾼다.
 */
async function stillLoading(page: Page): Promise<boolean> {
  const visible = () =>
    page
      .evaluate((sel) => {
        return [...document.querySelectorAll(sel)].some((e) => {
          const r = e.getBoundingClientRect();
          return r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < innerHeight;
        });
      }, SKELETON)
      .catch(() => false);
  for (const end = Date.now() + LOADING_WAIT_MS; Date.now() < end; await sleep(250)) {
    if (!(await visible())) return false;
  }
  return visible();
}

/** 실패하면 기본 타임아웃으로 한 번 더 찍는다. */
async function snap(page: Page, path: string) {
  await page.screenshot({ path, timeout: STEP_TIMEOUT }).catch(() => page.screenshot({ path }));
}

/** 마우스를 from → to로 durationMs 동안 움직인다(호버 효과용. 커서 그림은 렌더가 그린다). */
async function glide(page: Page, from: Point, to: Point, durationMs: number) {
  const n = 14;
  for (let i = 1; i <= n; i++) {
    const t = i / n;
    await page.mouse.move(from.x + (to.x - from.x) * t, from.y + (to.y - from.y) * t);
    await sleep(durationMs / n);
  }
}

type Ctx = { page: Page; baseUrl: string; shotPath: string | null; mouse: Point };
type Result = { click: Point | null; taken?: boolean; clipStart?: number };

/**
 * 단계를 실행하고 클릭 좌표를 돌려준다. 실패하면 throw.
 * click은 좌표가 클릭 전 화면 기준이므로 클릭 직전에 찍는다(taken). 클릭 결과는 다음 단계 화면에 나온다.
 * shotPath가 null이면(auth 단계) 찍지 않고, 사람처럼 천천히 움직이지도 않는다.
 * 일반 단계 입력값은 가리지 않는다(LLM이 만든 데모 문구). auth 값은 찍지도 로그에 쓰지도 않는다.
 */
async function run(c: Ctx, step: Step): Promise<Result> {
  const { page } = c;
  const live = c.shotPath !== null; // 녹화되는 본 단계
  const loc = step.selector ? page.locator(step.selector).first() : null;
  switch (step.action) {
    case "goto": {
      // new URL(path, base)는 base의 하위 경로(/repo/)를 버리므로 문자열로 이어 붙인다. 해시(/#/x)·쿼리도 그대로.
      const path = step.path!.startsWith("/") ? step.path! : `/${step.path}`;
      const res = await page.goto(c.baseUrl.replace(/\/+$/, "") + path, { waitUntil: "load" });
      // 없는 페이지(404 등)는 정상 장면처럼 들어가지 않게 fallback으로. 메시지에 URL은 넣지 않는다(auth secret)
      if (res && res.status() >= 400) throw new Error(`HTTP ${res.status()}`);
      // clip은 페이지가 뜬 뒤부터 — 로딩 중 빈 화면이 장면 앞을 채우지 않게
      const clipStart = Date.now();
      await enableFlutterSemantics(page);
      return { click: null, clipStart };
    }
    case "click": {
      // trial: 클릭 없이 스크롤·actionability만 확인. 리렌더로 요소가 바뀌어도 재시도한다(scrollIntoViewIfNeeded는 안 함)
      await loc!.click({ trial: true });
      const click = await center(loc!);
      if (!live || !click) {
        if (c.shotPath) await snap(page, c.shotPath);
        await loc!.click();
        return { click, taken: live };
      }
      await snap(page, c.shotPath!);
      // 렌더 박자: clip 시작 0.1초 뒤부터 커서 이동, 0.8초에 클릭
      const clipStart = Date.now();
      await sleep(CURSOR_FROM_MS);
      await glide(page, c.mouse, click, CLICK_AT_MS - CURSOR_FROM_MS - 80);
      await sleep(Math.max(0, clipStart + CLICK_AT_MS - Date.now()));
      await page.mouse.click(click.x, click.y);
      c.mouse = click;
      return { click, taken: true, clipStart };
    }
    case "type": {
      await loc!.click({ trial: true });
      const click = await center(loc!);
      if (!live) {
        await loc!.fill(step.value!);
        return { click };
      }
      // click과 같은 박자: clip 시작 0.8초에 입력칸을 누르고 한 글자씩 입력
      const clipStart = Date.now();
      if (click) {
        await sleep(CURSOR_FROM_MS);
        await glide(page, c.mouse, click, CLICK_AT_MS - CURSOR_FROM_MS - 80);
        await sleep(Math.max(0, clipStart + CLICK_AT_MS - Date.now()));
        c.mouse = click;
      }
      await loc!.click();
      await loc!.fill("");
      await loc!.pressSequentially(step.value!, { delay: TYPE_DELAY_MS });
      return { click, clipStart };
    }
    case "scroll":
      if (loc) {
        await loc.scrollIntoViewIfNeeded();
        return { click: null };
      }
      // 휠은 마우스 아래 요소로 간다. goto 직후 (0,0)이면 고정 메뉴 위라 안쪽 div가 스크롤되는 사이트(nuxt/movies)에서 안 움직인다
      c.mouse = { x: VIEWPORT.w / 2, y: VIEWPORT.h / 2 };
      await page.mouse.move(c.mouse.x, c.mouse.y);
      if (!live) await page.mouse.wheel(0, VIEWPORT.h * 0.8);
      else {
        // 천천히 출발해 천천히 멈추게(ease-in-out) 잘게 나눠 굴린다. 0.4초에 8번 굴리던 것은 렌더가 빨리 재생하면 툭툭 끊겼다
        const total = VIEWPORT.h * 0.8;
        const steps = SCROLL_STEPS;
        const at = (i: number) => total * (1 - Math.cos((Math.PI * i) / steps)) / 2;
        for (let i = 1; i <= steps; i++) {
          await page.mouse.wheel(0, at(i) - at(i - 1));
          await sleep(SCROLL_MS / steps);
        }
      }
      return { click: null };
    case "wait":
      await page.waitForTimeout(1000);
      return { click: null };
  }
}

type Auth = { storageState: Awaited<ReturnType<BrowserContext["storageState"]>>; session: { origin: string; items: Record<string, string> } | null };

/** 녹화하지 않는 컨텍스트에서 로그인하고 상태만 꺼낸다. 실패한 단계는 건너뛴다(값·URL·에러는 로그에 안 씀). */
async function login(browser: Browser, scenario: Scenario): Promise<Auth> {
  const ctx = await browser.newContext({ viewport: { width: VIEWPORT.w, height: VIEWPORT.h } });
  try {
    const page = await ctx.newPage();
    page.setDefaultTimeout(STEP_TIMEOUT);
    page.setDefaultNavigationTimeout(STEP_TIMEOUT * 3);
    const c: Ctx = { page, baseUrl: scenario.baseUrl, shotPath: null, mouse: { x: 0, y: 0 } };
    const steps = scenario.auth!.steps;
    const lastClick = steps.map((s) => s.action).lastIndexOf("click");
    for (const [i, step] of steps.entries()) {
      const before = page.url();
      await run(c, step).catch(() => console.warn(`! auth step ${step.id} (${step.action}) 실패 — 건너뜀`));
      // 로그인 버튼 뒤: 응답 전에 상태를 꺼내거나 컨텍스트를 닫으면 로그인 요청이 끊긴다 → 페이지가 넘어갈 때까지 기다린다
      if (i === lastClick) await page.waitForURL((u) => u.href !== before, { timeout: 8000 }).catch(() => {});
    }
    await page.waitForLoadState("networkidle", { timeout: 3000 }).catch(() => {});
    const session = (await page
      .evaluate("({ origin: location.origin, items: Object.fromEntries(Object.entries(sessionStorage)) })")
      .catch(() => null)) as Auth["session"];
    // indexedDB: Firebase Auth(JS·Flutter firebase_auth) 등은 토큰을 IndexedDB에 둔다(기본값은 빠짐)
    return { storageState: await ctx.storageState({ indexedDB: true }), session };
  } finally {
    await ctx.close();
  }
}

/**
 * 녹화 컨텍스트와 페이지. 녹화는 페이지를 만들 때 시작하므로(ffmpeg가 없으면 여기서 실패) newPage까지 시도하고,
 * 실패하면 녹화 없는 컨텍스트로 대체한다.
 */
async function recordingPage(browser: Browser, auth: Auth | null, videoDir: string) {
  const base = { viewport: { width: VIEWPORT.w, height: VIEWPORT.h }, storageState: auth?.storageState };
  const open = async (record: boolean) => {
    const ctx: BrowserContext = await browser.newContext(
      record ? { ...base, recordVideo: { dir: videoDir, size: { width: VIEWPORT.w, height: VIEWPORT.h } } } : base,
    );
    try {
      if (auth?.session && Object.keys(auth.session.items).length) {
        // sessionStorage는 storageState에 안 들어간다. 같은 origin에서 비어 있는 키만 복원(앱이 바꾼 값은 덮지 않음)
        const s = JSON.stringify(auth.session);
        await ctx.addInitScript({
          content: `(() => { const s = ${s}; if (location.origin !== s.origin) return;
            for (const [k, v] of Object.entries(s.items)) if (sessionStorage.getItem(k) === null) sessionStorage.setItem(k, v); })();`,
        });
      }
      return { ctx, page: await ctx.newPage(), recording: record };
    } catch (e) {
      await ctx.close().catch(() => {});
      throw e;
    }
  };
  return open(true).catch((e) => {
    console.warn(`! 녹화 시작 실패 — 정지 화면만: ${msg(e)}`);
    return open(false);
  });
}

type AgentArgs = { goal: string; script?: string; cmd: string } | null;

async function main(scenarioPath: string, runDir: string, agent: AgentArgs) {
  // 에이전트 모드는 끝나면 scenario.json 을 실제로 한 동작으로 덮어쓴다 — 원래 시나리오는 처음 한 번 plan 으로 남겨
  // 다시 돌릴 때(에이전트 실패 시 대신 쓸 단계) 읽는다
  const plan = join(runDir, "scenario.plan.json");
  const hasPlan = agent !== null && (await readFile(plan, "utf8").then(() => true, () => false));
  const scenario: Scenario = JSON.parse(await readFile(hasPlan ? plan : scenarioPath, "utf8"));
  if (agent && !hasPlan) await writeFile(plan, JSON.stringify(scenario, null, 2));
  await mkdir(join(runDir, "shots"), { recursive: true });
  const videoDir = await mkdtemp(join(tmpdir(), "demoday-video-"));

  const browser = await chromium.launch();
  const shots: Shot[] = [];
  let video: string | undefined;
  try {
    const auth = scenario.auth
      ? await login(browser, scenario).catch(() => (console.warn("! 로그인 컨텍스트 실패 — 로그인 없이 진행"), null))
      : null;
    const { ctx, page, recording } = await recordingPage(browser, auth, videoDir);
    const t0 = Date.now(); // 녹화 기준점(≈ 영상 0초). atMs·clip 모두 이 기준
    page.setDefaultTimeout(STEP_TIMEOUT);
    page.setDefaultNavigationTimeout(STEP_TIMEOUT * 3); // 첫 로딩(콜드 스타트)은 여유를 더 준다
    // 렌더 커서의 출발점과 같게
    const c: Ctx = { page, baseUrl: scenario.baseUrl, shotPath: null, mouse: { x: VIEWPORT.w * 0.62, y: VIEWPORT.h * 0.78 } };

    let prevEnd = 0; // 앞 clip 끝(ms)
    // 에이전트 모드면 화면을 보고 고른 동작이 단계가 된다(#53). 실행·녹화는 아래 그대로
    const executed: Step[] = [];
    const source: AsyncIterable<Step> | Step[] = agent
      ? agentSteps({ page, runDir, scenario, ...agent, snap, lastOk: () => shots.at(-1)?.status === "ok" }, executed)
      : scenario.steps;
    if (agent) {
      await rm(join(runDir, "agent"), { recursive: true, force: true }); // 이전 실행의 관찰이 섞이지 않게
      await mkdir(join(runDir, "agent"), { recursive: true });
    }
    for await (const step of source) {
      const image = `shots/${step.id}.png`;
      c.shotPath = join(runDir, image);
      const stepStart = Date.now();
      let shot: Shot;
      let taken = false;
      try {
        const r = await run(c, step);
        taken = r.taken ?? false;
        // 클릭·이동 후 화면이 안정될 때까지 잠깐 기다린다(실패해도 무시)
        await page.waitForLoadState("networkidle", { timeout: 2000 }).catch(() => {});
        if (await stillLoading(page)) throw new Error("로딩 화면에서 멈춤 — 보여줄 내용 없음");
        // 로그인이 필요한 페이지는 로그인 화면으로 보내진다 — 자막(원래 페이지 설명)과 화면이 어긋난다
        if (step.action === "goto" && !LOGIN_PATH.test(step.path!) && LOGIN_PATH.test(new URL(page.url()).pathname + new URL(page.url()).hash)) {
          throw new Error("로그인 화면으로 이동함");
        }
        shot = { stepId: step.id, image, click: r.click, status: "ok", atMs: Date.now() - t0 };
        if (recording) {
          await sleep(HOLD_MS); // 결과 화면을 더 녹화
          // 클릭 단계는 클릭 직전에 찍혔다 — 녹화가 있으면 장면은 영상이 그리므로, 스크린샷(대체 화면·이미지 모델 근거)을
          // clip 마지막 프레임과 같게 덮어쓴다. 실패하면 클릭 직전 화면을 그대로 둔다
          if (taken) await snap(page, c.shotPath).catch(() => {});
          // 앞 clip 끝과 겹치지 않게(겹치면 장면이 바뀔 때 앞 장면 끝이 되감겨 보인다)
          const startMs = r.clipStart !== undefined ? r.clipStart - t0 : Math.max(prevEnd, stepStart - t0 - CLIP_PAD_MS);
          shot.clip = { startMs, endMs: Date.now() - t0 };
          prevEnd = shot.clip.endMs;
        }
      } catch (e) {
        console.warn(`! step ${step.id} (${step.action}) fallback: ${msg(e)}`);
        shot = { stepId: step.id, image, click: null, status: "fallback", atMs: Date.now() - t0 };
      }
      if (!taken) {
        // 페이지가 응답하지 않아 찍지 못해도 멈추지 않는다 — 빈 화면을 쓰고 fallback
        const atMs = shot.atMs;
        await snap(page, c.shotPath).catch(async (e) => {
          console.warn(`! step ${step.id} 스크린샷 실패 — 빈 화면: ${msg(e)}`);
          await writeFile(c.shotPath!, BLANK_PNG);
          shot = { stepId: step.id, image, click: null, status: "fallback", atMs };
        });
      }
      shots.push(shot);
      console.log(`${shot.status === "ok" ? "✓" : "!"} ${image}`);
    }
    if (agent) {
      // 실제로 한 동작을 시나리오로 남긴다 — scene 은 이 단계의 caption·stepId 로 자막을 만든다. auth 등 나머지는 그대로
      await writeFile(join(runDir, "scenario.json"), JSON.stringify({ ...scenario, steps: executed }, null, 2));
      console.log(`✓ 에이전트 ${executed.length}단계 → ${join(runDir, "scenario.json")}`);
    }

    await sleep(CLIP_PAD_MS); // 기준점 오차만큼 더 녹화해 마지막 clip 끝이 영상 안에 들어가게
    const rec = page.video();
    await ctx.close(); // 녹화 파일은 컨텍스트를 닫아야 완성된다
    if (recording && rec) {
      video = await rec
        .saveAs(join(runDir, VIDEO_FILE))
        .then(() => VIDEO_FILE)
        .catch((e) => (console.warn(`! 녹화 저장 실패 — 정지 화면만: ${msg(e)}`), undefined));
    }
  } finally {
    await browser.close();
    await rm(videoDir, { recursive: true, force: true });
  }

  if (!video) for (const s of shots) delete s.clip; // 영상이 없으면 구간도 의미가 없다
  const capture: Capture = { viewport: VIEWPORT, shots, ...(video && { video }) };
  await writeFile(join(runDir, "capture.json"), JSON.stringify(capture, null, 2));
  const fallbacks = shots.filter((s) => s.status === "fallback").length;
  console.log(`✓ ${join(runDir, "capture.json")} (${fallbacks} fallback, ${video ? VIDEO_FILE : "녹화 없음"})`);
}

const { values: opt, positionals } = parseArgs({
  allowPositionals: true,
  options: { agent: { type: "boolean" }, goal: { type: "string" }, "agent-script": { type: "string" } },
});
const [scenarioPath, runDir] = positionals;
if (!scenarioPath || !runDir) {
  console.error("사용법: capture <scenario.json> <runDir> [--agent [--goal <목표>] [--agent-script <actions.json>]]");
  process.exit(1);
}
// 에이전트 모드: --agent 또는 CAPTURE_MODE=agent. 에이전트 명령은 DEMODAY_AGENT_CMD(기본: A의 app.agent)
const agentOn = opt.agent || Boolean(opt["agent-script"]) || process.env.CAPTURE_MODE === "agent";
const agentArgs: AgentArgs = agentOn
  ? {
      goal: opt.goal || "이 서비스의 핵심 기능을 처음 쓰는 사람처럼 직접 써 보며 보여준다",
      script: opt["agent-script"],
      // cd·작은따옴표 없이 — Windows cmd.exe 에서도 그대로 동작한다(경로는 큰따옴표)
      cmd: process.env.DEMODAY_AGENT_CMD || `uv run --directory "${fileURLToPath(new URL("../../backend", import.meta.url))}" python -m app.agent`,
    }
  : null;
main(scenarioPath, runDir, agentArgs).catch((e) => {
  console.error(`✗ ${e instanceof Error ? e.message : e}`);
  process.exit(2);
});
