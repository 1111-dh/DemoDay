"""계약 fixture가 스키마와 생성 모델 양쪽을 통과하는지 확인."""

import json
from pathlib import Path

import pytest

from app.contracts import Capture, Scenario, SceneDoc, schema_errors

FIXTURES = Path(__file__).resolve().parents[2] / "contracts" / "fixtures"
MODELS = {"scenario": Scenario, "capture": Capture, "scene": SceneDoc}


@pytest.mark.parametrize("kind", MODELS)
def test_fixture_matches_schema_and_model(kind):
    data = json.loads((FIXTURES / f"{kind}.json").read_text())
    assert schema_errors(kind, data) == []
    MODELS[kind].model_validate(data)


def test_schema_rejects_click_without_selector():
    bad = {"baseUrl": "https://x.dev", "steps": [{"id": 1, "action": "click", "caption": "c"}]}
    assert any("selector" in e for e in schema_errors("scenario", bad))


def test_schema_rejects_unknown_scene_type():
    bad = {"fps": 30, "totalSec": 10, "scenes": [{"type": "erd", "durationSec": 3}]}
    assert schema_errors("scene", bad)
