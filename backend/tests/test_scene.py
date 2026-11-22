import json
import shutil

import pytest

from app import paths
from app.analyze.facts import RepoFacts
from app.contracts import schema_errors
from app.scene import SceneCopy, assemble, build_scene
from tests.fakes import FakeLLM

FIXTURES = paths.ROOT / "contracts" / "fixtures"
FACTS = RepoFacts("DemoDay", "레포로 만드는 데모 영상", ["next", "react"], "web", "next-app", [])


@pytest.fixture
def scenario():
    return json.loads((FIXTURES / "scenario.json").read_text())


@pytest.fixture
def capture():
    return json.loads((FIXTURES / "capture.json").read_text())


def test_assemble_without_copy_matches_contract(scenario, capture):
    doc = assemble(scenario, capture, FACTS, 60, True, None)
    assert schema_errors("scene", doc) == []
    assert (doc["fps"], doc["totalSec"]) == (30, 60)
    assert [s["type"] for s in doc["scenes"]] == ["title", "screen", "screen", "architecture"]
    title = doc["scenes"][0]
    assert (title["text"], title["subtitle"], title["durationSec"]) == (
        "DemoDay",
        "레포로 만드는 데모 영상",
        3,
    )
    clicked = doc["scenes"][2]
    assert clicked["image"] == "shots/2.png"
    assert clicked["caption"] == "검색 기능"  # scenario step 2 caption
    assert clicked["zoom"] == {"x": 640, "y": 120, "scale": 1.6}
    assert clicked["cursor"] == {"x": 640, "y": 120}
    assert clicked["durationSec"] == 4
    assert doc["scenes"][3]["nodes"] == ["Next.js"]


def test_screen_without_click_has_no_zoom(scenario, capture):
    first = assemble(scenario, capture, FACTS, 60, False, None)["scenes"][1]
    assert "zoom" not in first and "cursor" not in first


def test_fallback_shot_is_short_and_unzoomed(scenario, capture):
    capture["shots"][1]["status"] = "fallback"
    shot = assemble(scenario, capture, FACTS, 60, False, None)["scenes"][2]
    assert shot["durationSec"] == 2
    assert "zoom" not in shot and "cursor" not in shot


def test_architecture_toggle(scenario, capture):
    doc = assemble(scenario, capture, FACTS, 60, False, None)
    assert [s["type"] for s in doc["scenes"]] == ["title", "screen", "screen"]


def test_copy_applied_and_weights_clamped(scenario, capture):
    copy = SceneCopy(
        title="데모데이", subtitle="", captions=["첫 화면", "검색"], weights=[5.0, 0.1]
    )
    doc = assemble(scenario, capture, FACTS, 60, False, copy)
    title, s1, s2 = doc["scenes"]
    assert title["text"] == "데모데이" and "subtitle" not in title
    assert (s1["caption"], s1["durationSec"]) == ("첫 화면", 8)
    assert (s2["caption"], s2["durationSec"]) == ("검색", 2)
    assert schema_errors("scene", doc) == []


def run_dir(tmp_path):
    run = tmp_path / "run"
    shutil.copytree(FIXTURES, run)
    (run / "facts.json").write_text(FACTS.to_json())
    return run


def test_build_scene_writes_file_with_llm_copy(tmp_path):
    run = run_dir(tmp_path)
    copy = SceneCopy(title="T", subtitle="S", captions=["a", "b"], weights=[1, 1])
    doc = build_scene(run, 90, True, FakeLLM(copy))
    assert json.loads((run / "scene.json").read_text()) == doc
    assert doc["scenes"][0]["text"] == "T"
    assert doc["totalSec"] == 90


def test_build_scene_rejects_bad_copy_then_defaults(tmp_path):
    run = run_dir(tmp_path)
    wrong_len = SceneCopy(title="T", subtitle="", captions=["a"], weights=[1])
    llm = FakeLLM(wrong_len, wrong_len, wrong_len)
    doc = build_scene(run, 60, False, llm)
    assert doc["scenes"][0]["text"] == "DemoDay"
    assert len(llm.users) == 3


def test_build_scene_without_llm(tmp_path):
    doc = build_scene(run_dir(tmp_path), 60, True, None)
    assert schema_errors("scene", doc) == []
