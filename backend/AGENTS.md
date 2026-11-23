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
- 공급자는 `.env`의 `LLM_PROVIDER`: **`baze`(기본 추천, 학교 BAZE 게이트웨이 — `BAZE_API_KEY`, 월 5,000크레딧 무료, 모델 `claude-haiku-5-5`(`BAZE_MODEL`), 영상 1개 ≈ 4크레딧)**, `groq`(무료 플랜, `GROQ_API_KEY`, 기본 모델 `openai/gpt-oss-120b`, `GROQ_MODEL`로 변경. 하루 한도(TPD 20만)를 다 쓰면 기다리지 않고 `GROQ_FALLBACK_MODEL`(기본 `qwen/qwen3.8-27b`, 빈 값이면 끔)로 바꾼다) 또는 `anthropic`(`ANTHROPIC_API_KEY`). 비어 있으면 키가 있는 쪽(BAZE → Groq). BAZE가 크레딧·인증·서버 오류로 내려가면 Groq 키가 있을 때 Groq로 넘어간다(`FallbackLLM`). BAZE는 strict JSON schema(`additionalProperties: false`, 모든 필드 required)를 요구한다. 키가 없으면 규칙 기반 기본값만 쓴다. 구현은 `app/llm.py`의 `get_llm()`.
- scene 자막 전에 캡처 스크린샷을 이미지 모델(BAZE면 `BAZE_VISION_MODEL` 기본 `claude-haiku-5-5` → 예비 Groq `GROQ_VISION_MODEL` 기본 `qwen/qwen3.8-27b`, 빈 값이면 끔)로 읽어 화면별 `seen`(실제로 보이는 내용)을 scene LLM에 넣는다(`app/vision.py`). Groq가 이미지 1장을 약 2,000토큰으로 잡아서(분당 7,000) 4장씩 2x2로 붙여 요청 1번에 보낸다. 실패하면 `seen` 없이 예전처럼 자막을 쓴다.
- 결과는 반드시 `schema_errors(kind, data)`로 검증한다. pydantic 모델은 if/then 조건(goto→path 등)을 확인하지 못한다.
- 위반이 있으면 에러 목록을 프롬프트에 붙여 재시도(최대 2회)하고, 그래도 실패하면 규칙 기반 기본값을 쓴다.
- 샘플 레포 분석 결과는 `runs/cache/`에 캐싱한다. 라이브 시연 중 LLM 지연을 막기 위해서다. 시연 레포는 `backend/samples.json`(`{repo, url, prompt?}`)에 두고 시연 전에 `make warm`으로 채운다. `prompt`가 있으면 그 프롬프트의 시나리오를 캐시하므로, 시연 때 웹에 **같은 문장**을 넣어야 즉시 나온다.
- GitHub에 닿지 못하면(연결 실패·rate limit·5xx) 그 레포의 가장 최근 스냅샷 캐시를 대신 쓴다(`GitHubUnavailable`). 404는 캐시가 있어도 에러.
- 프롬프트는 `app/prompts/`에 파일로 둔다(코드에 긴 문자열 금지).

## API (C의 web이 호출) — `make dev-api` → http://localhost:8000, CORS `localhost:3000`

| 메서드 | 경로 | 요청 | 응답 |
|---|---|---|---|
| POST | `/api/runs` | `{repo, url, totalSec?=60, prompt?(≤500자), login?: {username, password} \| auth?}` | `{id, scenario}` — 분석은 동기(캐시면 즉시). 잘못된 레포 → 400 `{detail: "메시지"}`, 잘못된 `auth`·`login`과 `auth` 동시·긴 `prompt` → 422, `login`인데 로그인 폼 없음 → 400 |
| PUT | `/api/runs/{id}/scenario` | Scenario JSON | `{ok: true}`. 스키마 위반 → 422 `{detail: [에러…]}` |
| POST | `/api/runs/{id}/build` | `{totalSec?}` (`includeArchitecture`는 범위 제외 — 기본 false, 보내지 않는다) | `{id, stage: "queued"}` — 백그라운드로 capture → scene → render |
| GET | `/api/runs/{id}` | — | `{id, stage, error?, warning?, updatedAt, repo, url, totalSec, scenario?, scene?, videoUrl?}` |
| PUT | `/api/runs/{id}/scene` | SceneDoc JSON | `{id, stage: "queued"}` — 저장 후 백그라운드 재렌더. 위반 → 422 |
| GET | `/api/runs/{id}/files/{path}` | — | run 디렉터리 파일(`shots/2.png`, `preview.mp4`). 밖 경로·없는 파일 → 404 |

- `stage`: `created` → `analyzed` → (`queued` → `capturing` → `scening` → `rendering` → `done`) / 실패 시 `error` + `error` 메시지. 웹은 `done`·`error`가 될 때까지 `GET /api/runs/{id}`를 폴링한다(1~2초).
- 영상 길이: `totalSec`은 **최대 길이**다. scene 은 장면마다 내용만큼 길이를 잡고(카드는 글자 수로 2~4초, 화면은 녹화 구간 길이) `scene.totalSec = min(요청, 내용 합)`으로 쓴다. 짧은 내용을 요청 길이까지 늘리지 않는다(루즈해진다).
- 캡처가 통째로 실패하면(사이트 응답 없음 등) 빈 capture.json으로 계속해 화면 없이(제목·문제·해결·정리 카드) 영상을 만들고 `stage: "done"` + `warning` 메시지를 남긴다. 다음 build 때 지워진다.
- scene 안의 이미지 경로(`shots/2.png`)는 `/api/runs/{id}/files/` 뒤에 붙여 쓴다. 없는 run id → 404.
- `auth`(캡처 전 로그인, `{steps: Step[]}`)는 run 디렉터리의 scenario.json에만 실제 값으로 저장하고 LLM·캐시에는 넣지 않는다. 응답의 scenario에서는 `value`와 경로의 쿼리가 `***`로 가려진다. 가린 채로 `PUT /scenario`하면 저장된 값을 유지하고, 바꾸려면 새 값을 보낸다. CLI·e2e는 `--auth <file>` / `make e2e … AUTH=<file>`.
- `login`(테스트 계정)이면 A가 분석 결과의 로그인 페이지(경로 `login`/`signin`, 입력칸 2개 이상 + 버튼)에서 auth 단계(goto → type 아이디 → type 비밀번호 → click)를 만든다(`app/login.py`). 저장·가림 규칙은 `auth`와 같다. 소셜 로그인만 있어 폼을 못 찾으면 400 — 웹은 로그인 URL을 `auth`로 받는 고급 옵션을 안내한다.
- `prompt`(영상에 바라는 점)는 시나리오 LLM에는 화면 순서, scene LLM에는 자막 말투·강조로만 "사용자 요청(참고)" 블록(`app/prompts/reference.md`)에 넣는다. 규칙·grounding을 못 뒤집는다. 단 "빼주세요·제외·말고" 문장에 적힌 경로(`/reports`)는 LLM이 무시해도 코드가 페이지 목록에서 지운다(`excluded_paths`, 그 아래 경로 포함). run 디렉터리 `prompt.txt`에 남고 시나리오 캐시 키에 들어간다. CLI·e2e는 `--prompt` / `make e2e … PROMPT="…"`.
