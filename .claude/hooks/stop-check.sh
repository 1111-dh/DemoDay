#!/usr/bin/env bash
# Stop: 코드가 바뀌었으면 make check 통과 전에는 "완료" 불가. 변경이 없으면(질문·답변만) 건너뛴다.
input="$(cat)"
[[ "$(echo "$input" | jq -r '.stop_hook_active')" == "true" ]] && exit 0
cd "$CLAUDE_PROJECT_DIR" || exit 0
state="$( (git status --porcelain; git diff) 2>/dev/null | shasum | cut -c1-16)"
stamp=".claude/.last-check"
[[ -f "$stamp" && "$(cat "$stamp")" == "$state" ]] && exit 0
if out="$(make check 2>&1)"; then
  echo "$state" > "$stamp"; exit 0
fi
{ echo "make check 실패 — 고친 뒤 마무리하세요:"; echo "$out" | tail -30; } >&2
exit 2
