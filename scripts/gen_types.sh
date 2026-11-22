#!/usr/bin/env bash
# contracts/*.schema.json → Python(pydantic) + TypeScript 타입 생성.
# 사용법: scripts/gen_types.sh            # 실제 파일에 생성
#        scripts/gen_types.sh --check    # 생성 결과가 커밋된 파일과 같은지만 확인
set -euo pipefail
export PYTHONWARNINGS="ignore::FutureWarning"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODE="${1:-write}"

if [[ "$MODE" == "--check" ]]; then
  OUT="$(mktemp -d)"
  trap 'rm -rf "$OUT"' EXIT
  PY_OUT="$OUT/py"; TS_OUT="$OUT/ts"
else
  PY_OUT="$ROOT/backend/app/contracts"; TS_OUT="$ROOT/contracts/ts"
fi
mkdir -p "$PY_OUT" "$TS_OUT"

for kind in scenario capture scene; do
  (cd "$ROOT/backend" && uv run -q datamodel-codegen \
    --input "$ROOT/contracts/$kind.schema.json" --input-file-type jsonschema \
    --output "$PY_OUT/$kind.py" --output-model-type pydantic_v2.BaseModel \
    --use-annotated --field-constraints --use-union-operator --target-python-version 3.12 \
    --disable-timestamp --custom-file-header "# 자동 생성 파일 — 수정 금지. make gen 으로 재생성.")
  (cd "$ROOT" && pnpm exec json2ts --no-additionalProperties --bannerComment \
    "// 자동 생성 파일 — 수정 금지. make gen 으로 재생성." \
    -i "contracts/$kind.schema.json" -o "$TS_OUT/$kind.ts")
done

if [[ "$MODE" == "--check" ]]; then
  fail=0
  for kind in scenario capture scene; do
    diff -q "$PY_OUT/$kind.py" "$ROOT/backend/app/contracts/$kind.py" >/dev/null 2>&1 || { echo "✗ backend/app/contracts/$kind.py 가 스키마와 다름"; fail=1; }
    diff -q "$TS_OUT/$kind.ts" "$ROOT/contracts/ts/$kind.ts" >/dev/null 2>&1 || { echo "✗ contracts/ts/$kind.ts 가 스키마와 다름"; fail=1; }
  done
  [[ $fail == 0 ]] && echo "✓ 생성 타입 최신" || { echo "→ make gen 실행 필요"; exit 1; }
fi
