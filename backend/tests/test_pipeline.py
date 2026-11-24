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
        (tmp_path / "scenario.json").write_text(
            json.dumps({"baseUrl": "https://a.dev", "steps": steps})
        )

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
