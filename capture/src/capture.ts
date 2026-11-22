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
import { chromium, type Browser, type BrowserContext, type Locator, type Page } from "playwright";
import type { Capture, Scenario } from "@demoday/contracts";

const VIEWPORT = { w: 1280, h: 720 };
const STEP_TIMEOUT = 5000;
const VIDEO_FILE = "capture.webm";
/** 렌더 ScreenScene: 0.1~0.8초 커서 이동, 0.8초 클릭. 바꾸면 둘 다 바꾼다. */
const CURSOR_FROM_MS = 100;
const CLICK_AT_MS = 800;
/** 기준점 오차를 덮는 clip 앞뒤 여유 (click 앞쪽은 박자를 지키려고 두지 않는다) */
const CLIP_PAD_MS = 300;
const TYPE_DELAY_MS = 60;

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
      await page.goto(c.baseUrl.replace(/\/+$/, "") + path, { waitUntil: "load" });
      await enableFlutterSemantics(page);
      return { click: null };
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
      if (loc) await loc.scrollIntoViewIfNeeded();
      else if (!live) await page.mouse.wheel(0, VIEWPORT.h * 0.8);
      else {
        // 한 번에 점프하지 않고 나눠서 부드럽게
        for (let i = 0; i < 8; i++) {
          await page.mouse.wheel(0, (VIEWPORT.h * 0.8) / 8);
          await sleep(50);
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
    for (const step of scenario.auth!.steps) {
      await run(c, step).catch(() => console.warn(`! auth step ${step.id} (${step.action}) 실패 — 건너뜀`));
    }
    await page.waitForLoadState("networkidle", { timeout: 3000 }).catch(() => {});
    const session = (await page
      .evaluate("({ origin: location.origin, items: Object.fromEntries(Object.entries(sessionStorage)) })")
      .catch(() => null)) as Auth["session"];
    return { storageState: await ctx.storageState(), session };
  } finally {
    await ctx.close();
  }
}

/** 녹화 컨텍스트. 만들 수 없으면 녹화 없는 컨텍스트로 대체한다. */
async function recordingContext(browser: Browser, auth: Auth | null, videoDir: string) {
  const base = { viewport: { width: VIEWPORT.w, height: VIEWPORT.h }, storageState: auth?.storageState };
  let ctx: BrowserContext;
  let recording = true;
  try {
    ctx = await browser.newContext({
      ...base,
      recordVideo: { dir: videoDir, size: { width: VIEWPORT.w, height: VIEWPORT.h } },
    });
  } catch (e) {
    console.warn(`! 녹화 컨텍스트 실패 — 정지 화면만: ${msg(e)}`);
    ctx = await browser.newContext(base);
    recording = false;
  }
  if (auth?.session && Object.keys(auth.session.items).length) {
    // sessionStorage는 storageState에 안 들어간다. 같은 origin에서 비어 있는 키만 복원(앱이 바꾼 값은 덮지 않음)
    const s = JSON.stringify(auth.session);
    await ctx.addInitScript({
      content: `(() => { const s = ${s}; if (location.origin !== s.origin) return;
        for (const [k, v] of Object.entries(s.items)) if (sessionStorage.getItem(k) === null) sessionStorage.setItem(k, v); })();`,
    });
  }
  return { ctx, recording };
}

async function main(scenarioPath: string, runDir: string) {
  const scenario: Scenario = JSON.parse(await readFile(scenarioPath, "utf8"));
  await mkdir(join(runDir, "shots"), { recursive: true });
  const videoDir = await mkdtemp(join(tmpdir(), "demoday-video-"));

  const browser = await chromium.launch();
  const shots: Shot[] = [];
  let video: string | undefined;
  try {
    const auth = scenario.auth
      ? await login(browser, scenario).catch(() => (console.warn("! 로그인 컨텍스트 실패 — 로그인 없이 진행"), null))
      : null;
    const { ctx, recording } = await recordingContext(browser, auth, videoDir);
    const page = await ctx.newPage();
    const t0 = Date.now(); // 녹화 기준점(≈ 영상 0초). atMs·clip 모두 이 기준
    page.setDefaultTimeout(STEP_TIMEOUT);
    page.setDefaultNavigationTimeout(STEP_TIMEOUT * 3); // 첫 로딩(콜드 스타트)은 여유를 더 준다
    // 렌더 커서의 출발점과 같게
    const c: Ctx = { page, baseUrl: scenario.baseUrl, shotPath: null, mouse: { x: VIEWPORT.w * 0.62, y: VIEWPORT.h * 0.78 } };

    for (const step of scenario.steps) {
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
        const end = Date.now();
        shot = { stepId: step.id, image, click: r.click, status: "ok", atMs: end - t0 };
        if (recording) {
          const startMs = r.clipStart !== undefined ? r.clipStart - t0 : Math.max(0, stepStart - t0 - CLIP_PAD_MS);
          shot.clip = { startMs, endMs: end - t0 + CLIP_PAD_MS };
        }
      } catch (e) {
        console.warn(`! step ${step.id} (${step.action}) fallback: ${msg(e)}`);
        shot = { stepId: step.id, image, click: null, status: "fallback", atMs: Date.now() - t0 };
      }
      if (!taken) await snap(page, c.shotPath);
      shots.push(shot);
      console.log(`${shot.status === "ok" ? "✓" : "!"} ${image}`);
    }

    await sleep(CLIP_PAD_MS); // 마지막 clip의 뒤 여유만큼 더 녹화
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

const [scenarioPath, runDir] = process.argv.slice(2);
if (!scenarioPath || !runDir) {
  console.error("사용법: capture <scenario.json> <runDir>");
  process.exit(1);
}
main(scenarioPath, runDir).catch((e) => {
  console.error(`✗ ${e instanceof Error ? e.message : e}`);
  process.exit(2);
});
