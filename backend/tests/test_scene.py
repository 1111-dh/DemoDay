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
    doc = assemble(scenario, capture["shots"], FACTS, 60, True, None)
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
    first = assemble(scenario, capture["shots"], FACTS, 60, False, None)["scenes"][1]
    assert "zoom" not in first and "cursor" not in first


def test_fallback_shot_is_short_and_unzoomed(scenario, capture):
    capture["shots"][1]["status"] = "fallback"
    shot = assemble(scenario, capture["shots"], FACTS, 60, False, None)["scenes"][2]
    assert shot["durationSec"] == 2
    assert "zoom" not in shot and "cursor" not in shot


def test_architecture_toggle(scenario, capture):
    doc = assemble(scenario, capture["shots"], FACTS, 60, False, None)
    assert [s["type"] for s in doc["scenes"]] == ["title", "screen", "screen"]


def test_copy_applied_and_weights_clamped(scenario, capture):
    copy = SceneCopy(
        title="데모데이", subtitle="", captions=["첫 화면", "검색"], weights=[5.0, 0.1]
    )
    doc = assemble(scenario, capture["shots"], FACTS, 60, False, copy)
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


def _shots(*statuses):
    return [
        {"stepId": i, "image": f"shots/{i}.png", "click": None, "status": st}
        for i, st in enumerate(statuses, start=1)
    ]


def test_keep_shots_drops_consecutive_fallbacks():
    from app.scene import keep_shots

    kept = keep_shots(_shots("ok", "fallback", "fallback", "ok", "fallback"))
    assert [s["stepId"] for s in kept] == [1, 2, 4, 5]


def test_all_fallback_keeps_first(scenario):
    from app.scene import keep_shots

    doc = assemble(scenario, keep_shots(_shots("fallback", "fallback")), FACTS, 60, False, None)
    assert [s["type"] for s in doc["scenes"]] == ["title", "screen"]
    assert schema_errors("scene", doc) == []


def _copy(**kw):
    base = {"title": "T", "subtitle": "", "captions": ["a", "b"], "weights": [1, 1]}
    return SceneCopy(**{**base, **kw})


def test_story_cards_from_copy(scenario, capture):
    copy = _copy(problem="회의록 정리는 늘 PM 몫", closing="회의만 하면 할 일이 정리됩니다")
    scenes = assemble(scenario, capture["shots"], FACTS, 60, True, copy)["scenes"]
    assert scenes[1] == {"type": "title", "durationSec": 3, "text": "회의록 정리는 늘 PM 몫"}
    assert scenes[-2] == {
        "type": "title",
        "durationSec": 3,
        "text": "회의만 하면 할 일이 정리됩니다",
    }
    assert scenes[-1]["type"] == "architecture"


def test_no_problem_card_when_empty(scenario, capture):
    scenes = assemble(scenario, capture["shots"], FACTS, 60, False, _copy())["scenes"]
    assert [s["type"] for s in scenes] == ["title", "screen", "screen"]


def test_scene_prompt_and_readme_reach_llm(tmp_path):
    run = run_dir(tmp_path)
    facts = RepoFacts(**{**FACTS.__dict__, "readme": "회의록을 손으로 옮기는 일은 PM의 몫"})
    (run / "facts.json").write_text(facts.to_json())
    (run / "prompt.txt").write_text("밝고 짧은 말투")
    llm = FakeLLM(_copy())
    build_scene(run, 60, False, llm)
    assert "사용자 요청(참고)" in llm.users[0] and "밝고 짧은 말투" in llm.users[0]
    assert "PM의 몫" in llm.users[0]


def test_check_rejects_long_cards(tmp_path):
    long = _copy(problem="가" * 41)
    llm = FakeLLM(long, long, long)
    doc = build_scene(run_dir(tmp_path), 60, False, llm)
    assert len(llm.users) == 3 and doc["scenes"][1]["type"] == "screen"
