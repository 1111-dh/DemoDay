#!/usr/bin/env bash
# PostToolUse(Edit|Write|MultiEdit): 방금 고친 파일만 빠르게 검사. 실패하면 exit 2 → Claude가 바로 고친다.
f="$(jq -r '.tool_input.file_path // empty')"
[[ -z "$f" || ! -f "$f" ]] && exit 0
cd "$CLAUDE_PROJECT_DIR" || exit 0
rel="${f#"$CLAUDE_PROJECT_DIR"/}"
fail() { { echo "✗ $rel 검사 실패:"; echo "$1" | head -30; } >&2; exit 2; }

case "$rel" in
  backend/*.py)
    (cd backend && uv run -q ruff format "${rel#backend/}" >/dev/null 2>&1)
    out="$(cd backend && uv run -q ruff check "${rel#backend/}" 2>&1)" || fail "$out" ;;
  capture/*.ts|capture/*.tsx|render/*.ts|render/*.tsx|web/*.ts|web/*.tsx)
    pkg="${rel%%/*}"
    out="$(cd "$pkg" && pnpm exec tsc --noEmit --pretty false 2>&1)" || fail "$out" ;;
  *.json)
    case "$(basename "$rel")" in *scenario*|*capture*|*scene*)
      out="$(uv run -q --project backend python scripts/validate_contracts.py "$f" 2>&1)" || fail "$out" ;;
    esac ;;
esac
exit 0
