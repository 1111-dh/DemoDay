import sys

import pytest

from app import pipeline


def test_run_times_out_as_runtime_error():  # 리뷰 #4
    with pytest.raises(RuntimeError, match="시간 초과"):
        pipeline._run([sys.executable, "-c", "import time; time.sleep(5)"], "캡처", timeout=0.2)


def test_agent_capture_args_only_in_agent_mode(tmp_path, monkeypatch):  # #53 — CAPTURE_MODE=agent
    from app.analyze.facts import RepoFacts
    from app.pipeline import agent_capture

    (tmp_path / "facts.json").write_text(
        RepoFacts("CS 길라잡이", "꼬리질문 학습", [], "", "next-app", []).to_json()
    )
    (tmp_path / "prompt.txt").write_text("질문 지도 위주로")
    monkeypatch.delenv("CAPTURE_MODE", raising=False)
    assert agent_capture(tmp_path) == ([], None)
    monkeypatch.setenv("CAPTURE_MODE", "agent")
    args, env = agent_capture(tmp_path)
    assert args[0] == "--agent" and args[1] == "--goal" and "CS 길라잡이" in args[2]
    assert "질문 지도 위주로" in args[2]
    assert env["DEMODAY_RUN_DIR"] == str(tmp_path.resolve())
    assert "DEMODAY_AGENT_CMD" not in env or env["DEMODAY_AGENT_CMD"] == __import__(
        "os"
    ).environ.get("DEMODAY_AGENT_CMD")  # 캡처 기본값(Windows 호환, #70)을 덮어쓰지 않는다


def test_auto_agent_when_analysis_is_thin(tmp_path, monkeypatch):  # 라우터 없는 SPA (11/24)
    import json

    from app.pipeline import use_agent

    def scenario(n):
        steps = [{"id": i, "action": "scroll", "caption": "x"} for i in range(1, n + 1)]
        doc = json.dumps({"baseUrl": "https://a.dev", "steps": steps})
        (tmp_path / "scenario.json").write_text(doc)
        (tmp_path / "scenario.analyzed.json").write_text(doc)  # 사용자가 고치지 않음

    monkeypatch.delenv("CAPTURE_MODE", raising=False)
    scenario(1)
    assert use_agent(tmp_path) is False  # 판단 모델 키가 없으면 안 쓴다
    monkeypatch.setenv("BAZE_API_KEY", "k")
    assert use_agent(tmp_path) is True
    scenario(6)
    assert use_agent(tmp_path) is False  # 코드 분석이 충분하면 계획대로
    monkeypatch.setenv("CAPTURE_MODE", "agent")
    assert use_agent(tmp_path) is True
    monkeypatch.setenv("CAPTURE_MODE", "plan")
    scenario(1)
    assert use_agent(tmp_path) is False


def test_auto_agent_respects_user_edits_and_login(tmp_path, monkeypatch):
    import json

    from app.pipeline import use_agent

    monkeypatch.delenv("CAPTURE_MODE", raising=False)
    monkeypatch.setenv("BAZE_API_KEY", "k")
    steps = [{"id": i, "action": "scroll", "caption": "x"} for i in range(1, 7)]
    (tmp_path / "scenario.analyzed.json").write_text(json.dumps({"steps": steps}))
    # 분석은 6단계였는데 사용자가 2단계만 남겼다 — 고친 대로 녹화한다
    edited = {"baseUrl": "https://a.dev", "steps": steps[:2]}
    (tmp_path / "scenario.json").write_text(json.dumps(edited))
    assert use_agent(tmp_path) is False
    thin = steps[:1]
    (tmp_path / "scenario.analyzed.json").write_text(json.dumps({"steps": thin}))
    auth = {"steps": [{"id": 1, "action": "goto", "path": "/login", "caption": "로그인"}]}
    doc = {"baseUrl": "https://a.dev", "steps": thin, "auth": auth}
    (tmp_path / "scenario.json").write_text(json.dumps(doc))
    assert use_agent(tmp_path) is False  # 로그인이 필요한 서비스는 자동으로 켜지 않는다


def test_capture_timeout_grows_with_steps(tmp_path):
    import json

    from app.pipeline import CAPTURE_TIMEOUT, _capture_timeout

    steps = [{"id": i, "action": "scroll", "caption": "x"} for i in range(1, 31)]
    (tmp_path / "scenario.json").write_text(json.dumps({"steps": steps}))
    assert _capture_timeout(tmp_path) == 60 + 15 * 30 > CAPTURE_TIMEOUT
    (tmp_path / "scenario.json").write_text(json.dumps({"steps": steps[:3]}))
    assert _capture_timeout(tmp_path) == CAPTURE_TIMEOUT
