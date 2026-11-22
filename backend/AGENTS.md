# backend/ — A 담당 (FastAPI · 레포 분석 · LLM)

- 실행: `make dev-api`, 테스트: `make test`. Python 3.12, `uv add <pkg>`로 의존성 추가.
- 구조: `app/main.py`(API), `app/cli.py`(단계별 CLI, e2e·API가 같은 함수 사용), `app/contracts/`(생성 모델, 수정 금지; `__init__.py`의 헬퍼만 예외).
- 단계 함수 시그니처는 `app/cli.py`의 `analyze(repo, url, out)`, `scene(run, total_sec)`. 바꾸면 `scripts/e2e.sh`도 같이 고친다.
- 분석 범위: React Router / Next.js `pages`·`app` 라우트 + README + package.json만. 공개 레포만 지원.
- 캡처·렌더는 subprocess로 호출한다: `pnpm --filter @demoday/capture capture <scenario> <runDir>`, `pnpm --filter @demoday/render render <runDir> <out.mp4>`.

## LLM 출력 규칙
- LLM은 **scenario.json / scene.json만** 만든다. 최신 Claude 모델과 structured output(JSON schema)을 쓴다.
- 결과는 반드시 `schema_errors(kind, data)`로 검증한다. pydantic 모델은 if/then 조건(goto→path 등)을 확인하지 못한다.
- 위반이 있으면 에러 목록을 프롬프트에 붙여 재시도(최대 2회)하고, 그래도 실패하면 규칙 기반 기본값을 쓴다.
- 샘플 레포 분석 결과는 `runs/cache/`에 캐싱한다. 라이브 시연 중 LLM 지연을 막기 위해서다.
- 프롬프트는 `app/prompts/`에 파일로 둔다(코드에 긴 문자열 금지).
