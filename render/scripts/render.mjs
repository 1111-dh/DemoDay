// scene.json → MP4   (B 담당)
//   pnpm --filter @demoday/render render <runDir> <out.mp4> [--scale=0.5]
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const [runDir, out, ...rest] = process.argv.slice(2);
if (!runDir || !out) {
  console.error("사용법: render <runDir> <out.mp4> [--scale=0.5]");
  process.exit(1);
}
const root = fileURLToPath(new URL("..", import.meta.url));
execFileSync("node", ["scripts/use-run.mjs", resolve(runDir)], { cwd: root, stdio: "inherit" });

// 주소창에 보일 도메인(계약 밖 렌더 전용 prop). 호스트만 쓰므로 경로·쿼리의 비밀값은 들어가지 않는다.
const props = JSON.parse(readFileSync(resolve(runDir, "scene.json"), "utf8"));
const scenarioPath = resolve(runDir, "scenario.json");
if (existsSync(scenarioPath)) {
  try {
    props.domain = new URL(JSON.parse(readFileSync(scenarioPath, "utf8")).baseUrl).host;
  } catch {}
}
const propsPath = join(root, "public/run/.props.json");
writeFileSync(propsPath, JSON.stringify(props));
// pnpm 대신 node로 CLI를 직접 실행한다(Windows에서 pnpm은 .cmd라 execFileSync로 못 띄운다)
execFileSync(
  process.execPath,
  ["node_modules/@remotion/cli/remotion-cli.js", "render", "src/index.ts", "Demo", resolve(out), `--props=${propsPath}`, ...rest],
  { cwd: root, stdio: "inherit" },
);
