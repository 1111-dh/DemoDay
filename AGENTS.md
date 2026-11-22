# DemoDay — 에이전트 공통 규칙

> Claude Code와 Codex가 모두 이 파일을 읽는다. 규칙은 여기에만 쓰고, `CLAUDE.md`는 이 파일을 불러오기만 한다.
> 기획 전체: `docs/기획안.md`. 마감: **11/24(화) 11시 제출 목표**.

GitHub 레포 + 배포 URL → 실제 화면 캡처 기반 발표용 데모 영상(MP4).
**LLM은 영상을 만들지 않는다. 장면 JSON만 만들고, 렌더러가 그대로 그린다.**

## 파이프라인과 담당

```
repo+url ─[A analyze]→ scenario.json ─[B capture]→ capture.json + shots/
                                                       │
                       scene.json ←──[A scene]─────────┘ (+ C 아키텍처 노드)
                           │
                           ├─[B render]→ preview.mp4
                           └─[C web]→ 미리보기·순서/길이/자막 수정 → 다시 render
```

| 폴더 | 담당 | 내용 |
|---|---|---|
| `contracts/` | **전원 합의** | JSON Schema 3개 + fixtures + 생성된 TS 타입 |
| `backend/` | A | FastAPI, GitHub 분석, LLM(scenario·scene 생성), 파이프라인 연결 |
| `capture/` | B | Playwright 캡처 CLI |
| `render/` | B (아키텍처 장면은 C) | Remotion 장면 컴포넌트, 렌더 CLI |
| `web/` | C | Next.js 입력·시나리오 확인·미리보기·수정 UI |

남의 폴더를 고쳐야 하면 고치지 말고 사용자에게 먼저 말한다.

## 계약 (가장 중요)

- `contracts/*.schema.json`이 유일한 기준이다. 필드 이름과 구조는 스키마를 따르고, **추측해서 만들지 않는다**.
- 스키마·fixtures는 **팀 합의 없이 수정 금지**. 바꿔야 하면 멈추고 사용자에게 무엇을 왜 바꿀지 제안한다.
- 합의 후 변경 순서: 스키마 수정 → `make gen` → fixtures 갱신 → `make check`.
- 생성 파일은 직접 수정 금지: `backend/app/contracts/{scenario,capture,scene}.py`, `contracts/ts/{scenario,capture,scene}.ts`.
- 타입은 생성된 것만 import한다. Python `from app.contracts import SceneDoc, schema_errors`, TS `import type { SceneDoc } from "@demoday/contracts"`.
- 다른 사람 단계가 아직 없으면 `contracts/fixtures/*.json`으로 개발한다.
- 이미지 경로는 항상 **run 디렉터리 기준 상대경로**(`shots/2.png`). 실행 산출물은 `runs/<id>/`(git 제외).

## 명령 (사람·에이전트 공통)

| 명령 | 용도 |
|---|---|
| `make check` | 계약 검증 + 생성 타입 최신 여부 + lint + typecheck + test. **"완료"라고 말하기 전에 반드시 통과** |
| `make validate FILES=runs/x/scene.json` | 특정 JSON 계약 검증 |
| `make gen` | 스키마 → 타입 재생성 |
| `make e2e REPO=… URL=…` | 전체 파이프라인. 어느 단계에서 깨지는지 출력 |
| `make e2e-render` | fixture로 렌더만 (B·C 장면 작업 확인용) |
| `make studio` / `dev-api` / `dev-web` | 개발 서버 |

패키지 매니저: Python은 `uv`(pip 금지), JS는 `pnpm`(npm·yarn 금지). 의존성은 해당 폴더에서 `uv add` / `pnpm add`.

## 작업 규칙

- MVP 범위만 만든다. **제외**: 로그인 페이지, 요청 흐름·ERD 장면, 자연어 수정, 작업 큐·스토리지. 아이디어가 생기면 구현하지 말고 제안만 한다.
- 레포 분석이 지원하는 프레임워크는 `backend/AGENTS.md`의 "분석 범위"가 기준이다. 지원을 늘리면 그 줄을 먼저 고치고 팀에 알린다.
- 실패해도 영상은 나와야 한다. 캡처 실패는 `status: "fallback"` 스크린샷, LLM 출력 스키마 위반은 에러를 붙여 재시도(최대 2회) 후 규칙 기반 기본값을 쓴다.
- 비밀값은 `.env`에만 둔다(`.env.example` 참고). 코드나 로그에 키를 남기지 않는다.
- 커밋은 사용자가 요청할 때만. 브랜치는 `a/…`, `b/…`, `c/…`. `main`에 force push 금지.
- 커밋 시 `.githooks/pre-commit`이 `make check`를 실행하고 계약 파일 변경을 막는다. 훅을 우회(`--no-verify`)하지 않는다.
