// scene.json → MP4   (B 담당)
//   pnpm --filter @demoday/render render <runDir> <out.mp4> [--scale=0.5]
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const [runDir, out, ...rest] = process.argv.slice(2);
if (!runDir || !out) {
  console.error("사용법: render <runDir> <out.mp4> [--scale=0.5]");
  process.exit(1);
}
const root = fileURLToPath(new URL("..", import.meta.url));
execFileSync("node", ["scripts/use-run.mjs", resolve(runDir)], { cwd: root, stdio: "inherit" });
execFileSync(
  "pnpm",
  ["exec", "remotion", "render", "src/index.ts", "Demo", resolve(out), `--props=${resolve(runDir, "scene.json")}`, ...rest],
  { cwd: root, stdio: "inherit" },
);
