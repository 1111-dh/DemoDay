<!-- BEGIN:nextjs-agent-rules -->

## This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

# web/ — C 담당 (Next.js)

> 위 블록은 Next.js가 관리한다. 팀 규칙은 이 아래에만 쓴다.

- 실행: `make dev-web`(:3000). 백엔드는 `make dev-api`(:8000)이다.
- 화면: 입력(레포 URL, 배포 URL, 발표 시간 60/90/180초) → 시나리오 확인(장면 순서 변경·삭제, 아키텍처 장면 포함 여부) → 미리보기 → 장면 수정(순서·길이·자막만) → 다운로드.
- 타입은 `import type { SceneDoc, Scene } from "@demoday/contracts"`만 쓴다. 응답 타입을 직접 정의하지 않는다.
- 백엔드가 준비되기 전에는 `@demoday/contracts/fixtures/scene.json`을 import해서 UI를 개발한다.
- 수정 결과는 scene.json 전체를 백엔드에 보내 다시 렌더한다. 보내기 전에 장면 길이가 0보다 큰지, 자막 길이가 적당한지 클라이언트에서 확인한다.
- 시연용이므로 로딩·실패 상태 UI가 반드시 있어야 한다(렌더는 수십 초 걸림).
