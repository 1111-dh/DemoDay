# DemoDay — 사람·Claude Code·Codex 모두 이 명령만 쓴다.
SHELL := /bin/bash
PY := uv run --project backend
.DEFAULT_GOAL := help

help: ## 명령 목록
	@grep -E '^[a-z0-9-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-14s %s\n", $$1, $$2}'

setup: ## 최초 1회: 의존성 설치 + 브라우저 + git 훅
	corepack enable pnpm || true
	pnpm install
	cd backend && uv sync
	pnpm --filter @demoday/capture exec playwright install chromium
	git config core.hooksPath .githooks
	@test -f .env || cp .env.example .env
	@echo "✓ setup 완료 — .env 에 키를 채우세요"

gen: ## 스키마 → Python/TS 타입 재생성 (계약 변경 후)
	scripts/gen_types.sh

# ---------- 검증 ----------
validate: ## 계약 fixture 검증 (FILES=a.json b.json 로 특정 파일)
	@$(PY) python scripts/validate_contracts.py $(FILES)

gen-check:
	@scripts/gen_types.sh --check

lint: ## ruff + eslint
	@cd backend && uv run ruff check . && uv run ruff format --check .
	@pnpm --filter @demoday/web exec eslint --quiet .

typecheck: ## tsc (capture, render, web)
	@pnpm -r --if-present --silent run typecheck

test: ## pytest
	@cd backend && uv run pytest -q

check: validate gen-check lint typecheck test ## 전부. "작업 완료" 전에 반드시 통과
	@echo "✓ make check 통과"

# ---------- 실행 ----------
dev-api: ## FastAPI :8000
	cd backend && uv run uvicorn app.main:app --reload --port 8000

dev-web: ## Next.js :3000
	pnpm --filter @demoday/web dev

studio: ## Remotion Studio (fixture scene.json 으로 장면 미리보기)
	pnpm --filter @demoday/render studio

# PROMPT 는 따옴표·$·백틱이 들어가도 깨지지 않게 셸 인자 대신 환경변수로 넘긴다
e2e: export DEMODAY_PROMPT := $(value PROMPT)
e2e: ## 전체 파이프라인. REPO=<github url> URL=<배포 url> [SEC=60] [AUTH=<auth.json>] [PROMPT='…']
	scripts/e2e.sh "$(REPO)" "$(URL)" "$(or $(SEC),60)" "$(AUTH)"

warm: ## 시연 레포 분석 캐시 채우기 (backend/samples.json, FILE=로 변경, AGENT=1 이면 에이전트 동작을 캐시). 시연 전에 한 번
	cd backend && uv run python -m app.cli warm $(if $(FILE),--file $(abspath $(FILE))) $(if $(AGENT),--agent)

e2e-render: ## fixture scene.json → runs/fixture/preview.mp4 (렌더만)
	rm -rf runs/fixture && mkdir -p runs && cp -R contracts/fixtures runs/fixture
	pnpm --filter @demoday/render render $(CURDIR)/runs/fixture $(CURDIR)/runs/fixture/preview.mp4 --scale=0.5

.PHONY: help setup gen validate gen-check lint typecheck test check dev-api dev-web studio e2e warm e2e-render

.PHONY: e2e-web-video
e2e-web-video: ## 로컬 웹 UI로 제작·다운로드·자막 재렌더 검증
	@$(PY) python scripts/video-regression/run.py
