#!/usr/bin/env bash
# PreToolUse(Edit|Write|MultiEdit): 계약·생성 파일 수정 차단.
# 팀 합의 후 계약을 바꿀 때만: DEMODAY_CONTRACT_CHANGE=1 claude
f="$(jq -r '.tool_input.file_path // empty')"
[[ -z "$f" ]] && exit 0
rel="${f#"$CLAUDE_PROJECT_DIR"/}"
case "$rel" in
  backend/app/contracts/scenario.py|backend/app/contracts/capture.py|backend/app/contracts/scene.py|contracts/ts/scenario.ts|contracts/ts/capture.ts|contracts/ts/scene.ts)
    echo "✋ $rel 은 자동 생성 파일입니다. 스키마를 고친 뒤 'make gen'으로 재생성하세요." >&2; exit 2 ;;
  contracts/*.schema.json|contracts/fixtures/*)
    if [[ "${DEMODAY_CONTRACT_CHANGE:-}" != "1" ]]; then
      echo "✋ $rel 은 팀 계약입니다. 수정하지 말고, 무엇을 왜 바꿀지 사용자에게 제안하세요. (합의 후에는 DEMODAY_CONTRACT_CHANGE=1 로 Claude를 다시 실행)" >&2; exit 2
    fi ;;
esac
exit 0
