// scene.json → MP4   (B 담당)
//   pnpm --filter @demoday/render render <runDir> <out.mp4> [--scale=0.5]
// 렌더마다 임시 폴더에 자기 public(글꼴·배경음악 + 그 run 의 렌더 자료만)을 만들어 --public-dir 로 넘긴다.
// 공용 public/run 을 쓰지 않으므로 동시에 여러 렌더가 돌아도 서로 자료를 덮거나 지우지 않는다(#56).
import { execFileSync } from "node:child_process";
import { cpSync, existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { stageRun } from "./use-run.mjs";

const [runDir, out, ...rest] = process.argv.slice(2);
if (!runDir || !out) {
  console.error("사용법: render <runDir> <out.mp4> [--scale=0.5]");
  process.exit(1);
}
if (!existsSync(resolve(runDir, "scene.json"))) {
  console.error(`✗ ${runDir}/scene.json 이 없습니다`);
  process.exit(1);
}
const root = fileURLToPath(new URL("..", import.meta.url));
const job = mkdtempSync(join(tmpdir(), "demoday-render-"));
try {
  const pub = join(job, "public");
  cpSync(join(root, "public/fonts"), join(pub, "fonts"), { recursive: true });
  if (existsSync(join(root, "public/bgm.mp3"))) cpSync(join(root, "public/bgm.mp3"), join(pub, "bgm.mp3"));
  const props = stageRun(runDir, join(pub, "run"));

  // 주소창에 보일 도메인(계약 밖 렌더 전용 prop). 호스트만 쓰므로 경로·쿼리의 비밀값은 들어가지 않는다.
  const scenarioPath = resolve(runDir, "scenario.json");
  if (existsSync(scenarioPath)) {
    try {
      props.domain = new URL(JSON.parse(readFileSync(scenarioPath, "utf8")).baseUrl).host;
    } catch {}
  }
  const propsPath = join(job, "props.json"); // public 밖 — 정적 파일로 노출하지 않는다
  writeFileSync(propsPath, JSON.stringify(props));
  // pnpm 대신 node로 CLI를 직접 실행한다(Windows에서 pnpm은 .cmd라 execFileSync로 못 띄운다)
  execFileSync(
    process.execPath,
    ["node_modules/@remotion/cli/remotion-cli.js", "render", "src/index.ts", "Demo", resolve(out), `--props=${propsPath}`, `--public-dir=${pub}`, ...rest],
    { cwd: root, stdio: "inherit" },
  );
} finally {
  rmSync(job, { recursive: true, force: true }); // 자기 작업 폴더만 지운다
}
