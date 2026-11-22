# capture/ — B 담당 (Playwright 캡처)

- CLI: `pnpm --filter @demoday/capture capture <scenario.json> <runDir>`. 진입점은 `src/capture.ts`.
- 입력 `Scenario`, 출력 `<runDir>/capture.json`(`Capture`)과 `<runDir>/shots/<stepId>.png`. 타입은 `@demoday/contracts`.
- viewport는 1280x720 고정이다. 클릭 좌표는 이 viewport 기준 px이고, 렌더러가 줌·커서에 그대로 쓴다.
- 클릭 좌표는 요소 bounding box의 중심으로 기록한다.
- 셀렉터를 못 찾거나 타임아웃(단계당 5초)이 나도 **멈추지 않는다**. 현재 화면을 찍고 `status: "fallback"`으로 기록한 뒤 다음 단계로 간다.
- 종료 코드: 0이면 capture.json 생성(fallback 포함), 0이 아니면 생성 실패.
- 개발 중에는 `contracts/fixtures/scenario.json`이나 직접 쓴 scenario로 실제 배포 URL에 돌려 본다. 결과는 `make validate FILES=<runDir>/capture.json`으로 확인한다.
- 로그인이 필요한 페이지는 MVP에서 제외한다. 입력값은 캡처 화면에서 마스킹 처리한다.
