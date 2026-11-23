const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("../../capture/node_modules/playwright");

const [ui, api, out] = process.argv.slice(2);
const original = "메인 화면";
const edited = "수정한 데모 자막";
const file = (name) => path.join(out, name);

async function download(page, name) {
  const link = page.getByRole("link", { name: "MP4 다운로드" });
  const retry = page.getByRole("button", { name: "다시 시도" });
  await link.or(retry).first().waitFor({ timeout: 900000 });
  if (await retry.isVisible()) throw Error(await page.locator("main").innerText());
  const [video] = await Promise.all([page.waitForEvent("download"), link.click()]);
  await video.saveAs(file(name + ".mp4"));
  console.log("Downloaded", name);
}

async function decode(page, name, time) {
  await page.setContent("<video preload=auto></video>");
  const video = page.locator("video");
  const duration = await video.evaluate((v, data) => new Promise((resolve, reject) => {
    v.onloadeddata = () => resolve(v.duration);
    v.onerror = () => reject(Error("MP4 decoding failed"));
    v.src = "data:video/mp4;base64," + data;
  }), fs.readFileSync(file(name + ".mp4")).toString("base64"));
  // The fixed scenario has one screen after its title; sample its settled final second.
  const at = time ?? duration - 0.5;
  assert(at > 0 && at < duration);
  const frame = await video.evaluate((v, seconds) => new Promise((resolve, reject) => {
    v.onerror = () => reject(Error("Frame decoding failed"));
    v.onseeked = () => {
      const canvas = document.createElement("canvas");
      canvas.width = 1280;
      canvas.height = 720;
      canvas.getContext("2d").drawImage(v, 0, 0, canvas.width, canvas.height);
      resolve(canvas.toDataURL("image/png").split(",")[1]);
    };
    v.currentTime = seconds;
  }), at);
  fs.writeFileSync(file(name + ".png"), Buffer.from(frame, "base64"));
  return at;
}

async function run() {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  try {
    await page.goto(ui);
    await page.getByLabel("GitHub 저장소 URL").fill("https://github.com/demo/local-example");
    await page.getByLabel("배포 URL").fill(api);
    const [response] = await Promise.all([
      page.waitForResponse(r => r.request().method() === "POST" && r.url().endsWith("/api/runs")),
      page.getByRole("button", { name: "시나리오 확인 →" }).click(),
    ]);
    assert(response.ok(), await response.text());
    const { id } = await response.json();
    await page.getByRole("article").filter({ hasText: original }).waitFor();
    await page.getByRole("button", { name: "영상 만들기" }).click();
    await download(page, "original");
    const json = name => JSON.parse(fs.readFileSync(path.join(out, id, name), "utf8"));
    const capture = json("capture.json");
    assert.equal(capture.shots.length, 1);
    assert.notEqual(capture.shots[0].status, "fallback");
    assert.deepEqual(json("scene.json").scenes.map(s => s.type), ["title", "screen"]);
    await page.getByRole("button", { name: "장면 수정" }).click();
    await page.getByRole("button", { name: new RegExp(original) }).click();
    const caption = page.getByLabel("자막", { exact: true });
    assert.equal(await caption.inputValue(), original);
    await caption.fill(edited);
    await page.getByRole("button", { name: "저장하고 다시 렌더링" }).click();
    await download(page, "edited");

    const decoder = await browser.newPage();
    const time = await decode(decoder, "original");
    await decode(decoder, "edited", time);
    const font = fs.readFileSync(path.join(__dirname, "../../render/public/fonts/Pretendard-SemiBold.woff2"));
    await decoder.setContent(`<style>@font-face{font-family:reference;src:url(data:font/woff2;base64,${font.toString("base64")})}span{display:inline-block;font:30px/1.35 reference;background:black;color:white}</style><span></span>`);
    for (const [name, text] of [["original", original], ["edited", edited]]) {
      const reference = decoder.locator("span");
      await reference.evaluate((el, value) => { el.textContent = value; }, text);
      await decoder.evaluate(() => document.fonts.ready);
      await reference.screenshot({ path: file(name + "-expected.png") });
    }
    console.log("Compared frame time (seconds):", time);
  } catch (error) {
    await page.screenshot({ path: file("failure.png") }).catch(() => {});
    throw error;
  } finally {
    await browser.close();
  }
}
run().catch(error => { console.error(error); process.exitCode = 1; });
