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
