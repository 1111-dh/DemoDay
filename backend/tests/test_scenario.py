import json

from app.analyze.elements import Element
from app.analyze.facts import PageFacts, RepoFacts
from app.contracts import schema_errors
from app.scenario import (
    ScenarioDraft,
    StepDraft,
    analyze,
    build_scenario,
    default_scenario,
    ground,
)
from tests.conftest import make_snap
from tests.fakes import FakeLLM

BASE = "https://demo.vercel.app"


def facts(pages=None) -> RepoFacts:
    if pages is None:
        pages = [
            PageFacts("/", False, "app/page.tsx", [Element("link", "검색", "text=검색")]),
            PageFacts(
                "/search",
                False,
                "app/search/page.tsx",
                [Element("input", "q", "input[name=q]"), Element("button", "찾기", "text=찾기")],
            ),
            PageFacts("/about", False, "app/about/page.tsx", []),
            PageFacts("/posts/[id]", True, "app/posts/[id]/page.tsx", []),
        ]
    return RepoFacts("Demo", "데모 서비스", ["next"], "", "next-app", pages)


def step(action, path="", selector="", value="", caption="c"):
    return StepDraft(action=action, path=path, selector=selector, value=value, caption=caption)


GOOD = ScenarioDraft(
    steps=[
        step("goto", path="/", caption="메인"),
        step("click", selector="text=검색", caption="검색 이동"),
        step("goto", path="/search", caption="검색 페이지"),
        step("type", selector="input[name=q]", value="React", caption="입력"),
        step("click", selector="text=찾기", caption="검색 실행"),
    ]
)


def test_ground_keeps_grounded_steps():
    out = ground(GOOD, facts())
    assert [s["action"] for s in out] == ["goto", "click", "goto", "type", "click"]
    assert [s["id"] for s in out] == [1, 2, 3, 4, 5]
    assert out[3] == {
        "id": 4,
        "action": "type",
        "selector": "input[name=q]",
        "value": "React",
        "caption": "입력",
    }


def test_ground_drops_invented():
    draft = ScenarioDraft(
        steps=[
            step("goto", path="/"),
            step("goto", path="/pricing"),  # 없는 경로
            step("goto", path="/posts/[id]"),  # 동적 경로
            step("click", selector="text=로그인"),  # 없는 문구
            step("click", selector="text=찾기"),  # 다른 페이지(/search)의 요소
            step("type", selector="text=검색", value=""),  # 빈 값
        ]
    )
    assert [(s["action"], s.get("path")) for s in ground(draft, facts())] == [("goto", "/")]


def test_ground_inserts_root_goto():
    draft = ScenarioDraft(steps=[step("click", selector="text=검색")])
    out = ground(draft, facts())
    assert [(s["action"], s.get("path"), s.get("selector")) for s in out] == [
        ("goto", "/", None),
        ("click", None, "text=검색"),
    ]


def test_ground_truncates_to_seven():
    draft = ScenarioDraft(steps=[step("goto", path="/")] * 10)
    assert len(ground(draft, facts())) == 7


def test_default_scenario_valid():
    many = [PageFacts(f"/p{i}", False, f"f{i}", []) for i in range(8)]
    sc = default_scenario(facts([PageFacts("/", False, "f", []), *many]), BASE + "/")
    assert sc["baseUrl"] == BASE
    assert len(sc["steps"]) == 6
    assert sc["steps"][0] == {"id": 1, "action": "goto", "path": "/", "caption": "메인 화면"}
    assert schema_errors("scenario", sc) == []


def test_default_skips_dynamic_routes():
    sc = default_scenario(facts(), BASE)
    assert [s["path"] for s in sc["steps"]] == ["/", "/search", "/about"]


def test_default_when_no_routes():
    sc = default_scenario(facts([]), BASE)
    assert sc["steps"] == [{"id": 1, "action": "goto", "path": "/", "caption": "메인 화면"}]
    assert schema_errors("scenario", sc) == []


def test_build_scenario_falls_back_when_llm_none():
    assert build_scenario(facts(), BASE, None) == default_scenario(facts(), BASE)


def test_build_scenario_uses_llm_when_grounded():
    sc = build_scenario(facts(), BASE, FakeLLM(GOOD))
    assert len(sc["steps"]) == 5
    assert schema_errors("scenario", sc) == []


def test_build_scenario_retries_then_defaults():
    bad = ScenarioDraft(steps=[step("goto", path="/nope")])
    llm = FakeLLM(bad, bad, bad)
    assert build_scenario(facts(), BASE, llm) == default_scenario(facts(), BASE)
    assert "/nope" in llm.users[1]


def test_small_app_does_not_need_five_steps():
    tiny = facts([PageFacts("/", False, "f", [Element("button", "시작", "text=시작")])])
    draft = ScenarioDraft(steps=[step("goto", path="/"), step("click", selector="text=시작")])
    llm = FakeLLM(draft)
    assert len(build_scenario(tiny, BASE, llm)["steps"]) == 2
    assert len(llm.users) == 1


def test_analyze_writes_files_and_uses_cache(tmp_path, demo_like_snap):
    draft = ScenarioDraft(
        steps=[
            step("goto", path="/"),
            step("click", selector="text=시작하기"),
            step("goto", path="/search"),
            step("type", selector="input[name=q]", value="React"),
            step("click", selector="text=검색"),
        ]
    )
    llm = FakeLLM(draft)
    out = tmp_path / "run1"
    sc = analyze(
        "https://github.com/o/r",
        BASE,
        out,
        llm,
        fetch=lambda url: demo_like_snap,
        cache_dir=tmp_path / "cache",
    )
    assert json.loads((out / "scenario.json").read_text()) == sc
    assert json.loads((out / "facts.json").read_text())["app_dir"] == "web"
    assert len(sc["steps"]) == 5

    llm2 = FakeLLM()
    sc2 = analyze(
        "https://github.com/o/r",
        BASE,
        tmp_path / "run2",
        llm2,
        fetch=lambda url: demo_like_snap,
        cache_dir=tmp_path / "cache",
    )
    assert sc2 == sc
    assert llm2.users == []


def test_analyze_does_not_cache_default(tmp_path):
    snap = make_snap({"README.md": "# X"})
    analyze(
        "https://github.com/o/r",
        BASE,
        tmp_path / "a",
        None,
        fetch=lambda url: snap,
        cache_dir=tmp_path / "cache",
    )
    assert not list((tmp_path / "cache").glob("scenario__*"))
