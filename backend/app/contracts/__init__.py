"""계약 모델 + JSON Schema 검증 헬퍼.

모델(scenario.py / capture.py / scene.py)은 make gen 으로 생성된다 — 직접 수정 금지.
pydantic 모델은 스키마의 if/then 조건(goto→path 필수 등)을 표현하지 못하므로,
LLM 출력처럼 신뢰할 수 없는 JSON은 반드시 schema_errors()로 먼저 검증한다.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Literal

from jsonschema import Draft202012Validator, FormatChecker

from .capture import Capture
from .scenario import Scenario
from .scene import SceneDoc

Kind = Literal["scenario", "capture", "scene"]
SCHEMA_DIR = Path(__file__).resolve().parents[3] / "contracts"


@cache
def _validator(kind: Kind) -> Draft202012Validator:
    schema = json.loads((SCHEMA_DIR / f"{kind}.schema.json").read_text())
    return Draft202012Validator(schema, format_checker=FormatChecker())


def schema_errors(kind: Kind, data: object) -> list[str]:
    """스키마 위반 목록. 빈 리스트면 통과. LLM 재시도 프롬프트에 그대로 넣을 수 있는 형태."""
    out = []
    for err in _validator(kind).iter_errors(data):
        loc = "/".join(str(p) for p in err.absolute_path) or "(root)"
        out.append(f"{loc}: {err.message}")
    return out


__all__ = ["Capture", "Kind", "Scenario", "SceneDoc", "schema_errors"]
