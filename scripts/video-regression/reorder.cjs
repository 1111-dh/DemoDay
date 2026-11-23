const assert = require("node:assert/strict");
const { chromium } = require("../../capture/node_modules/playwright");

const url = process.argv[2] || "http://127.0.0.1:3000";
const scenario = {
  baseUrl: "https://example.com",
  steps: ["검색", "선택", "상세", "저장"].map((caption, index) => ({
    id: index + 1,
    action: "goto",
    caption,
    path: index === 0 ? "/" : "/page-" + index,
  })),
};

async function verify(browser, touch) {
  const context = await browser.newContext({
    hasTouch: touch,
    isMobile: touch,
    viewport: { width: touch ? 390 : 1200, height: 860 },
  });
  try {
    const page = await context.newPage();
    const calls = [];
    let saved;
    await page.route("**/api/runs**", async (route) => {
      const request = route.request();
      const endpoint = new URL(request.url()).pathname;
      calls.push(request.method() + " " + endpoint);
      if (endpoint.endsWith("/scenario")) saved = request.postDataJSON();
      await route.fulfill({
        json: { id: "sort-test", scenario, stage: "queued" },
      });
    });
    await page.goto(url);
    await page.getByRole("button", { name: /nuxt\/movies 예시/i }).click();
    await page.getByRole("button", { name: "시나리오 확인 →" }).click();
    const handles = page.locator(".step-handle");
    const order = () => handles.locator("b").allTextContents();
    const initial = await handles.first().waitFor().then(order);
    assert.equal(initial.length, 4);
    assert.equal(await handles.first().locator("small").count(), 0);
    assert.equal(await handles.nth(1).locator("small").innerText(), "/page-1");
    await handles.first().scrollIntoViewIfNeeded();
    const first = await handles.first().boundingBox();
    const last = await handles.last().boundingBox();
    const point = (box) => ({ x: box.x + 24, y: box.y + box.height / 2 });
    const a = point(first),
      b = point(last);
    if (touch) {
      const session = await context.newCDPSession(page);
      const dispatch = (type, points) =>
        session.send("Input.dispatchTouchEvent", { type, touchPoints: points });
      await dispatch("touchStart", [a]);
      await dispatch("touchEnd", []);
      assert.deepEqual(await order(), initial);
      await dispatch("touchStart", [a]);
      await page.locator("article[data-dragging]").waitFor();
      await dispatch("touchMove", [b]);
      await dispatch("touchCancel", []);
      await page.locator("article[data-dragging]").waitFor({ state: "detached" });
      assert.deepEqual(await order(), initial);
      await handles.first().scrollIntoViewIfNeeded();
      await dispatch("touchStart", [point(await handles.first().boundingBox())]);
      await page.locator("article[data-dragging]").waitFor();
      await dispatch("touchMove", [point(await handles.last().boundingBox())]);
      await dispatch("touchEnd", []);
    } else {
      await page.mouse.move(a.x, a.y);
      await page.mouse.down();
      await page.locator("article[data-dragging]").waitFor();
      await page.mouse.move(b.x, b.y, { steps: 12 });
      await page.mouse.up();
    }
    await page
      .getByRole("button", { name: "4번째 장면 순서 변경: 검색" })
      .waitFor();
    assert.deepEqual(await order(), [
      "1. 선택",
      "2. 상세",
      "3. 저장",
      "4. 검색",
    ]);
    if (!touch) {
      await handles.last().click({ trial: true });
      await handles.last().focus();
      await page.keyboard.press("ArrowUp");
      await page
        .getByRole("button", { name: "3번째 장면 순서 변경: 검색" })
        .waitFor();
    }
    // A new gesture starts after dnd-kit releases its post-drop click guard.
    await page.waitForTimeout(250);
    const buildButton = page.getByRole("button", { name: "영상 만들기" });
    if (touch) await buildButton.tap();
    else await buildButton.click();
    await page.locator("progress").waitFor();
    assert.deepEqual(
      saved.steps.map((s) => s.id),
      touch ? [2, 3, 4, 1] : [2, 3, 1, 4],
    );
    for (const step of saved.steps)
      assert.deepEqual(
        step,
        scenario.steps.find((s) => s.id === step.id),
      );
    assert(
      calls.indexOf("PUT /api/runs/sort-test/scenario") <
        calls.indexOf("POST /api/runs/sort-test/build"),
    );
    console.log(
      touch
        ? "Touch hold, cancel and save passed"
        : "Mouse hold, keyboard and save passed",
    );
  } finally {
    await context.close();
  }
}

(async () => {
  const browser = await chromium.launch();
  try {
    await verify(browser, false);
    await verify(browser, true);
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
