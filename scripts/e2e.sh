#!/usr/bin/env bash
# 레포 + URL → runs/<id>/ 에 scenario → capture → scene → preview.mp4
# 단계마다 계약 검증. 실패한 단계와 원인을 출력하고 멈춘다.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="${1:-}"; URL="${2:-}"; SEC="${3:-60}"; AUTH="${4:-}"; PROMPT="${5:-}"
[[ -z "$REPO" || -z "$URL" ]] && { echo "사용법: make e2e REPO=<github url> URL=<배포 url> [SEC=60] [AUTH=<auth.json>] [PROMPT=\"영상에 바라는 점\"]"; exit 1; }
AUTH_ABS=""; [[ -n "$AUTH" ]] && AUTH_ABS="$(cd "$(dirname "$AUTH")" && pwd)/$(basename "$AUTH")"

RUN="$ROOT/runs/$(date +%m%d-%H%M%S)"
mkdir -p "$RUN"
echo "▶ run: $RUN"

stage() {  # stage <이름> <검증할 파일|-> <명령...>
  local name="$1" out="$2"; shift 2
  echo "── [$name]"
  if ! "$@"; then echo "✗ [$name] 실패 — 위 로그 확인"; exit 1; fi
  if [[ "$out" != "-" ]]; then
    uv run --project "$ROOT/backend" python "$ROOT/scripts/validate_contracts.py" "$out" \
      || { echo "✗ [$name] 출력이 계약 위반"; exit 1; }
  fi
  echo "✓ [$name]"
}

stage analyze "$RUN/scenario.json" \
  bash -c 'cd "$1/backend" && uv run python -m app.cli analyze --repo "$2" --url "$3" --out "$4/scenario.json" ${5:+--auth "$5"} ${6:+--prompt "$6"}' _ "$ROOT" "$REPO" "$URL" "$RUN" "$AUTH_ABS" "$PROMPT"
stage capture "$RUN/capture.json" \
  pnpm --silent --filter @demoday/capture capture "$RUN/scenario.json" "$RUN"
stage scene "$RUN/scene.json" \
  bash -c "cd '$ROOT/backend' && uv run python -m app.cli scene --run '$RUN' --total-sec '$SEC'"
stage render - \
  pnpm --silent --filter @demoday/render render "$RUN" "$RUN/preview.mp4" --scale=0.5

echo "✓ 완료: $RUN/preview.mp4"
