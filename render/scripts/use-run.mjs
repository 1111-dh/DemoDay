// run 디렉터리에서 렌더에 필요한 파일만 골라 <dest>/run 으로 복사한다 → 장면은 staticFile("run/...")로 읽는다.
// scene.json 이 가리키는 이미지·녹화만 복사한다. scenario.json(로그인 값이 들어갈 수 있음)·capture.json 등은 복사하지 않는다.
//   node scripts/use-run.mjs <runDir>   → studio 용(render/public/run)
import { cpSync, existsSync, mkdirSync, readFileSync, rmSync } from "node:fs";
import { dirname, isAbsolute, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

/** scene.json 이 쓰는 run 기준 상대경로들. run 밖을 가리키는 경로(../, 절대경로)는 뺀다. */
export function assetsOf(runDir, doc) {
  const paths = new Set();
  for (const s of doc.scenes ?? []) {
    if (typeof s.image === "string") paths.add(s.image);
    if (typeof s.video?.src === "string") paths.add(s.video.src);
  }
  return [...paths].filter((p) => {
    const rel = relative(runDir, resolve(runDir, p));
    return p && !isAbsolute(p) && rel && !rel.startsWith("..") && !isAbsolute(rel);
  });
}

/** runDir 의 렌더 자료만 runDest 로. 없는 파일은 건너뛴다(장면이 정지 화면·빈 화면으로 대신). */
export function stageRun(runDir, runDest) {
  runDir = resolve(runDir);
  const doc = JSON.parse(readFileSync(join(runDir, "scene.json"), "utf8"));
  rmSync(runDest, { recursive: true, force: true });
  mkdirSync(runDest, { recursive: true });
  for (const p of assetsOf(runDir, doc)) {
    const from = resolve(runDir, p);
    if (!existsSync(from)) continue;
    mkdirSync(dirname(join(runDest, p)), { recursive: true });
    cpSync(from, join(runDest, p));
  }
  return doc;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const runDir = process.argv[2];
  if (!runDir || !existsSync(resolve(runDir, "scene.json"))) {
    console.error(`✗ ${runDir}/scene.json 이 없습니다`);
    process.exit(1);
  }
  stageRun(runDir, fileURLToPath(new URL("../public/run", import.meta.url)));
  console.log(`public/run ← ${runDir}`);
}
