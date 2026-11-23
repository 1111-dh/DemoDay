// 에이전트 동작 검사·셀렉터 생성 자체 검사: pnpm --filter @demoday/capture exec tsx src/agent.check.ts
import assert from "node:assert/strict";
import { stableSelector, validAction } from "./agent";

const ids = new Set([1, 2]);
assert.deepEqual(validAction({ action: "click", id: 1, caption: "열어요" }, ids), { action: "click", id: 1, value: undefined, caption: "열어요" });
assert.equal(validAction({ action: "click", id: 9 }, ids), null); // 화면에 없는 번호
assert.equal(validAction({ action: "type", id: 2 }, ids), null); // 입력값 없음
assert.equal(validAction({ action: "fly" }, ids), null);
assert.equal(validAction("done", ids), null);
assert.deepEqual(validAction({ action: "done" }, ids), { action: "done", caption: undefined });

const box = { x: 0, y: 0, w: 10, h: 10 };
assert.equal(stableSelector({ id: 3, role: "link", name: "학습 분야 고르기 ↓", box }), 'role=link[name="학습 분야 고르기"]');
assert.equal(stableSelector({ id: 3, role: "button", name: 'say "hi"', box }), 'role=button[name="say \\"hi\\""]');
assert.equal(stableSelector({ id: 4, role: "radio", name: "", box }), '[data-demoday-id="4"]');
console.log("✓ agent.check");
