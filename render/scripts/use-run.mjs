// <runDir>의 scene.json·shots를 public/run 으로 복사 → 장면 컴포넌트는 staticFile("run/...")로 읽는다.
import { cpSync, rmSync, existsSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const runDir = process.argv[2];
if (!runDir || !existsSync(resolve(runDir, "scene.json"))) {
  console.error(`✗ ${runDir}/scene.json 이 없습니다`);
  process.exit(1);
}
const dest = fileURLToPath(new URL("../public/run", import.meta.url));
rmSync(dest, { recursive: true, force: true });
cpSync(resolve(runDir), dest, { recursive: true });
console.log(`public/run ← ${runDir}`);
