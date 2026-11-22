/**
 * scenario.json → <runDir>/capture.json + <runDir>/shots/*.png   (B 담당)
 *
 *   pnpm --filter @demoday/capture capture <scenario.json> <runDir>
 *
 * 규칙
 * - 스크린샷 경로는 runDir 기준 상대경로로 기록 (예: "shots/2.png")
 * - 셀렉터를 못 찾은 단계도 건너뛰지 말고 현재 화면을 찍어 status: "fallback" 으로 기록
 * - 종료 코드: 0 = capture.json 생성됨(fallback 포함), 1 = 생성 실패
 */
import { readFile } from "node:fs/promises";
import type { Capture, Scenario } from "@demoday/contracts";

async function main(scenarioPath: string, runDir: string): Promise<Capture> {
  const scenario: Scenario = JSON.parse(await readFile(scenarioPath, "utf8"));
  // TODO(B): Playwright로 scenario.steps 실행 → 스크린샷·클릭 좌표 기록 → capture.json 쓰기
  void scenario;
  void runDir;
  throw new Error("capture 단계 미구현 (B)");
}

const [scenarioPath, runDir] = process.argv.slice(2);
if (!scenarioPath || !runDir) {
  console.error("사용법: capture <scenario.json> <runDir>");
  process.exit(1);
}
main(scenarioPath, runDir).catch((e) => {
  console.error(`✗ ${e instanceof Error ? e.message : e}`);
  process.exit(2);
});
