// 에이전트 동작 검사·셀렉터 생성 자체 검사: pnpm --filter @demoday/capture exec tsx src/agent.check.ts
import assert from "node:assert/strict";
import { chromium } from "playwright";
import { elements, replayableSelector, stableSelector, validAction } from "./agent";

const ids = new Set([1, 2]);
assert.deepEqual(validAction({ action: "click", id: 1, caption: "열어요" }, ids), { action: "click", id: 1, value: undefined, caption: "열어요" });
assert.equal(validAction({ action: "click", id: 9 }, ids), null); // 화면에 없는 번호
assert.equal(validAction({ action: "type", id: 2 }, ids), null); // 입력값 없음
assert.equal(validAction({ action: "fly" }, ids), null);
assert.equal(validAction("done", ids), null);
assert.deepEqual(validAction({ action: "done" }, ids), { action: "done", caption: undefined });

const box = { x: 0, y: 0, w: 10, h: 10 };
// 저장한 셀렉터가 실제 페이지에서 다시 찾아지는지 — 접근성 이름과 관찰 이름의 공백 차이, 숨은 같은 이름 링크
const browser = await chromium.launch();
try {
  const page = await browser.newPage();
  await page.setContent(`
    <nav style="display:none"><a href="/q">CS 질문·해설</a></nav>
    <a href="/q"><strong>CS 질문·해설 →</strong><span>개념을 이어 읽는 질문 지도</span></a>
    <a href="#x">학습 분야 고르기 <span aria-hidden="true">↓</span></a>
    <button>say "hi" (1/2)</button>`);
  const cases: [string, string][] = [
    ["link", "CS 질문·해설 → 개념을 이어 읽는 질문 지도"], // innerText 는 줄바꿈 → 공백, 접근성 이름은 "→개념"
    ["link", "학습 분야 고르기 ↓"], // 장식 기호가 접근성 이름에 없음
    ["button", 'say "hi" (1/2)'], // 따옴표·정규식 특수문자
  ];
  for (const [role, name] of cases) {
    const sel = stableSelector({ id: 1, role, name, box });
    assert.equal(await page.locator(sel).count(), 1, sel);
  }
  // 실제 추출 → 기록 → 다시 찾기: label 이 붙은 검색칸은 접근성 이름이 placeholder 가 아니다
  await page.setContent(`
    <label for="question-search">질문 검색</label>
    <input id="question-search" type="search" placeholder="질문이나 기술 키워드로 찾기">
    <input name="q2" placeholder="두 번째">`);
  const els = await elements(page);
  assert.deepEqual(els.map((e) => [e.role, e.name]), [["searchbox", "질문 검색"], ["textbox", "두 번째"]]);
  for (const e of els) {
    const sel = stableSelector(e);
    assert.equal(await page.locator(sel).count(), 1, sel);
  }
  // 관찰 이름과 접근성 이름이 다를 때(aria-hidden 평점, aria-label, 안쪽 SVG 의 aria-label) — 실제로 찾는 셀렉터로 바꿔 저장(#68, #70 리뷰)
  // 재생은 새 페이지에서 한다: 원본 DOM 을 다시 연 뒤(data-demoday-id 없음) 같은 요소를 찾아야 한다
  const html = `
    <a href="#a">Iron Man <span aria-hidden="true">7.7</span></a>
    <button aria-label="장바구니 담기">🛒</button>
    <button><svg aria-label="Save" role="img" width="16" height="16"><rect width="16" height="16"/></svg></button>
    <a href="#b">오늘의 질문</a>`;
  await page.setContent(html);
  const recorded = [];
  for (const e of await elements(page)) recorded.push({ e, sel: await replayableSelector(page, e) });
  assert.ok(recorded.find((r) => r.e.name.startsWith("Iron"))!.sel.startsWith(String.raw`role=link[name=/^\s*Iron\s*Man/]`));
  await page.setContent(html);
  for (const { e, sel } of recorded) {
    assert.ok(!sel.includes("data-demoday-id"), `임시 번호가 저장됨: ${sel}`);
    const box = await page.locator(sel).boundingBox({ timeout: 1000 });
    assert.ok(box && Math.abs(box.x - e.box.x) < 2 && Math.abs(box.y - e.box.y) < 2, `${e.name || e.role} → ${sel}`);
  }
} finally {
  await browser.close();
}
assert.equal(stableSelector({ id: 4, role: "radio", name: "", box }), '[data-demoday-id="4"]');
console.log("✓ agent.check");
