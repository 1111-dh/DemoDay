<!-- BEGIN:nextjs-agent-rules -->

## This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

# web/ — C 담당 (Next.js)

> 위 블록은 Next.js가 관리한다. 팀 규칙은 이 아래에만 쓴다.

- 실행: `make dev-web`(:3000). 백엔드는 `make dev-api`(:8000)이다.
- 화면: 입력(레포 URL, 배포 URL, 최대 길이 60/90/180초 — 영상은 내용만큼 짧아질 수 있다) → 시나리오 확인(장면 순서 변경·삭제, 아키텍처 장면 포함 여부) → 미리보기 → 장면 수정(순서·길이·자막만) → 다운로드.
- 타입은 `import type { SceneDoc, Scene } from "@demoday/contracts"`만 쓴다. 응답 타입을 직접 정의하지 않는다.
- 백엔드가 준비되기 전에는 `@demoday/contracts/fixtures/scene.json`을 import해서 UI를 개발한다.
- 수정 결과는 scene.json 전체를 백엔드에 보내 다시 렌더한다. 보내기 전에 장면 길이가 0보다 큰지, 자막 길이가 적당한지 클라이언트에서 확인한다.
- 시연용이므로 로딩·실패 상태 UI가 반드시 있어야 한다(렌더는 수십 초 걸림).

## 영상 품질 C안 (설계: docs/superpowers/specs/2026-11-22-video-quality-design.md)
- 입력 화면에 선택 항목 추가: **테스트 계정 아이디·비밀번호**(`type=password`) → `POST /api/runs`의 `login: {username, password}`, **"영상에 바라는 점"** 프롬프트(500자) → `prompt`. 응답에 돌아오는 로그인 값은 `***`.
- 고급 옵션: 로그인 URL 직접 입력(소셜 로그인만 있는 앱용) → `auth: {steps: [{id: 1, action: "goto", path: "<URL 경로>", caption: "로그인"}]}`. `login`과 동시에 보내지 않는다(422).
- `login`인데 로그인 폼을 못 찾으면 400 `{detail}` — 메시지를 보여주고 고급 옵션으로 안내한다.
- 미리보기·수정 화면은 scene의 `video`·`highlight`·`kicker`(계약 합의 후 생김)를 지우지 않고 그대로 보낸다.
- 아키텍처 장면이 노드 2개 미만이면 보기 흉하다 — 빼거나 서비스 흐름 표로 바꾸는 것은 C가 판단.
- `GET /api/runs/{id}`에 `warning`이 있으면(예: 사이트가 응답하지 않아 화면 없이 만든 영상) 미리보기 위에 눈에 띄게 보여준다.
