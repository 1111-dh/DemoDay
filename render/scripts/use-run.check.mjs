// 렌더 자료 고르기 자체 검사: node scripts/use-run.check.mjs
import assert from "node:assert/strict";
import { existsSync, mkdirSync, mkdtempSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { stageRun } from "./use-run.mjs";

const t = mkdtempSync(join(tmpdir(), "use-run-check-"));
try {
  const run = join(t, "run");
  mkdirSync(join(run, "shots"), { recursive: true });
  writeFileSync(join(t, "secret.txt"), "x");
  for (const f of ["shots/1.png", "shots/2.png", "capture.webm", "scenario.json", "scenario.plan.json", "capture.json"]) writeFileSync(join(run, f), "x");
  writeFileSync(
    join(run, "scene.json"),
    JSON.stringify({
      scenes: [
        { type: "title" },
        { type: "screen", image: "shots/2.png", video: { src: "capture.webm", startMs: 0, endMs: 1 } },
        { type: "screen", image: "../secret.txt" },
        { type: "screen", image: "shots/9.png" },
      ],
    }),
  );
  const dest = join(t, "out");
  stageRun(run, dest);
  assert.deepEqual(readdirSync(dest).sort(), ["capture.webm", "shots"]);
  assert.deepEqual(readdirSync(join(dest, "shots")), ["2.png"]);
  assert.ok(!existsSync(join(t, "secret.txt").replace(t, dest)));
  console.log("✓ use-run.check");
} finally {
  rmSync(t, { recursive: true, force: true });
}
