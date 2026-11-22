import json

from app import cli, llm, scenario

GOOD = {
    "baseUrl": "https://x.dev",
    "steps": [{"id": 1, "action": "goto", "path": "/", "caption": "c"}],
}


def _run(monkeypatch, tmp_path, result):
    monkeypatch.setattr(llm, "get_llm", lambda: None)
    monkeypatch.setattr(scenario, "analyze", lambda repo, url, out_dir, _llm: result)
    out = tmp_path / "draft.json"
    code = cli.main(
        ["analyze", "--repo", "https://github.com/o/r", "--url", "https://x.dev", "--out", str(out)]
    )
    return code, out


def test_analyze_writes_exact_out_path(monkeypatch, tmp_path):  # 리뷰 #10
    code, out = _run(monkeypatch, tmp_path, GOOD)
    assert code == 0
    assert json.loads(out.read_text()) == GOOD


def test_analyze_rejects_invalid_scenario(monkeypatch, tmp_path):  # 리뷰 #10
    code, out = _run(monkeypatch, tmp_path, {"baseUrl": "x", "steps": []})
    assert code == 1
    assert not out.exists()
