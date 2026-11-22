# backend/ — A 담당 (FastAPI · 레포 분석 · LLM)

- 실행: `make dev-api`, 테스트: `make test`. Python 3.12, `uv add <pkg>`로 의존성 추가.
- 구조: `app/main.py`(API), `app/cli.py`(단계별 CLI, e2e·API가 같은 함수 사용), `app/contracts/`(생성 모델, 수정 금지; `__init__.py`의 헬퍼만 예외).
- 단계 함수 시그니처는 `app/cli.py`의 `analyze(repo, url, out)`, `scene(run, total_sec)`. 바꾸면 `scripts/e2e.sh`도 같이 고친다.
- 분석 범위(라우트 + UI 요소 + README + package.json/pubspec.yaml), 공개 레포만:
  - 클릭·입력까지: React Router(`lazy` import 포함) · Next.js `pages`/`app` · Vue Router · Nuxt `pages/` · SvelteKit `src/routes/`
  - Flutter web(go_router · `MaterialApp.routes`): canvas 렌더라 semantics 노드의 role 셀렉터(`role=button[name="다음"]`, `role=textbox[name="이메일"]`)를 만든다. 리터럴 문구의 `…Button` 위젯·`TextField`만. 캡처가 semantics를 켜야 클릭된다(capture/AGENTS.md)
  - 그 외(Angular·백엔드 전용 등)는 `/` 1단계 기본값
  - UI 요소는 페이지 파일에서 import(재export 묶음은 가져온 이름만)·Nuxt 자동 import 컴포넌트를 따라가며 리터럴 문구만 모은다. `…Button`·`…Link`·`…Field` 디자인 시스템 컴포넌트와 react-hook-form `register('x')`도 인식. 다른 라우트의 화면 파일은 따라가지 않는다. Flutter는 `usePathUrlStrategy`가 없으면 `/#/x` 해시 URL.
- 캡처·렌더는 subprocess로 호출한다: `pnpm --filter @demoday/capture capture <scenario> <runDir>`, `pnpm --filter @demoday/render render <runDir> <out.mp4>`.

## LLM 출력 규칙
- LLM은 **scenario.json / scene.json만** 만든다. structured output(JSON schema)을 쓴다.
- 공급자는 `.env`의 `LLM_PROVIDER`: `groq`(무료 플랜, `GROQ_API_KEY`, 기본 모델 `openai/gpt-oss-120b`, `GROQ_MODEL`로 변경) 또는 `anthropic`(`ANTHROPIC_API_KEY`). 키가 없으면 규칙 기반 기본값만 쓴다. 구현은 `app/llm.py`의 `get_llm()`.
- 결과는 반드시 `schema_errors(kind, data)`로 검증한다. pydantic 모델은 if/then 조건(goto→path 등)을 확인하지 못한다.
- 위반이 있으면 에러 목록을 프롬프트에 붙여 재시도(최대 2회)하고, 그래도 실패하면 규칙 기반 기본값을 쓴다.
- 샘플 레포 분석 결과는 `runs/cache/`에 캐싱한다. 라이브 시연 중 LLM 지연을 막기 위해서다.
- 프롬프트는 `app/prompts/`에 파일로 둔다(코드에 긴 문자열 금지).

## API (C의 web이 호출) — `make dev-api` → http://localhost:8000, CORS `localhost:3000`

| 메서드 | 경로 | 요청 | 응답 |
|---|---|---|---|
| POST | `/api/runs` | `{repo, url, totalSec?=60, auth?}` | `{id, scenario}` — 분석은 동기(캐시면 즉시). 잘못된 레포 → 400 `{detail: "메시지"}`, 잘못된 `auth` → 422 |
| PUT | `/api/runs/{id}/scenario` | Scenario JSON | `{ok: true}`. 스키마 위반 → 422 `{detail: [에러…]}` |
| POST | `/api/runs/{id}/build` | `{includeArchitecture?=true, totalSec?}` | `{id, stage: "queued"}` — 백그라운드로 capture → scene → render |
| GET | `/api/runs/{id}` | — | `{id, stage, error?, updatedAt, repo, url, totalSec, scenario?, scene?, videoUrl?}` |
| PUT | `/api/runs/{id}/scene` | SceneDoc JSON | `{id, stage: "queued"}` — 저장 후 백그라운드 재렌더. 위반 → 422 |
| GET | `/api/runs/{id}/files/{path}` | — | run 디렉터리 파일(`shots/2.png`, `preview.mp4`). 밖 경로·없는 파일 → 404 |

- `stage`: `created` → `analyzed` → (`queued` → `capturing` → `scening` → `rendering` → `done`) / 실패 시 `error` + `error` 메시지. 웹은 `done`·`error`가 될 때까지 `GET /api/runs/{id}`를 폴링한다(1~2초).
- scene 안의 이미지 경로(`shots/2.png`)는 `/api/runs/{id}/files/` 뒤에 붙여 쓴다. 없는 run id → 404.
- `auth`(캡처 전 로그인, `{steps: Step[]}`)는 run 디렉터리의 scenario.json에만 실제 값으로 저장하고 LLM·캐시에는 넣지 않는다. 응답의 scenario에서는 `value`와 경로의 쿼리가 `***`로 가려진다. 가린 채로 `PUT /scenario`하면 저장된 값을 유지하고, 바꾸려면 새 값을 보낸다. CLI·e2e는 `--auth <file>` / `make e2e … AUTH=<file>`.
