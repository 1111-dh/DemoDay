# Backend(A) 설계 — 레포 분석 · 장면 생성 · API

2026-11-22 · A 담당

## 목적
레포 URL + 배포 URL → `scenario.json`(B 캡처 입력) → (캡처 후) `scene.json`(B 렌더·C 편집 입력). 이를 FastAPI로 묶어 C의 웹이 전체 흐름을 돌릴 수 있게 한다.
성공 기준: **샘플 레포 2개 + DemoDay 자체 레포**에서 사람 손 안 대고 계약을 통과하는 scenario/scene이 나온다.

- 목표: React(Vite/CRA, React Router) · Next.js(pages/app) 라우트 추출, 하위 폴더 앱(모노레포) 지원, 셀렉터는 코드에서 추출(①안), 실패해도 항상 유효한 JSON 반환.
- 비목표: 로그인 페이지, 요청 흐름·ERD, 자연어 수정, 작업 큐, 비공개 레포.
- 안티목표: LLM이 지어낸 페이지·버튼으로 시나리오를 채우는 것("가짜 데모"). 코드에 없는 경로/문구는 쓰지 않는다.

## 접근 (선택: ①)
| | 셀렉터 출처 | 비고 |
|---|---|---|
| **① 코드 추출 (선택)** | 페이지 파일 JSX의 버튼·링크 문구, input name/placeholder | 빠름, A 단독. 변수 문구는 놓침 → B fallback |
| ② 라이브 DOM 스캔 | Playwright로 각 페이지 클릭 가능 요소 수집 | 정확하지만 느리고 B와 겹침. 1차 통합 후 캡처 실패율 보고 추가 검토 |
| ③ goto만 | 없음 | 밋밋함 |

## 구성 (`backend/app/`)

### 1. `github.py` — 수집
- `https://github.com/{owner}/{repo}` 파싱 → 기본 브랜치 HEAD sha → `git/trees/{sha}?recursive=1` 1회.
- 트리에서 필요한 파일만 raw로 받는다(`raw.githubusercontent.com`, rate limit 안 셈): README, 모든 `package.json`(node_modules 제외), 라우트 후보 파일.
- `GITHUB_TOKEN` 있으면 사용. 결과는 `runs/cache/{owner}__{repo}__{sha}.json`에 캐시 (같은 커밋이면 재요청 없음).

### 2. `analyze/routes.py` — 라우트·요소 추출 (LLM 없음, 정규식 기반)
- **앱 루트 탐지**: `next` 또는 `react` 의존성이 있는 package.json 디렉터리. 여러 개면 `next` 우선 → 라우트 많은 쪽.
- Next app router: `**/app/**/page.{tsx,jsx,ts,js}` → 경로(`(group)` 제거, `[param]`은 동적으로 표시). pages router: `pages/**` (`_app`, `_document`, `api/` 제외).
- React Router: `<Route path="...">`, `createBrowserRouter([{ path: ... }])` 의 path 문자열 + element 컴포넌트명 → 파일 추적은 import 경로 1단계만.
- 페이지별 요소: `<button>…</button>`, `<Link …>…</Link>`, `<a …>…</a>`, `<input name|placeholder=…>`, `aria-label`의 **리터럴 문구만**. 페이지당 최대 15개.
- 출력: `RepoFacts { name, description(README 앞부분), stack(deps), routes: [{path, dynamic, file, elements: [...]}] }`.

### 3. `llm.py` + `prompts/` — 생성
- Claude API `claude-opus-5-5`, `output_config.effort="low"`(속도), `client.messages.parse(output_format=<pydantic>)`로 JSON 강제. LLM 출력 스키마는 계약 스키마가 아닌 단순화된 초안 모델(if/then·oneOf 없음) → 코드에서 계약 JSON으로 변환 후 `schema_errors()` 검증.
- refusal(`stop_reason == "refusal"`)·API 오류도 '실패'로 처리 → 재시도 후 규칙 기반 기본값 (서버측 fallbacks 대신).
- 공통 루프: 생성 → `schema_errors()` → 위반 시 에러를 붙여 재시도(최대 2회) → 실패 시 규칙 기반 기본값.
- 추가 검증(안티목표): scenario의 `goto.path`는 추출된 정적 라우트에만, click/type 셀렉터 문구는 추출 요소에만 있어야 한다. 위반 단계는 제거.
- **scenario**: RepoFacts → 5~7단계, 동적 라우트 제외. 기본값 = 정적 라우트 순회 goto.
- **scene**: 대부분 결정적으로 조립하고 LLM은 문구만 맡는다(일관성·속도).
  - title ← README 이름/한 줄 소개, screen ← capture.shots 순서대로(zoom·cursor = click 좌표, click 없으면 zoom 없음, fallback 샷은 짧게), architecture ← 아래 4.
  - LLM: 제목·부제, 장면별 자막(15자 내외), 장면 중요도(durationSec 비율). 렌더러가 totalSec에 맞춰 늘리고 줄인다.

### 4. 아키텍처 노드
- C의 추출 모듈이 오기 전까지 A가 임시 구현: 의존성 → 노드(프론트 프레임워크, API 서버/BaaS, DB, 외부 API 예: anthropic·openai·supabase·prisma) + 순서대로 edge. C 모듈이 오면 교체(인터페이스: `RepoFacts -> {nodes, edges}`).

### 5. `main.py` — API (C용)
렌더·캡처는 수십 초 걸리므로 BackgroundTasks + 상태 폴링. 상태는 `runs/{id}/status.json`.

| 메서드 | 경로 | 동작 |
|---|---|---|
| POST | `/api/runs` `{repo, url, totalSec}` | run 생성 + analyze(동기, 캐시 시 즉시) → `{id, scenario}` |
| PUT | `/api/runs/{id}/scenario` | 사용자가 순서 바꾼/뺀 scenario 저장(스키마 검증) |
| POST | `/api/runs/{id}/build` `{includeArchitecture}` | 백그라운드: capture → scene → render |
| GET | `/api/runs/{id}` | `{stage, status, error?, scene?, videoUrl?}` |
| PUT | `/api/runs/{id}/scene` | 수정된 scene 저장 → 백그라운드 재렌더 |
| GET | `/api/runs/{id}/files/{path}` | shots/·preview.mp4 서빙 |

CORS: localhost:3000 허용.

## 정해진 것 / 빌더 재량
- 정해진 것: ①안, Python·FastAPI·uv, 계약 스키마 그대로, CLI(`app.cli analyze/scene`)와 API가 같은 함수 사용.
- 정해진 것: API 키는 **서버 `.env`의 팀 키만** 사용(`ANTHROPIC_API_KEY`, `GITHUB_TOKEN`). 사용자 키 입력(BYOK)·GitHub OAuth·비공개 레포는 하지 않는다.
- 내 판단(수정 가능): Opus 5.5 + effort low, scene 대부분 결정적 조립, 앱 루트 `next` 우선, 페이지당 요소 15개, 재시도 2회.
- 빌더 재량: 정규식 세부, 프롬프트 문구, 캐시 키 형식.

## 순서 (시간표 맞춤)
1. 11/22 밤: github.py + routes.py + 테스트(샘플 트리 fixture) — LLM 없이 RepoFacts 확인
2. 11/23 오전: scenario 생성(LLM + 검증 + 기본값), `make e2e`의 analyze 통과, B에게 실제 scenario 전달
3. 11/23 오후: scene 조립 + API 엔드포인트, C에게 API 표 공유
4. 11/23 저녁 통합 전: 샘플 레포 분석 결과 캐시
