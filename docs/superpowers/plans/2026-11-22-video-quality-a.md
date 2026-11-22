# 영상 품질 C안 — A(backend) 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 자동 생성 영상이 문제 → 해결 → 정리 이야기로 흐르고, 사용자 프롬프트·테스트 계정 로그인을 받으며, 계약 합의 뒤에는 녹화 구간·강조·장 구분 카드를 scene에 채운다.

**Architecture:** 1단계(Task 1~5)는 계약 변경 없이 backend만 바꾼다 — README 본문을 facts에 넣고, 시나리오·scene LLM 입력에 사용자 프롬프트를 "참고 요청"으로 붙이고, 로그인 폼을 찾아 `scenario.auth`를 만든다. 2단계(Task 6~7)는 B가 이슈 #8에서 계약에 동의한 뒤에만 시작한다.

**Tech Stack:** Python 3.12, FastAPI, pydantic, pytest(`tests/fakes.FakeLLM`), uv. 계약은 `contracts/*.schema.json` → `make gen`.

**Spec:** `docs/superpowers/specs/2026-11-22-video-quality-design.md`

## Global Constraints

- 남의 폴더(`capture/`·`render/`)는 고치지 않는다. 예외: `web/AGENTS.md` 문서(사용자 허락, C 미착수).
- 사용자 프롬프트 최대 **500자**. 공백뿐이면 없는 것으로 본다.
- 프롬프트가 바꾸는 것: **화면 순서(시나리오), 자막 말투, 강조할 부분(scene)**. 계약·스키마 규칙과 grounding(코드에서 확인된 경로·셀렉터만)을 뒤집지 못한다 — 사용자 문장은 "참고 요청" 블록으로만 넣는다.
- 비밀번호·로그인 값은 run 디렉터리 `scenario.json`의 `auth`에만. LLM 입력·`runs/cache/`·로그·응답(가림 `***`)에 넣지 않는다.
- README 본문 상한 **2,000자**. 문제 설명이 README에 없으면 "문제" 카드를 만들지 않는다(지어내지 않기, df48d34).
- fallback이 연속되면 첫 번째만 남긴다. 거르기는 scene LLM 호출 **전**.
- 계약 파일 커밋은 B 동의 후 `DEMODAY_CONTRACT_CHANGE=1 git commit`. 순서: 스키마 → `make gen` → fixtures → `make check`.
- 매 커밋 전 `make check` 통과(훅이 실행).

## Review Focus

1. 로그인 폼이 없는 앱(소셜 로그인만, 입력칸 < 2) + `login` 입력 → 400과 "로그인 URL을 직접 넣어 주세요" 안내 (Task 5 테스트).
2. 프롬프트로 없는 경로를 요구("/admin으로 가")해도 grounding이 그 단계를 버린다 (Task 3 테스트).
3. 이전 run의 `facts.json`(readme 필드 없음)을 `RepoFacts.from_json`이 그대로 읽는다 — scene 재생성 시 (Task 2 테스트).
4. 모든 shot이 fallback → 첫 shot만 남고 scene이 계약을 통과한다 (Task 4 테스트).
5. `login`과 `auth`를 동시에 보내면 422 (어느 쪽을 쓸지 모호) (Task 5 테스트).

---

### Task 1: 규칙 문서 — MVP 범위·C 몫

**Files:**
- Modify: `AGENTS.md:55` (MVP 제외 줄)
- Modify: `web/AGENTS.md` (팀 규칙 블록 끝에 추가)

- [ ] **Step 1: 루트 `AGENTS.md` 55행을 바꾼다**

```markdown
- MVP 범위만 만든다. **제외**: 로그인 과정 녹화·입력값이 보이는 로그인 장면, 요청 흐름·ERD 장면, 자연어 수정(제작 전 프롬프트는 허용), 작업 큐·스토리지. (로그인은 scenario `auth`로 캡처 전에 처리하고, 장면으로 넣을 때는 입력칸을 가린 정지 화면만 — 낮은 우선순위.) 아이디어가 생기면 구현하지 말고 제안만 한다.
```

- [ ] **Step 2: `web/AGENTS.md` 끝에 C 몫을 추가한다** (스펙 "C — web" 절을 그대로 옮긴다)

```markdown
## 영상 품질 C안 (설계: docs/superpowers/specs/2026-11-22-video-quality-design.md)
- 입력 화면에 선택 항목 추가: **테스트 계정 아이디·비밀번호**(`type=password`) → `POST /api/runs`의 `login: {username, password}`, **"영상에 바라는 점"** 프롬프트(500자) → `prompt`. 응답에 돌아오는 로그인 값은 `***`.
- 고급 옵션: 로그인 URL 직접 입력(소셜 로그인만 있는 앱용) → `auth: {steps: [{id: 1, action: "goto", path: "<URL 경로>", caption: "로그인"}]}`. `login`과 동시에 보내지 않는다(422).
- `login`인데 로그인 폼을 못 찾으면 400 `{detail}` — 메시지를 보여주고 고급 옵션으로 안내한다.
- 미리보기·수정 화면은 scene의 `video`·`highlight`·`kicker`(계약 합의 후 생김)를 지우지 않고 그대로 보낸다.
- 아키텍처 장면이 노드 2개 미만이면 보기 흉하다 — 빼거나 서비스 흐름 표로 바꾸는 것은 C가 판단.
```

- [ ] **Step 3: `make check` → `✓ make check 통과`**

- [ ] **Step 4: Commit** `docs: MVP 범위에 로그인 장면·제작 전 프롬프트 반영, web에 C안 몫 추가`

---

### Task 2: README 본문을 facts에

**Files:**
- Modify: `backend/app/analyze/facts.py` (`RepoFacts`, `build_facts`)
- Test: `backend/tests/test_facts.py`

**Interfaces:**
- Produces: `RepoFacts.readme: str = ""` (마지막 필드, 기본값 — 기존 위치 인자 생성자 호환), `README_LIMIT = 2000`, `readme_body(readme: str) -> str`

- [ ] **Step 1: 실패 테스트**
  - `test_readme_body_strips_markup_and_limits`: 입력 `'<div align="center">\n<img src="x.png" />\n\n# 안정형\n\n[![Flutter](https://img.shields.io/x)](f)\n\n**내 상황에 맞는 자산관리**\n\n## 서비스 소개\n회의록을 손으로 옮기는 일은 PM의 몫입니다.\n' + "가" * 3000` → 결과에 `"서비스 소개"`·`"PM의 몫"` 포함, `"<img"`·`"img.shields.io"` 미포함, `len(result) <= 2000`.
  - `test_build_facts_keeps_readme`: `demo_like_snap` → `facts.readme`에 `"레포를 넣으면 데모 영상을 만든다."` 포함.
  - `test_from_json_without_readme_field` (Review Focus 3): `asdict` 결과에서 `readme` 키를 지운 JSON → `RepoFacts.from_json` 성공, `readme == ""`.

- [ ] **Step 2: `cd backend && uv run pytest tests/test_facts.py -q` → FAIL**

- [ ] **Step 3: 구현** — `readme_body`: HTML 태그 줄·이미지/배지 마크다운(`![`·`[![`)·코드 펜스 안쪽을 버리고, 빈 줄 연속을 하나로, `README_LIMIT`에서 자른다. `build_facts`가 두 반환 지점 모두 `readme=readme_body(_readme(snap))`을 넘긴다. `from_json`은 `d.setdefault("readme", "")`.

- [ ] **Step 4: `uv run pytest tests/test_facts.py -q` → PASS, `make check` 통과**

- [ ] **Step 5: Commit** `feat(backend): README 본문(2,000자)을 RepoFacts에`

---

### Task 3: 시나리오 — 사용자 프롬프트·이야기 순서·상태 의존 화면 제외

**Files:**
- Modify: `backend/app/scenario.py` (`_NOT_DEMO` 옆에 `_STATEFUL`, `_demo_page`, `_user_message`, `scenario_from_llm`, `build_scenario`, `analyze`)
- Modify: `backend/app/prompts/scenario.md`
- Modify: `backend/app/cli.py` (`analyze`에 `--prompt`), `scripts/e2e.sh`·`Makefile` e2e (`PROMPT=`)
- Test: `backend/tests/test_scenario.py`, `backend/tests/test_cli.py`

**Interfaces:**
- Consumes: `RepoFacts.readme` (Task 2)
- Produces:
  - `MAX_PROMPT = 500`, `SCENARIO_VERSION = 2`
  - `normalize_prompt(prompt: str | None) -> str | None` — strip, 500자 자르기, 빈 문자열 → `None`
  - `scenario_from_llm(facts, base_url, llm, prompt: str | None = None)`, `build_scenario(facts, base_url, llm, prompt: str | None = None)`
  - `analyze(repo_url, base_url, out_dir, llm, *, prompt: str | None = None, fetch=…, cache_dir=…)` — 프롬프트가 있으면 `out_dir / "prompt.txt"`에 쓴다(Task 4가 읽음)
  - 캐시 파일: `scenario__{owner}__{repo}__{sha}__{key}.json`, `key = sha1(f"v{SCENARIO_VERSION}|{base}|{prompt or ''}")[:8]`
  - CLI: `analyze --repo … --url … --out … [--auth f] [--prompt "…"]`; e2e: `make e2e … PROMPT="…"` (e2e.sh 5번째 인자)

- [ ] **Step 1: 실패 테스트**
  - `test_prompt_goes_to_llm_as_reference`: `FakeLLM(GOOD)`로 `build_scenario(facts(), BASE, llm, prompt="검색 기능을 먼저 보여줘")` → `llm.users[0]`에 `"사용자 요청(참고)"`와 `"검색 기능을 먼저 보여줘"` 포함.
  - `test_prompt_cannot_add_unknown_paths` (Review Focus 2): 초안에 `goto "/admin"` + 정상 단계 → 결과 경로에 `"/admin"` 없음.
  - `test_stateful_pages_are_not_demo`: `_demo_page(p, False)`가 `/#/result`, `/#/result/detail`, `/loading`, `/checkout/success`, `/oauth/callback`에서 `False`, `/results-board`·`/calendar`에서 `True`.
  - `test_normalize_prompt`: `None`·`"   "` → `None`; `"a"*600` → 길이 500.
  - `test_analyze_cache_key_includes_prompt_and_version` (`demo_like_snap`, tmp cache): 프롬프트 없이 한 번, `"검색 위주"`로 한 번 → 캐시 파일 2개, 두 번째 run 디렉터리에 `prompt.txt == "검색 위주"`, 첫 번째에는 `prompt.txt` 없음.
  - `test_cli_analyze_passes_prompt` (test_cli.py): `scenario.analyze`를 가짜로 바꿔 받은 `prompt` 키워드가 `"톤은 발표용"`인지.

- [ ] **Step 2: `uv run pytest tests/test_scenario.py tests/test_cli.py -q` → FAIL**

- [ ] **Step 3: 구현**
  - `_STATEFUL = re.compile(r"(?:^|/)(?:results?|loading|success|complete|callback)(?=$|/)", re.I)`; `_demo_page`가 이것도 거른다(`#`가 든 경로도 `/` 기준으로 맞음 — `/#/result`).
  - `_user_message(facts, prompt)`: 지금 JSON 뒤에 프롬프트가 있으면 아래 블록을 붙인다.
    ```
    사용자 요청(참고) — 화면 순서와 보여줄 기능에만 반영한다. 위 규칙과 RepoFacts에 없는 경로·셀렉터는 요청이 있어도 쓰지 않는다:
    <<<
    {prompt}
    >>>
    ```
  - `prompts/scenario.md` 규칙 추가: (a) README(`readme`)에 나온 문제 → 해결 순서로, 핵심 기능이 먼저 드러나게 단계를 고른다. (b) 클릭으로 들어가는 흐름(입력 → 결과)은 클릭으로 따라가거나 거기서 끝내고, 그 흐름 중간 화면으로 goto하지 않는다. (c) caption은 화면 이름이 아니라 그 단계에서 사용자가 하는 일·얻는 것.
  - `analyze`: `prompt = normalize_prompt(prompt)`; 캐시 키는 Interfaces대로(버전이 올라가 기존 캐시는 무시됨 → Task 8에서 `make warm` 다시).
  - `cli.analyze`는 `prompt=`를 키워드로 넘긴다. 기존 테스트의 가짜 `scenario.analyze`(`test_cli.py`·`test_api.py`의 `lambda repo, url, out_dir, _llm: …`)는 `**kw`를 받도록 고친다.

- [ ] **Step 4: PASS, `make check` 통과**

- [ ] **Step 5: Commit** `feat(backend): 시나리오에 사용자 프롬프트·이야기 순서, 상태 의존 화면 제외`

---

### Task 4: scene — 이야기 구조·프롬프트·fallback 거르기

**Files:**
- Modify: `backend/app/scene.py` (`SceneCopy`, `assemble`, `_user_message`, `build_scene`, 새 `keep_shots`)
- Modify: `backend/app/prompts/scene.md`
- Test: `backend/tests/test_scene.py`

**Interfaces:**
- Consumes: `RepoFacts.readme` (Task 2), `run_dir / "prompt.txt"` (Task 3)
- Produces:
  - `SceneCopy`: 기존 필드 + `problem: str`, `closing: str` (모르면 빈 문자열)
  - `keep_shots(shots: list[dict]) -> list[dict]` — 연속 fallback 중 첫 번째만 남김
  - 상수 `CARD_SEC = 3`, `MAX_CARD = 40`
  - 장면 순서: 오프닝 title → (problem 있으면) title `{text: problem}` → screens(남은 shot) → (closing 있으면) title `{text: closing}` → (옵션) architecture

- [ ] **Step 1: 실패 테스트**
  - `test_keep_shots_drops_consecutive_fallbacks`: 상태 `[ok, fallback, fallback, ok, fallback]` → 남은 stepId 순서 `[1, 2, 4, 5]`.
  - `test_all_fallback_keeps_first` (Review Focus 4): 모든 shot fallback → `assemble(...)` 결과 screen 장면 1개, `schema_errors("scene", doc) == []`.
  - `test_story_cards_from_copy`: `SceneCopy(..., problem="회의록 정리는 늘 PM 몫", closing="회의만 하면 할 일이 정리됩니다")` → `scenes[1] == {"type": "title", "durationSec": 3, "text": "회의록 정리는 늘 PM 몫"}`, 마지막 비아키텍처 장면이 closing 카드.
  - `test_no_problem_card_when_empty`: `problem=""` → title 장면은 오프닝(+closing)뿐.
  - `test_scene_prompt_reaches_llm`: run 디렉터리에 `prompt.txt`("밝고 짧은 말투") → `FakeLLM.users[0]`에 `"사용자 요청(참고)"`와 그 문장 포함; README 본문도 포함.
  - `test_check_rejects_long_cards`: `problem`이 41자 → 재시도(FakeLLM에 나쁜 응답 3개 → 기본값, `scenes[1]`이 screen).

- [ ] **Step 2: `uv run pytest tests/test_scene.py -q` → FAIL**

- [ ] **Step 3: 구현**
  - `build_scene`: `shots = keep_shots(capture["shots"])`로 n·LLM 입력·assemble 모두 이 목록 기준. `assemble`은 `capture` 대신 거른 shots를 받도록 시그니처를 `assemble(scenario, shots, facts, total_sec, include_architecture, copy)`로 바꾸고 기존 테스트 호출부를 맞춘다.
  - `_user_message(scenario, shots, facts, prompt)`: `readme` 추가, 프롬프트는 Task 3과 같은 블록 형식(문구만 "자막 말투와 강조할 부분에만 반영한다").
  - `check`: `problem`·`closing` 각각 0~`MAX_CARD`자.
  - `prompts/scene.md`: captions는 "그 화면에서 사용자가 얻는 것"을 말한다(화면 이름표 금지, 초안·README에 없는 기능은 여전히 금지). `problem`은 README에 나온 불편·문제를 한 문장으로, README에 없으면 빈 문자열. `closing`은 서비스 가치 한 문장(README 근거).

- [ ] **Step 4: PASS, `make check` 통과**

- [ ] **Step 5: Commit** `feat(backend): scene 이야기 구조(문제·정리 카드)·프롬프트·연속 fallback 거르기`

---

### Task 5: 테스트 계정 로그인 → scenario.auth, API에 login·prompt

**Files:**
- Create: `backend/app/login.py`
- Modify: `backend/app/main.py` (`CreateRun`, `create_run`)
- Modify: `backend/AGENTS.md` (API 표 `POST /api/runs` 요청 칸, auth 설명 줄)
- Test: `backend/tests/test_login.py`, `backend/tests/test_api.py`

**Interfaces:**
- Consumes: `RepoFacts.pages`, `scenario.analyze(..., prompt=)` (Task 3)
- Produces:
  - `login_steps(facts: RepoFacts, username: str, password: str) -> dict | None` — `{"steps": [goto, type, type, click]}` 또는 폼을 못 찾으면 `None`
  - API: `CreateRun.login: Login | None` (`Login{username: str, password: str}`), `CreateRun.prompt: str | None = Field(None, max_length=500)`

- [ ] **Step 1: 실패 테스트**
  - `test_login_steps_from_form` (test_login.py): 페이지 `/login`에 요소 `input "이메일" input[placeholder="이메일"]`, `input "비밀번호" input[placeholder="비밀번호"]`, `button "로그인" text=로그인` → `[{"id":1,"action":"goto","path":"/login","caption":"로그인"}, {"id":2,"action":"type","selector":'input[placeholder="이메일"]',"value":"u","caption":"아이디"}, {"id":3,"action":"type","selector":'input[placeholder="비밀번호"]',"value":"p","caption":"비밀번호"}, {"id":4,"action":"click","selector":"text=로그인","caption":"로그인"}]`.
  - `test_login_steps_flutter_hash_route`: `/#/signin`, `role=textbox[name="아이디"]`, `role=textbox[name="Password"]`, `role=button[name="Sign in"]` → 비밀번호 칸이 `Password` 쪽.
  - `test_login_steps_none_for_social_only` (Review Focus 1): `/#/login`에 버튼 2개(카카오·구글)만 → `None`.
  - `test_create_run_with_login` (test_api.py, 기존 가짜 analyze 패턴): 응답 `scenario.auth.steps[2].value == "***"`, run 디렉터리 scenario.json에는 실제 비밀번호.
  - `test_create_run_login_not_found_is_400`: → 400, `detail`에 `"로그인 URL"` 포함.
  - `test_create_run_login_and_auth_conflict_422` (Review Focus 5).
  - `test_create_run_prompt_too_long_422`: 501자 → 422.
  - `test_create_run_passes_prompt`: 가짜 analyze가 받은 `prompt == "검색 위주"`.

- [ ] **Step 2: `uv run pytest tests/test_login.py tests/test_api.py -q` → FAIL**

- [ ] **Step 3: 구현**
  - 로그인 페이지: 경로 세그먼트가 `log-?in|sign-?in`인 페이지 중 input 요소 2개 이상 + button 1개 이상인 첫 페이지.
  - 비밀번호 칸: `text` 또는 `selector`가 `password|비밀번호|비번|pw`(대소문자 무시)인 input, 없으면 두 번째 input. 아이디 칸: 비밀번호가 아닌 첫 input.
  - 버튼: `text`가 `로그인|log ?in|sign ?in`인 button, 없으면 마지막 button.
  - `create_run`: `login`과 `auth` 동시 → 422. `prompt`를 `scenario.analyze(..., prompt=body.prompt)`로. 분석 뒤 `login`이면 `RepoFacts.from_json(run_dir/"facts.json")`으로 `login_steps` → `None`이면 상태 error + 400 `"로그인 입력칸을 찾지 못했습니다 — 소셜 로그인만 있는 앱이면 로그인 URL을 직접 넣어 주세요(auth)"`. 결과는 기존 `body.auth`와 같은 경로로 붙인다(LLM·캐시를 거친 뒤).
  - `backend/AGENTS.md` API 표: `{repo, url, totalSec?=60, prompt?(≤500), login?:{username,password} | auth?}`; auth 설명 줄에 "`login`이면 A가 로그인 폼에서 auth 단계를 만든다. 폼을 못 찾으면 400" 추가.

- [ ] **Step 4: PASS, `make check` 통과**

- [ ] **Step 5: Commit** `feat(backend): 테스트 계정 로그인으로 auth 단계 생성, API에 login·prompt`

---

> **여기까지가 1단계.** Task 6~7은 이슈 #8에 B가 계약 동의 댓글을 단 뒤에만 시작한다. 동의가 없으면 Task 8로 건너뛴다.

### Task 6: 계약 변경 (optional 필드 6개)

**Files:**
- Modify: `contracts/capture.schema.json`, `contracts/scene.schema.json`
- Regenerate: `backend/app/contracts/{capture,scene}.py`, `contracts/ts/{capture,scene}.ts` (`make gen`, 직접 수정 금지)
- Modify: `contracts/fixtures/capture.json`, `contracts/fixtures/scene.json`

- [ ] **Step 1: 스키마 수정** — 스펙 "계약 변경" 절 그대로: `Capture.video`, `Capture.login{images}`, `Shot.clip{startMs,endMs}`(둘 다 integer ≥0, `additionalProperties: false`), `ScreenScene.video{src,startMs,endMs}`, `ScreenScene.highlight: string[]`, `TitleScene.kicker: string`. 모두 `required`에 넣지 않는다.
- [ ] **Step 2: `make gen` → 생성 파일 갱신, `make gen-check` 통과**
- [ ] **Step 3: fixtures 갱신** — capture.json에 `"video": "capture.webm"`과 shot 1~2개에 `clip`; scene.json에 `kicker` 있는 title 1개, `video`·`highlight` 있는 screen 1개. 녹화 파일 자체는 fixtures에 넣지 않는다(B가 렌더에서 없으면 `image`로 대체).
- [ ] **Step 4: `make check` → 통과** (기존 fixture가 하위 호환으로 통과하는지 포함)
- [ ] **Step 5: Commit** `DEMODAY_CONTRACT_CHANGE=1 git commit -m "feat(contracts): 녹화 구간·로그인 장면·강조·장 구분 (optional, #8)"` → PR, 본문에 이슈 #8 링크

---

### Task 7: scene 매핑 — video·highlight·kicker·로그인 장면

**Files:**
- Modify: `backend/app/scene.py`, `backend/app/prompts/scene.md`
- Test: `backend/tests/test_scene.py`

**Interfaces:**
- Consumes: Task 6 스키마, Task 4의 `assemble(scenario, shots, facts, …)`·카드 순서
- Produces: `SceneCopy.highlights: list[list[str]]`(shot 수와 같은 개수, 각 0~2개), 상수 `MAX_CLIP_SEC = 8`, `LOGIN_SEC = 2`

- [ ] **Step 1: 실패 테스트**
  - `test_clip_becomes_video`: capture에 `video: "capture.webm"`, shot `clip {startMs: 1200, endMs: 4700}` → screen에 `video == {"src": "capture.webm", "startMs": 1200, "endMs": 4700}`, `durationSec == 3.5`; clip 10초짜리 → `durationSec == 8`; `capture.video` 없으면 `video` 키 없음.
  - `test_highlight_only_words_in_caption`: highlights `[["녹음 파일", "없는말"]]`, caption `"녹음 파일로 올립니다"` → `highlight == ["녹음 파일"]`; 빈 목록이면 키 없음.
  - `test_cards_get_kicker`: problem 카드 `kicker == "문제"`, closing 카드 `kicker == "정리"`, 오프닝에는 없음.
  - `test_login_images_scene`: capture `login.images ["shots/login-1.png","shots/login-2.png"]` → 오프닝 바로 뒤 screen 2개, 각 `durationSec == 2`, caption `"테스트 계정으로 로그인"`(두 번째만).
  - 모든 결과 `schema_errors("scene", doc) == []`.

- [ ] **Step 2: FAIL 확인**
- [ ] **Step 3: 구현** — clip 길이는 `clamp((end-start)/1000, FALLBACK_SEC, MAX_CLIP_SEC)`(weight 미적용 — 움직임은 실제 길이). fallback shot에는 `video`를 넣지 않는다. `check`에 highlights 개수 = shot 수. scene.md에 "highlights: 각 caption에서 그대로 따온 핵심어 0~2개".
- [ ] **Step 4: PASS, `make check` 통과**
- [ ] **Step 5: Commit** `feat(backend): scene에 녹화 구간·강조·장 구분·로그인 장면`

---

### Task 8: 실제 레포로 확인과 시연 캐시

**Files:** 없음 (확인만). 문제가 나오면 해당 Task로 돌아가 테스트부터.

- [ ] **Step 1:** `make warm` → 두 레포 모두 `LLM 시나리오 캐시됨` (버전이 올라 새로 생성됨).
- [ ] **Step 2:** `make e2e REPO=https://github.com/kakaotechcampus-4/ktc4-kyungpook-4 URL=https://safebrother.duckdns.org SEC=45 AUTH=runs/auth-ktc4.json` → 완료, `scenario.json`에 `/#/result`·`/#/loading` goto 없음, `capture.json` fallback 0~1개, `scene.json` 첫 장면 뒤에 문제 카드(README에 문제 설명이 있을 때).
- [ ] **Step 3:** managers-manager(ktc4-kyungpook-3, `https://managers-manager.duckdns.org`)는 심사용 테스트 계정을 사용자에게 받아 API로 `login` 경로 확인(`make dev-api` 후 `POST /api/runs`) → 응답 auth가 `***`, 캡처에서 로그인 후 화면.
- [ ] **Step 4:** 프롬프트 한 번: `PROMPT="회의록 기능을 먼저, 밝은 말투로"` → 시나리오 순서·자막이 바뀌었는지 `scenario.json`·`scene.json` 비교.
- [ ] **Step 5:** 영상 프레임을 뽑아 기준 영상과 나란히 확인(브랜치 PR 본문에 결과 요약).
