"""계약 JSON 검증기.

사용법:
  python scripts/validate_contracts.py                 # contracts/fixtures 전체 검증
  python scripts/validate_contracts.py runs/x/scene.json ...   # 파일명으로 스키마 자동 선택

파일명(basename)에 scenario / capture / scene 이 들어가면 해당 스키마로 검증한다.
그 외 JSON은 건너뛴다. 실패하면 exit 1.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parent.parent
CONTRACTS = ROOT / "contracts"
KINDS = ("scenario", "capture", "scene")  # scene 은 scenario 보다 뒤에 매칭해야 함


def kind_of(path: Path) -> str | None:
    name = path.name.lower()
    if not name.endswith(".json") or name.endswith(".schema.json"):
        return None
    for kind in KINDS:
        if kind in name:
            return kind
    return None


def validate(path: Path) -> list[str]:
    kind = kind_of(path)
    if kind is None:
        return []
    schema = json.loads((CONTRACTS / f"{kind}.schema.json").read_text())
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        return [f"{path}: JSON 파싱 실패 — {e}"]
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = []
    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path)):
        loc = "/".join(str(p) for p in err.absolute_path) or "(root)"
        errors.append(f"{path} [{kind}] {loc}: {err.message}")
    if kind in ("capture", "scene"):
        errors += check_images(path, data)
    return errors


def check_images(path: Path, data: dict) -> list[str]:
    """image 경로는 JSON 파일이 있는 디렉터리(run 디렉터리) 기준으로 존재해야 한다."""
    items = data.get("shots") or data.get("scenes") or []
    missing = []
    for item in items:
        image = item.get("image") if isinstance(item, dict) else None
        if image and not (path.parent / image).exists():
            missing.append(f"{path}: 이미지 없음 — {image} (run 디렉터리 기준 상대경로여야 함)")
    return missing


def main(argv: list[str]) -> int:
    targets = [Path(a) for a in argv] or sorted((CONTRACTS / "fixtures").glob("*.json"))
    errors: list[str] = []
    checked = 0
    for t in targets:
        if kind_of(t):
            checked += 1
            errors += validate(t.resolve())
    for e in errors:
        print(e, file=sys.stderr)
    if errors:
        print(f"✗ 계약 위반 {len(errors)}건", file=sys.stderr)
        return 1
    print(f"✓ 계약 검증 통과 ({checked}개 파일)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
