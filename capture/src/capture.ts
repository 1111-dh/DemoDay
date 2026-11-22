/**
 * scenario.json → <runDir>/capture.json + <runDir>/shots/*.png   (B 담당)
 *
 *   pnpm --filter @demoday/capture capture <scenario.json> <runDir>
 *
 * 규칙
 * - 스크린샷 경로는 runDir 기준 상대경로로 기록 (예: "shots/2.png")
 * - 셀렉터를 못 찾은 단계도 건너뛰지 말고 현재 화면을 찍어 status: "fallback" 으로 기록
 * - 종료 코드: 0 = capture.json 생성됨(fallback 포함), 0 아님 = 생성 실패
 */
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { chromium, type Locator, type Page } from "playwright";
import type { Capture, Scenario } from "@demoday/contracts";

const VIEWPORT = { w: 1280, h: 720 };
const STEP_TIMEOUT = 5000;

type Step = Scenario["steps"][number];
type Shot = Capture["shots"][number];

async function center(loc: Locator) {
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

/** 입력값이 보이지 않게 지금까지 type한 입력칸을 모두 가리고 찍는다. 실패해도 마스크 없이 다시 찍지 않는다. */
async function snap(page: Page, path: string, typed: Locator[]) {
  const opts = { path, mask: typed, maskColor: "#d1d5db" };
  await page.screenshot({ ...opts, timeout: STEP_TIMEOUT }).catch(() => page.screenshot(opts));
}

/**
 * 단계를 실행하고 클릭 좌표를 돌려준다. 실패하면 throw.
 * click은 좌표가 클릭 전 화면 기준이므로 클릭 직전에 찍는다(taken). 클릭 결과는 다음 단계 화면에 나온다.
 * shotPath가 null이면(auth 단계) 찍지 않는다.
 * typed: 실행 내내 공유하는 입력칸 목록. type 단계가 채우기 전에 추가하고, 이후 모든 스크린샷이 가린다.
 */
async function run(page: Page, baseUrl: string, step: Step, shotPath: string | null, typed: Locator[]) {
  const loc = step.selector ? page.locator(step.selector).first() : null;
  switch (step.action) {
    case "goto": {
      // new URL(path, base)는 base의 하위 경로(/repo/)를 버리므로 문자열로 이어 붙인다. 해시(/#/x)·쿼리도 그대로.
      const path = step.path!.startsWith("/") ? step.path! : `/${step.path}`;
      await page.goto(baseUrl.replace(/\/+$/, "") + path, { waitUntil: "load" });
      await enableFlutterSemantics(page);
      return { click: null };
    }
    case "click": {
      // trial: 클릭 없이 스크롤·actionability만 확인. 리렌더로 요소가 바뀌어도 재시도한다(scrollIntoViewIfNeeded는 안 함)
      await loc!.click({ trial: true });
      const click = await center(loc!);
      if (shotPath) await snap(page, shotPath, typed);
      await loc!.click();
      return { click, taken: true };
    }
    case "type": {
      await loc!.click({ trial: true });
      const click = await center(loc!);
      typed.push(loc!); // fill이 중간에 실패해도 fallback 화면에서 가려지도록 먼저 넣는다
      await loc!.fill(step.value!);
      return { click };
    }
    case "scroll":
      if (loc) await loc.scrollIntoViewIfNeeded();
      else await page.mouse.wheel(0, VIEWPORT.h * 0.8);
      return { click: null };
    case "wait":
      await page.waitForTimeout(1000);
      return { click: null };
  }
}

async function main(scenarioPath: string, runDir: string) {
  const scenario: Scenario = JSON.parse(await readFile(scenarioPath, "utf8"));
  await mkdir(join(runDir, "shots"), { recursive: true });

  const browser = await chromium.launch();
  const shots: Shot[] = [];
  try {
    const page = await browser.newPage({ viewport: { width: VIEWPORT.w, height: VIEWPORT.h } });
    page.setDefaultTimeout(STEP_TIMEOUT);
    page.setDefaultNavigationTimeout(STEP_TIMEOUT * 3); // 첫 로딩(콜드 스타트)은 여유를 더 준다

    // 로그인: 같은 컨텍스트에서 먼저 실행(쿠키·localStorage 유지). 찍지 않고, 값·URL·에러 메시지를 로그에 쓰지 않는다.
    for (const step of scenario.auth?.steps ?? []) {
      await run(page, scenario.baseUrl, step, null, []).catch(() => console.warn(`! auth step ${step.id} (${step.action}) 실패 — 건너뜀`));
    }
    if (scenario.auth) await page.waitForLoadState("networkidle", { timeout: 3000 }).catch(() => {});

    const start = Date.now();
    const typed: Locator[] = [];

    for (const step of scenario.steps) {
      const image = `shots/${step.id}.png`;
      let shot: Shot;
      let taken = false;
      try {
        const r = await run(page, scenario.baseUrl, step, join(runDir, image), typed);
        taken = r.taken ?? false;
        // 클릭·이동 후 화면이 안정될 때까지 잠깐 기다린다(실패해도 무시)
        await page.waitForLoadState("networkidle", { timeout: 2000 }).catch(() => {});
        shot = { stepId: step.id, image, click: r.click, status: "ok", atMs: Date.now() - start };
      } catch (e) {
        console.warn(`! step ${step.id} (${step.action}) fallback: ${e instanceof Error ? e.message.split("\n")[0] : e}`);
        shot = { stepId: step.id, image, click: null, status: "fallback", atMs: Date.now() - start };
      }
      if (!taken) await snap(page, join(runDir, image), typed);
      shots.push(shot);
      console.log(`${shot.status === "ok" ? "✓" : "!"} ${image}`);
    }
  } finally {
    await browser.close();
  }

  const capture: Capture = { viewport: VIEWPORT, shots };
  await writeFile(join(runDir, "capture.json"), JSON.stringify(capture, null, 2));
  console.log(`✓ ${join(runDir, "capture.json")} (${shots.filter((s) => s.status === "fallback").length} fallback)`);
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
