import json
import shutil

import pytest

from app import paths
from app.analyze.facts import RepoFacts
from app.contracts import schema_errors
from app.scene import SceneCopy, assemble, build_scene
from tests.fakes import FakeLLM

FIXTURES = paths.ROOT / "contracts" / "fixtures"
STACK = ["next", "react", "@supabase/supabase-js"]
FACTS = RepoFacts("DemoDay", "레포로 만드는 데모 영상", STACK, "web", "next-app", [])


@pytest.fixture
def scenario():
    return json.loads((FIXTURES / "scenario.json").read_text())


@pytest.fixture
def capture():
    return json.loads((FIXTURES / "capture.json").read_text())


def test_assemble_without_copy_matches_contract(scenario, capture):
    doc = assemble(scenario, capture["shots"], FACTS, 60, True, None)
    assert schema_errors("scene", doc) == []
    assert doc["fps"] == 30
    assert doc["totalSec"] == sum(x["durationSec"] for x in doc["scenes"]) < 60  # 내용 길이
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
    assert doc["scenes"][3]["nodes"] == ["Next.js", "Supabase"]


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


def test_single_node_architecture_is_dropped(
    scenario, capture
):  # nuxt/movies: 'Nuxt' 한 단어만 4초
    from app.analyze.facts import RepoFacts

    lone = RepoFacts("n", "s", ["nuxt"], "", "nuxt", [])
    doc = assemble(scenario, capture["shots"], lone, 60, True, None)
    assert "architecture" not in [s["type"] for s in doc["scenes"]]


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
    assert doc["totalSec"] == sum(x["durationSec"] for x in doc["scenes"]) <= 90


def test_wrong_caption_count_keeps_copy_and_pads_from_drafts(tmp_path):
    # 화면 6개에 자막 4개만 오는 일이 잦다 — 문제·해결·정리까지 버리지 않고 모자란 자막만 초안으로
    run = run_dir(tmp_path)
    short = SceneCopy(title="T", subtitle="", captions=["a"], weights=[1], problem="정리가 늦어요")
    llm = FakeLLM(short)
    doc = build_scene(run, 60, False, llm)
    assert len(llm.users) == 1 and doc["scenes"][0]["text"] == "T"
    assert doc["scenes"][1]["text"] == "정리가 늦어요"
    screens = [s for s in doc["scenes"] if s["type"] == "screen"]
    assert [s.get("caption") for s in screens] == ["a", "검색 기능"]  # 2번째는 시나리오 초안
    assert "화면 2개" in llm.users[0]


def test_build_scene_without_llm(tmp_path):
    doc = build_scene(run_dir(tmp_path), 60, True, None)
    assert schema_errors("scene", doc) == []


def _shots(*statuses):
    return [
        {"stepId": i, "image": f"shots/{i}.png", "click": None, "status": st}
        for i, st in enumerate(statuses, start=1)
    ]


def test_keep_shots_drops_failed_steps():  # 실패한 동작을 성공처럼 자막으로 말하지 않게
    from app.scene import keep_shots

    kept = keep_shots(_shots("ok", "fallback", "fallback", "ok", "fallback"))
    assert [s["stepId"] for s in kept] == [1, 4]


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
    from app.scene import _read_sec

    card = {"type": "title"}
    problem = "회의록 정리는 늘 PM 몫"
    assert scenes[1] == {
        **card,
        "durationSec": _read_sec(problem),
        "text": problem,
        "kicker": "문제",
    }
    closing = "회의만 하면 할 일이 정리됩니다"
    assert scenes[-2] == {
        **card,
        "durationSec": _read_sec(closing),
        "text": closing,
        "kicker": "정리",
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


def test_cards_stay_short_for_title_style():  # 최종 리뷰 #3 — kicker 전까지 제목 스타일로 그려짐
    from app.scene import MAX_CARD

    assert MAX_CARD <= 28


def _clip_shots(*clips):
    return [
        {"stepId": 1, "image": "shots/1.png", "click": None, "status": "ok", "clip": c}
        for c in clips
    ]


def test_clip_becomes_video(scenario):
    shots = _clip_shots({"startMs": 1200, "endMs": 4700}, {"startMs": 4700, "endMs": 14700})
    doc = assemble(scenario, shots, FACTS, 60, False, None, video="capture.webm")
    s1, s2 = doc["scenes"][1:]
    assert s1["video"] == {"src": "capture.webm", "startMs": 1200, "endMs": 4700}
    assert s1["durationSec"] == 3.5 and s2["durationSec"] == 8  # MAX_CLIP_SEC
    assert schema_errors("scene", doc) == []
    no_video = assemble(scenario, shots, FACTS, 60, False, None)
    assert all("video" not in s for s in no_video["scenes"])


def test_fallback_shot_gets_no_video(scenario):
    shots = _clip_shots({"startMs": 0, "endMs": 3000})
    shots[0]["status"] = "fallback"
    screen = assemble(scenario, shots, FACTS, 60, False, None, video="capture.webm")["scenes"][1]
    assert "video" not in screen and screen["durationSec"] == 2


def test_highlight_only_words_in_caption(scenario, capture):
    copy = _copy(
        captions=["녹음 파일로 올립니다", "검색"], highlights=[["녹음 파일", "없는말"], []]
    )
    s1, s2 = assemble(scenario, capture["shots"], FACTS, 60, False, copy)["scenes"][1:]
    assert s1["highlight"] == ["녹음 파일"]
    assert "highlight" not in s2


def test_cards_get_kicker(scenario, capture):
    copy = _copy(problem="회의록 정리는 늘 PM 몫", closing="회의만 하면 정리됩니다")
    scenes = assemble(scenario, capture["shots"], FACTS, 60, False, copy)["scenes"]
    assert "kicker" not in scenes[0]
    assert scenes[1]["kicker"] == "문제" and scenes[-1]["kicker"] == "정리"
    assert schema_errors("scene", {"fps": 30, "totalSec": 60, "scenes": scenes}) == []


def test_login_images_scene(scenario, capture):
    login = ["shots/login-1.png", "shots/login-2.png"]
    scenes = assemble(scenario, capture["shots"], FACTS, 60, False, None, login_images=login)[
        "scenes"
    ]
    a, b = scenes[1], scenes[2]
    assert (a["image"], a["durationSec"], "caption" in a) == ("shots/login-1.png", 2, False)
    assert (b["image"], b["caption"]) == ("shots/login-2.png", "테스트 계정으로 로그인")


def test_build_scene_reads_video_and_login(tmp_path):
    run = run_dir(tmp_path)
    cap = json.loads((run / "capture.video.json").read_text())
    (run / "capture.json").write_text(json.dumps(cap))
    doc = build_scene(run, 60, False, None)
    screens = [s for s in doc["scenes"] if s["type"] == "screen"]
    assert "caption" not in screens[0] and screens[1]["caption"] == "테스트 계정으로 로그인"
    assert any(s.get("video", {}).get("src") == "capture.webm" for s in screens)
    assert schema_errors("scene", doc) == []


def test_wrong_highlights_count_keeps_copy(tmp_path):  # 강조만 버리고 자막·카드는 살린다
    llm = FakeLLM(_copy(highlights=[["a"]]))  # shot 2개인데 1개
    doc = build_scene(run_dir(tmp_path), 60, False, llm)
    assert len(llm.users) == 1 and doc["scenes"][0]["text"] == "T"
    assert all("highlight" not in s for s in doc["scenes"])


@pytest.mark.parametrize(
    "clip", [{"startMs": 5000, "endMs": 3000}, {"startMs": 3000, "endMs": 3000}]
)
def test_bad_clip_falls_back_to_image(scenario, clip):  # Task 6~7 리뷰 #1
    screen = assemble(scenario, _clip_shots(clip), FACTS, 60, False, None, video="capture.webm")[
        "scenes"
    ][1]
    assert "video" not in screen and screen["durationSec"] == 4


def test_build_scene_tolerates_null_login(tmp_path):  # Task 6~7 리뷰 #7 — 실패해도 영상은 나와야
    run = run_dir(tmp_path)
    cap = json.loads((run / "capture.json").read_text())
    (run / "capture.json").write_text(json.dumps({**cap, "login": None}))
    assert build_scene(run, 60, False, None)["scenes"][1]["type"] == "screen"


def test_login_scenes_come_after_problem_card(scenario, capture):
    copy = _copy(problem="회의록 정리는 늘 PM 몫")
    login = ["shots/login-1.png", "shots/login-2.png"]
    scenes = assemble(scenario, capture["shots"], FACTS, 60, False, copy, login_images=login)[
        "scenes"
    ]
    kinds = [(s["type"], s.get("kicker") or s.get("image")) for s in scenes]
    assert kinds[:4] == [
        ("title", None),
        ("title", "문제"),
        ("screen", "shots/login-1.png"),
        ("screen", "shots/login-2.png"),
    ]


def test_highlight_dedupes_and_prefers_longer_word(scenario, capture):
    words = [["녹음", "녹음 파일", "녹음 파일"], []]
    copy = _copy(captions=["녹음 파일로 올립니다", "검색"], highlights=words)
    screen = assemble(scenario, capture["shots"], FACTS, 60, False, copy)["scenes"][1]
    assert screen["highlight"] == ["녹음 파일"]


def test_total_is_content_length_not_stretched(
    scenario, capture
):  # 60초를 채우려 늘리면 루즈해진다
    copy = _copy(problem="회의록 정리는 늘 PM 몫", closing="회의만 하면 정리돼요")
    doc = assemble(scenario, capture["shots"], FACTS, 60, True, copy)
    total = sum(s["durationSec"] for s in doc["scenes"])
    assert doc["totalSec"] == round(total, 2) < 60  # 내용 길이 그대로 (렌더가 늘리지 않음)


def test_total_capped_by_requested_length(scenario, capture):
    doc = assemble(scenario, capture["shots"], FACTS, 10, True, None)
    assert doc["totalSec"] == 10  # 내용이 더 길면 요청 길이에 맞춰 줄인다


def test_card_length_follows_text_length(scenario, capture):
    short = assemble(scenario, capture["shots"], FACTS, 60, False, _copy(problem="느려요"))
    long = assemble(
        scenario,
        capture["shots"],
        FACTS,
        60,
        False,
        _copy(problem="임대인이 빈 상가에 맞는 업종을 판단하기 어려워요"),
    )
    assert short["scenes"][1]["durationSec"] < long["scenes"][1]["durationSec"] <= 4


def _pt(icon, text):
    from app.scene import PointDraft

    return PointDraft(icon=icon, text=text)


def test_problem_and_solution_points_scenes(scenario, capture):  # 소개 그래픽 (#34)
    copy = _copy(
        problem="회의 정리는 늘 PM 몫이에요",
        problem_points=[
            _pt("clock", "회의록 옮기는 데 30분 걸려요"),
            _pt("alert", "담당자가 흐려져요"),
        ],
        solution="회의만 하면 할 일이 정리돼요",
        solution_points=[
            _pt("chat", "회의를 듣고 할 일을 찾아요"),
            _pt("check", "확실한 일은 바로 등록해요"),
            _pt("bolt", "애매한 것만 물어요"),
        ],
    )
    scenes = assemble(scenario, capture["shots"], FACTS, 60, False, copy)["scenes"]
    problem, solution = scenes[1], scenes[2]
    assert problem == {
        "type": "points",
        "durationSec": 3.5,  # 1.5초 + 항목당 1초
        "kicker": "문제",
        "heading": "회의 정리는 늘 PM 몫이에요",
        "items": [
            {"icon": "clock", "text": "회의록 옮기는 데 30분 걸려요"},
            {"icon": "alert", "text": "담당자가 흐려져요"},
        ],
    }
    assert (solution["kicker"], solution["durationSec"], len(solution["items"])) == ("해결", 4.5, 3)
    assert scenes[3]["type"] == "screen"
    assert schema_errors("scene", {"fps": 30, "totalSec": 60, "scenes": scenes}) == []


def test_single_point_falls_back_to_title_card(scenario, capture):
    copy = _copy(problem="정리가 늘 늦어요", problem_points=[_pt("clock", "하나뿐")])
    scenes = assemble(scenario, capture["shots"], FACTS, 60, False, copy)["scenes"]
    assert scenes[1]["type"] == "title" and scenes[1]["kicker"] == "문제"
    assert scenes[2]["type"] == "screen"  # solution 없으면 해결 장면도 없음


def test_check_rejects_long_point_text(tmp_path):
    bad = _copy(solution="한 줄", solution_points=[_pt("check", "가" * 25), _pt("bolt", "짧아요")])
    llm = FakeLLM(bad, bad, bad)
    doc = build_scene(run_dir(tmp_path), 60, False, llm)
    assert len(llm.users) == 3 and all(s["type"] != "points" for s in doc["scenes"])


class FakeDescriber:
    def __init__(self, answers: dict[bytes, str | None]):
        self.answers = answers
        self.calls: list[bytes] = []

    def describe_many(self, images: list[bytes]) -> list[str | None]:
        self.calls.extend(images)
        return [self.answers.get(i) for i in images]


def test_scene_llm_gets_what_each_screen_shows(tmp_path):  # 자막이 추측이 아니라 실제 화면 근거로
    run = run_dir(tmp_path)
    one, two = (run / "shots/1.png").read_bytes(), (run / "shots/2.png").read_bytes()
    describer = FakeDescriber({one: "검색창과 '찾기' 버튼", two: None})
    llm = FakeLLM(SceneCopy(title="T", subtitle="", captions=["a", "b"], weights=[1, 1]))
    build_scene(run, 60, False, llm, describer=describer)
    screens = json.loads(llm.users[0].split("\n\n화면")[0])["screens"]
    assert screens[0]["seen"] == "검색창과 '찾기' 버튼"
    # 화면을 보고 읽었으면 추측 초안은 빼서 끌려가지 않게
    assert "caption" not in screens[0]["step"]
    assert "seen" not in screens[1]  # 못 읽으면 넣지 않는다
    assert screens[1]["step"]["caption"]  # 그때는 초안이 유일한 근거
    assert describer.calls == [one, two]


def test_describer_unused_without_llm_or_image(tmp_path):
    run = run_dir(tmp_path)
    describer = FakeDescriber({})
    build_scene(run, 60, False, None, describer=describer)
    assert describer.calls == []  # 자막 LLM 이 없으면 읽을 이유가 없다
    (run / "shots/2.png").unlink()
    llm = FakeLLM(SceneCopy(title="T", subtitle="", captions=["a", "b"], weights=[1, 1]))
    build_scene(run, 60, False, llm, describer=describer)
    assert len(describer.calls) == 1  # 없는 파일은 건너뛴다


def test_build_scene_saves_what_screens_show(tmp_path):  # 자막 점검용 — 이미지 모델이 읽은 내용
    run = run_dir(tmp_path)
    one = (run / "shots/1.png").read_bytes()
    llm = FakeLLM(SceneCopy(title="T", subtitle="", captions=["a", "b"], weights=[1, 1]))
    build_scene(run, 60, False, llm, describer=FakeDescriber({one: "검색창"}))
    assert json.loads((run / "seen.json").read_text()) == ["검색창", None]
