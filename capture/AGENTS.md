# capture/ — B 담당 (Playwright 캡처)

- CLI: `pnpm --filter @demoday/capture capture <scenario.json> <runDir>`. 진입점은 `src/capture.ts`.
- 입력 `Scenario`, 출력 `<runDir>/capture.json`(`Capture`)과 `<runDir>/shots/<stepId>.png`. 타입은 `@demoday/contracts`.
- viewport는 1280x720 고정이다. 클릭 좌표는 이 viewport 기준 px이고, 렌더러가 줌·커서에 그대로 쓴다.
- 클릭 좌표는 요소 bounding box의 중심으로 기록한다.
- 셀렉터를 못 찾거나 타임아웃(단계당 5초)이 나도 **멈추지 않는다**. 현재 화면을 찍고 `status: "fallback"`으로 기록한 뒤 다음 단계로 간다. `goto` 응답이 400 이상(없는 페이지)이어도 fallback이다. 스크린샷까지 실패하면 빈 화면을 쓰고 fallback으로 둔다.
- 종료 코드: 0이면 capture.json 생성(fallback 포함), 0이 아니면 생성 실패.
- 개발 중에는 `contracts/fixtures/scenario.json`이나 직접 쓴 scenario로 실제 배포 URL에 돌려 본다. 결과는 `make validate FILES=<runDir>/capture.json`으로 확인한다.
- 로그인: scenario에 `auth.steps`가 있으면 본 `steps` 전에 **녹화하지 않는 별도 컨텍스트**에서 실행하고, 로그인 상태(쿠키·localStorage·IndexedDB·sessionStorage)만 녹화 컨텍스트로 넘긴다. 마지막 로그인 클릭 뒤에는 페이지가 넘어갈 때까지(최대 8초) 기다린다(로그인 요청이 끊기지 않게). 스크린샷·`capture.json`에 넣지 않고, 값·URL을 로그에 쓰지 않는다. 실패해도 멈추지 않고 본 단계로 간다. 예시: `contracts/fixtures/scenario.auth.json`.
- auth(로그인) 값은 영상·스크린샷·로그·`capture.json` 어디에도 남기지 않는다. 일반 단계 입력값은 가리지 않는다(LLM이 만든 데모 문구이고, 입력 장면이 움직임의 핵심이라서).
- 녹화: 본 단계를 1280x720로 녹화해 `<runDir>/capture.webm` + `capture.video`, 단계별 `clip`(녹화 시작 기준 ms)을 기록한다. 단계 뒤 결과 화면을 1.5초 더 녹화해 clip에 넣고, 앞 여유(0.3초)는 앞 clip 끝과 겹치지 않게 자른다. 녹화 안에서 로그인하지 않는다. 녹화가 실패하면(ffmpeg 없음 포함) `video`·`clip` 없이 정지 화면만 낸다.
- click·type 단계는 `clip.startMs + 0.8초`에 클릭한다(type은 그다음 입력). 렌더 ScreenScene의 커서 박자(0.1~0.8초 이동, 0.8초 클릭)와 같으므로 한쪽을 바꾸면 둘 다 바꾼다. `type`은 한 글자씩(60ms), 스크롤은 나눠서 움직인다.
- **Flutter web**(`flutter-view`·`flt-glass-pane` 요소가 있는 페이지)은 canvas라 그대로는 셀렉터가 없다. 페이지를 연 뒤 `document.querySelector('flt-semantics-placeholder')?.click()`으로 semantics를 켜면 `role=button[name="…"]`·`role=textbox[name="…"]` 셀렉터가 동작한다(A의 scenario가 이 형식을 쓴다). 해시 URL(`/#/x`)도 그대로 `baseUrl + path`로 연다.
