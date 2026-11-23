import io
import json

import httpx
from PIL import Image

from app import agent
from app.analyze.facts import RepoFacts


def _run(tmp_path, n=1):
    (tmp_path / "agent").mkdir(exist_ok=True)
    buf = io.BytesIO()
    Image.new("RGB", (1280, 720), "white").save(buf, "PNG")
    (tmp_path / f"agent/{n}.png").write_bytes(buf.getvalue())
    return tmp_path


OBS = {
    "goal": "질문을 검색해 본다",
    "step": 1,
    "url": "/questions",
    "screenshot": "agent/1.png",
    "elements": [
        {
            "id": 1,
            "role": "textbox",
            "name": "검색",
            "box": {"x": 140, "y": 210, "w": 630, "h": 44},
        },
        {
            "id": 2,
            "role": "button",
            "name": "로그아웃",
            "box": {"x": 1100, "y": 20, "w": 80, "h": 30},
        },
        {
            "id": 3,
            "role": "link",
            "name": "질문 지도",
            "box": {"x": 600, "y": 20, "w": 80, "h": 30},
        },
    ],
    "history": [],
}


def _decider(tmp_path, replies, seen=None):
    def handler(req):
        if seen is not None:
            seen.append(json.loads(req.content))
        content = replies.pop(0)
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return agent.Decider(api_key="k", model="m", run_dir=tmp_path, client=client)


def test_decide_sends_marked_screenshot_and_safe_elements(tmp_path):
    seen: list[dict] = []
    reply = '{"action": "type", "id": 1, "value": "프로세스", "caption": "궁금한 개념을 찾아요"}'
    d = _decider(_run(tmp_path), [reply], seen)
    out = d.decide(OBS)
    assert out == {
        "action": "type",
        "id": 1,
        "value": "프로세스",
        "caption": "궁금한 개념을 찾아요",
    }
    parts = seen[0]["messages"][-1]["content"]
    text = next(p["text"] for p in parts if p["type"] == "text")
    assert "[1] textbox 검색" in text and "[3] link 질문 지도" in text
    assert "로그아웃" not in text  # 위험한 요소는 후보에서 뺀다
    assert any(p["type"] == "image_url" for p in parts)
    assert seen[0]["response_format"]["json_schema"]["strict"] is True


def test_invalid_choice_retries_then_done(tmp_path):
    bad = '{"action": "click", "id": 2, "value": "", "caption": "나가요"}'  # 위험 요소 번호
    d = _decider(_run(tmp_path), [bad, bad])
    assert d.decide(OBS) == {"action": "done"}


def test_retry_fixes_choice(tmp_path):
    bad = '{"action": "type", "id": 3, "value": "", "caption": "검색해요"}'  # 링크에 입력, 값 없음
    good = '{"action": "click", "id": 3, "value": "", "caption": "질문 지도를 열어요"}'
    seen: list[dict] = []
    d = _decider(_run(tmp_path), [bad, good], seen)
    assert d.decide(OBS) == {"action": "click", "id": 3, "caption": "질문 지도를 열어요"}
    assert "이전 답" in json.dumps(seen[1], ensure_ascii=False)


def test_llm_failure_is_done(tmp_path):
    def handler(req):
        return httpx.Response(402, json={"detail": "크레딧 부족"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    d = agent.Decider(api_key="k", model="m", run_dir=_run(tmp_path), client=client)
    assert d.decide(OBS) == {"action": "done"}


def test_main_loop_answers_one_line_per_observation(tmp_path, monkeypatch, capsys):
    class Fake:
        def decide(self, obs):
            return {"action": "scroll", "caption": f"{obs['step']}번째"}

    stdin = io.StringIO(json.dumps(OBS) + "\n" + json.dumps({**OBS, "step": 2}) + "\n")
    monkeypatch.setattr("sys.stdin", stdin)
    agent.serve(Fake())
    lines = capsys.readouterr().out.splitlines()
    assert [json.loads(line)["caption"] for line in lines] == ["1번째", "2번째"]


def test_goal_from_facts_and_prompt():
    facts = RepoFacts("CS 길라잡이", "꼬리질문으로 CS를 공부해요", [], "", "next-app", [])
    goal = agent.goal_for(facts, "질문 지도 위주로")
    assert "CS 길라잡이" in goal and "꼬리질문" in goal and "질문 지도 위주로" in goal


def test_repeat_of_done_action_is_rejected(tmp_path):  # cs-pathfinder: '오늘의 질문'을 두 번
    click = '{"action": "click", "id": 3, "value": "", "caption": "질문 지도를 열어요"}'
    other = '{"action": "type", "id": 1, "value": "프로세스", "caption": "개념을 찾아요"}'
    d = _decider(_run(tmp_path), [click, click, other])
    assert d.decide(OBS)["action"] == "click"
    assert d.decide({**OBS, "step": 2})["action"] == "type"  # 같은 이름은 다시 안 누른다
