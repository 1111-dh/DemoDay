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
  // 관찰 이름과 접근성 이름이 다를 때(aria-hidden 평점, aria-label) — 실제로 찾는 셀렉터로 바꿔 저장(#68)
  await page.setContent(`
    <a href="#a">Iron Man <span aria-hidden="true">7.7</span></a>
    <button aria-label="장바구니 담기">🛒</button>
    <a href="#b">오늘의 질문</a>`);
  for (const e of await elements(page)) {
    const sel = await replayableSelector(page, e);
    const id = await page.locator(sel).evaluate((el) => el.getAttribute("data-demoday-id"));
    assert.equal(id, String(e.id), `${e.name} → ${sel}`);
  }
  assert.match(await replayableSelector(page, (await elements(page)).find((e) => e.name.startsWith("Iron"))!), /^role=link\[name=\/\^\\s\*Iron\\s\*Man\/\]/);
} finally {
  await browser.close();
}
assert.equal(stableSelector({ id: 4, role: "radio", name: "", box }), '[data-demoday-id="4"]');
console.log("✓ agent.check");
