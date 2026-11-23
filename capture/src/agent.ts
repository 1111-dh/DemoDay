/**
 * 에이전트 녹화 모드(#53) — 화면을 관찰해 에이전트(A, 자식 프로세스)에게 보내고, 돌아온 다음 동작을 scenario Step 으로 바꿔 내놓는다.
 * 실행·녹화·clip·스크린샷은 capture.ts 루프가 기존 방식 그대로 한다. 여기는 "다음 단계를 어디서 얻나"만 담당한다.
 *
 * 통신: 관찰 JSON 한 줄(stdin) → 동작 JSON 한 줄(stdout). 형식은 이슈 #53.
 * 에이전트를 못 띄우거나 첫 동작부터 실패하면 시나리오 단계로 대신한다(영상은 나와야 한다).
 */
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { createInterface, type Interface } from "node:readline";
import type { Page } from "playwright";
import type { Scenario } from "@demoday/contracts";

type Step = Scenario["steps"][number];
type Box = { x: number; y: number; w: number; h: number };
export type UiElement = { id: number; role: string; name: string; box: Box };
export type Action = { action: "click" | "type" | "scroll" | "done"; id?: number; value?: string; caption?: string };
type History = { action: string; id?: number; value?: string; caption?: string; ok: boolean };
type Observation = { goal: string; step: number; url: string; screenshot: string; elements: UiElement[]; history: History[] };

export const MAX_AGENT_STEPS = 10;
const MAX_ELEMENTS = 60;
const DECIDE_TIMEOUT_MS = 60_000;
const ATTR = "data-demoday-id";
const LOGIN_PATH = /\/(login|signin|sign-in)\b/i;

/**
 * 화면 안에 보이는 클릭·입력 가능한 요소에 번호를 붙여(data-demoday-id) 돌려준다. 위→아래, 왼→오른쪽 순.
 * 녹화에 남지 않게 화면에는 아무것도 그리지 않는다(번호 표시는 에이전트가 box 로 그린다).
 */
export async function elements(page: Page): Promise<UiElement[]> {
  // tsx(esbuild keepNames)가 아래 함수 안 화살표 함수에 __name(...) 호출을 끼워 넣는다 — 페이지에는 없으니 빈 함수로 둔다
  await page.evaluate("globalThis.__name ??= (f) => f").catch(() => {});
  return page
    .evaluate(
      ({ attr, max }) => {
        document.querySelectorAll(`[${attr}]`).forEach((e) => e.removeAttribute(attr));
        const sel =
          'a[href], button, input:not([type="hidden"]), textarea, select, [contenteditable="true"], [onclick], ' +
          '[role="button"], [role="link"], [role="tab"], [role="menuitem"], [role="checkbox"], [role="textbox"], [role="searchbox"], [role="combobox"]';
        const roleOf = (e: Element) => {
          const r = e.getAttribute("role");
          if (r) return r;
          const tag = e.tagName.toLowerCase();
          const type = (e.getAttribute("type") || "text").toLowerCase();
          if (tag === "a") return "link";
          if (tag === "textarea" || e.getAttribute("contenteditable") === "true") return "textbox";
          if (tag === "select") return "combobox";
          if (tag === "input") return ["checkbox", "radio"].includes(type) ? type : ["submit", "button"].includes(type) ? "button" : "textbox";
          return "button";
        };
        const nameOf = (e: HTMLElement) =>
          (
            e.getAttribute("aria-label") ||
            e.innerText ||
            e.getAttribute("placeholder") ||
            e.getAttribute("title") ||
            e.querySelector("img")?.getAttribute("alt") ||
            (e as HTMLInputElement).value ||
            ""
          )
            .replace(/\s+/g, " ")
            .trim()
            .slice(0, 40);
        const seen = new Set<Element>();
        const out: { el: HTMLElement; role: string; name: string; box: { x: number; y: number; w: number; h: number } }[] = [];
        for (const e of document.querySelectorAll<HTMLElement>(sel)) {
          // 안쪽 요소가 같은 컨트롤의 일부면(버튼 안의 span 등) 바깥 것 하나만
          if ([...seen].some((s) => s.contains(e))) continue;
          const r = e.getBoundingClientRect();
          const st = getComputedStyle(e);
          if (r.width < 4 || r.height < 4 || r.bottom <= 0 || r.top >= innerHeight || r.right <= 0 || r.left >= innerWidth) continue;
          if (st.visibility === "hidden" || st.display === "none" || Number(st.opacity) === 0 || (e as HTMLButtonElement).disabled) continue;
          // 가운데 점에 실제로 보이는 게 이 요소(또는 안쪽)여야 한다 — 닫힌 드롭다운·가려진 요소·숨긴 라디오를 뺀다
          const cx = Math.min(innerWidth - 1, Math.max(0, r.x + r.width / 2));
          const cy = Math.min(innerHeight - 1, Math.max(0, r.y + r.height / 2));
          const top = document.elementFromPoint(cx, cy);
          if (!top || !(e === top || e.contains(top) || (top as HTMLElement).closest?.("label")?.contains(e))) continue;
          seen.add(e);
          out.push({ el: e, role: roleOf(e), name: nameOf(e), box: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) } });
        }
        out.sort((a, b) => a.box.y - b.box.y || a.box.x - b.box.x);
        return out.slice(0, max).map((o, i) => {
          o.el.setAttribute(attr, String(i + 1));
          return { id: i + 1, role: o.role, name: o.name, box: o.box };
        });
      },
      { attr: ATTR, max: MAX_ELEMENTS },
    )
    .catch(() => []);
}

/** scenario.json 에 남길 안정적인 셀렉터. 실행은 data-demoday-id 로 하고, 기록은 다시 돌려도 찾을 수 있는 이름 기반으로. */
export function stableSelector(e: UiElement): string {
  // 화살표·꺾쇠 같은 장식 기호는 접근성 이름에 안 들어가는 경우가 많다(아이콘) — 빼고 앞부분만(이름은 부분 일치)
  const name = e.name.replace(/[←-⇿➔-➿›»<>]/g, "").trim().slice(0, 30).trim().replace(/"/g, '\\"');
  if (name && ["button", "link", "textbox", "searchbox", "combobox", "tab", "menuitem", "checkbox", "radio"].includes(e.role)) {
    return `role=${e.role}[name="${name}"]`;
  }
  return name ? `text=${name}` : `[${ATTR}="${e.id}"]`;
}

/** 동작 형식 검사. 틀리면 null(건너뛰고 history 에 ok:false). */
export function validAction(a: unknown, ids: Set<number>): Action | null {
  if (!a || typeof a !== "object") return null;
  const { action, id, value, caption } = a as Record<string, unknown>;
  if (action === "done" || action === "scroll") return { action, caption: typeof caption === "string" ? caption : undefined };
  if (action !== "click" && action !== "type") return null;
  if (typeof id !== "number" || !ids.has(id)) return null;
  if (action === "type" && (typeof value !== "string" || !value)) return null;
  return { action, id, value: action === "type" ? (value as string) : undefined, caption: typeof caption === "string" ? caption : undefined };
}

/** 에이전트와 한 줄씩 주고받는 연결. --script 면 정해진 동작을 순서대로 돌려주는 가짜 에이전트(A 없이 개발·테스트). */
interface Decider {
  decide(obs: Observation): Promise<unknown>;
  close(): void;
}

/** 동작에 id 대신 name 을 쓰면 그 화면에서 이름이 들어간 요소(role 이 맞으면 우선)로 바꾼다 — 번호는 화면마다 달라서 */
async function scriptDecider(file: string): Promise<Decider> {
  const actions: Record<string, unknown>[] = JSON.parse(await readFile(file, "utf8"));
  let i = 0;
  return {
    decide: async (obs) => {
      const a = actions[i++] ?? { action: "done" };
      if (typeof a.name !== "string" || a.id !== undefined) return a;
      const hits = obs.elements.filter((e) => e.name.includes(a.name as string));
      const want = a.action === "type" ? ["textbox", "searchbox", "combobox"] : ["button", "link", "tab", "menuitem"];
      const hit = hits.find((e) => want.includes(e.role)) ?? hits[0];
      return { ...a, id: hit?.id ?? -1 };
    },
    close: () => {},
  };
}

function processDecider(cmd: string): Decider {
  const child: ChildProcessWithoutNullStreams = spawn(cmd, { shell: true, stdio: ["pipe", "pipe", "pipe"] });
  child.stderr.on("data", (d) => process.stderr.write(`  [agent] ${d}`));
  const lines: Interface = createInterface({ input: child.stdout });
  const queue: ((line: string | null) => void)[] = [];
  let dead = false; // 프로세스가 이미 끝났으면 기다리지 않고 바로 실패
  const die = () => ((dead = true), queue.splice(0).forEach((r) => r(null)));
  lines.on("line", (line) => queue.shift()?.(line));
  child.on("exit", die);
  child.on("error", die);
  return {
    decide: (obs) =>
      new Promise((resolve, reject) => {
        if (dead) return reject(new Error("에이전트 종료됨"));
        const timer = setTimeout(() => reject(new Error("에이전트 응답 시간 초과")), DECIDE_TIMEOUT_MS);
        queue.push((line) => {
          clearTimeout(timer);
          if (line === null) return reject(new Error("에이전트 종료됨"));
          try {
            resolve(JSON.parse(line));
          } catch {
            resolve(null); // 형식 오류 → 건너뜀
          }
        });
        child.stdin.write(JSON.stringify(obs) + "\n");
      }),
    close: () => {
      child.stdin.end();
      child.kill();
    },
  };
}

export type AgentOptions = {
  page: Page;
  runDir: string;
  scenario: Scenario;
  goal: string;
  /** 가짜 에이전트 동작 파일. 없으면 cmd 프로세스 */
  script?: string;
  cmd: string;
  /** 방금 실행한 단계가 성공했는지(capture 루프의 shot.status) */
  lastOk: () => boolean;
  snap: (page: Page, path: string) => Promise<void>;
};

/**
 * 단계 공급원. 첫 단계는 홈(goto /), 그 뒤는 에이전트가 고른 동작.
 * 끝나면 executed 에 실제로 내놓은 단계(scenario.json 용, 안정 셀렉터)가 쌓인다.
 */
export async function* agentSteps(o: AgentOptions, executed: Step[]): AsyncGenerator<Step> {
  const base = new URL(o.scenario.baseUrl);
  const first: Step = { id: 1, action: "goto", path: "/", caption: o.scenario.steps[0]?.caption || "서비스를 열어요" };
  executed.push(first);
  yield first;

  let decider: Decider;
  try {
    decider = o.script ? await scriptDecider(o.script) : processDecider(o.cmd);
  } catch (e) {
    console.warn(`! 에이전트 시작 실패 — 시나리오 단계로: ${e instanceof Error ? e.message : e}`);
    yield* fallback(o.scenario, executed);
    return;
  }
  const history: History[] = [];
  const repeats = new Map<string, number>();
  try {
    for (let n = 2; n <= MAX_AGENT_STEPS + 1; n++) {
      const url = new URL(o.page.url());
      if (url.origin !== base.origin) {
        // 다른 사이트로 나가면 되돌린다 — 영상은 이 서비스만 보여준다
        await o.page.goBack({ timeout: 5000 }).catch(() => {});
      }
      if (LOGIN_PATH.test(new URL(o.page.url()).pathname)) {
        console.warn("! 에이전트: 로그인 화면 — 종료");
        break;
      }
      const els = await elements(o.page);
      const shot = `agent/${n}.png`;
      await o.snap(o.page, join(o.runDir, shot)).catch(() => {});
      const obs: Observation = { goal: o.goal, step: n, url: url.pathname + url.search + url.hash, screenshot: shot, elements: els, history };
      // 관찰을 남겨 둔다 — 디버깅과 A의 오프라인 개발(저장된 관찰로 판단 로직 테스트)용
      await writeFile(join(o.runDir, `agent/${n}.json`), JSON.stringify(obs, null, 2)).catch(() => {});
      let raw: unknown;
      try {
        raw = await decider.decide(obs);
      } catch (e) {
        console.warn(`! 에이전트: ${e instanceof Error ? e.message : e}`);
        if (executed.length === 1) yield* fallback(o.scenario, executed); // 동작을 하나도 못 받았으면 시나리오로
        break;
      }
      const a = validAction(raw, new Set(els.map((e) => e.id)));
      if (!a) {
        history.push({ action: "invalid", ok: false });
        continue;
      }
      if (a.action === "done") break;
      const el = els.find((e) => e.id === a.id);
      // 같은 화면에서 같은 동작을 반복하면 막힌 것 — 멈춘다
      const key = `${obs.url}|${a.action}|${el?.name ?? ""}|${a.value ?? ""}`;
      repeats.set(key, (repeats.get(key) ?? 0) + 1);
      if (repeats.get(key)! > 1) {
        console.warn("! 에이전트: 같은 동작 반복 — 종료");
        break;
      }
      history.push({ action: a.action, id: a.id, value: a.value, caption: a.caption, ok: true });
      const caption = a.caption || el?.name || "";
      const id = executed.length + 1;
      const run: Step =
        a.action === "scroll"
          ? { id, action: "scroll", caption }
          : { id, action: a.action, selector: `[${ATTR}="${a.id}"]`, caption, ...(a.value !== undefined && { value: a.value }) };
      executed.push(el && run.selector ? { ...run, selector: stableSelector(el) } : run);
      console.log(`  → ${a.action}${el ? ` "${el.name}"` : ""}${a.value ? ` "${a.value}"` : ""}`);
      yield run;
      history[history.length - 1].ok = o.lastOk(); // capture 루프가 실행한 결과
    }
  } finally {
    decider.close();
  }
}

/** 에이전트 없이 원래 시나리오로(첫 goto / 는 이미 했으므로 그 뒤부터). */
async function* fallback(scenario: Scenario, executed: Step[]): AsyncGenerator<Step> {
  for (const s of scenario.steps) {
    if (s.action === "goto" && (s.path === "/" || s.path === "") && executed.length === 1) continue;
    const step = { ...s, id: executed.length + 1 };
    executed.push(step);
    yield step;
  }
}
