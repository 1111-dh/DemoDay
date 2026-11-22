import json

from app import cli, llm, scenario

GOOD = {
    "baseUrl": "https://x.dev",
    "steps": [{"id": 1, "action": "goto", "path": "/", "caption": "c"}],
}


def _run(monkeypatch, tmp_path, result):
    monkeypatch.setattr(llm, "get_llm", lambda: None)
    monkeypatch.setattr(scenario, "analyze", lambda repo, url, out_dir, _llm, **kw: result)
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


def test_analyze_attaches_auth_file(monkeypatch, tmp_path):  # make e2e AUTH=…
    auth = {"steps": [{"id": 1, "action": "goto", "path": "/login?t=1", "caption": "로그인"}]}
    (tmp_path / "auth.json").write_text(json.dumps(auth))
    monkeypatch.setattr(llm, "get_llm", lambda: None)
    monkeypatch.setattr(scenario, "analyze", lambda repo, url, out_dir, _llm, **kw: dict(GOOD))
    out = tmp_path / "scenario.json"
    argv = ["analyze", "--repo", "r", "--url", "u", "--out", str(out)]
    assert cli.main([*argv, "--auth", str(tmp_path / "auth.json")]) == 0
    assert json.loads(out.read_text())["auth"] == auth


def test_warm_runs_every_sample_and_reports_failures(monkeypatch, tmp_path, capsys):
    from app import github, paths
    from app.github import RepoError, RepoSnapshot

    samples = [
        {"repo": "https://github.com/o/broken", "url": "https://a.dev"},
        {"repo": "https://github.com/o/good", "url": "https://b.dev"},
        {"repo": "https://github.com/o/stale", "url": "https://c.dev"},
    ]
    (tmp_path / "samples.json").write_text(json.dumps(samples))
    monkeypatch.setattr(paths, "CACHE", tmp_path / "cache")
    (tmp_path / "cache").mkdir()
    (tmp_path / "cache" / "scenario__o__good__new__k.json").write_text("{}")
    (tmp_path / "cache" / "scenario__o__stale__old__k.json").write_text("{}")  # 이전 커밋 것
    monkeypatch.setattr(
        github,
        "fetch_repo",
        lambda u: RepoSnapshot(owner="o", repo=u.rsplit("/", 1)[1], sha="new"),
    )
    seen = []

    def fake(repo, url, out_dir, _llm, *, fetch):
        seen.append(repo)
        if "broken" in repo:
            raise RepoError("레포를 찾을 수 없습니다")
        fetch(repo)
        return GOOD

    monkeypatch.setattr(llm, "get_llm", lambda: None)
    monkeypatch.setattr(scenario, "analyze", fake)
    assert cli.main(["warm", "--file", str(tmp_path / "samples.json")]) == 1
    assert seen == [s["repo"] for s in samples]
    lines = capsys.readouterr().out.splitlines()
    assert "✗ https://github.com/o/broken" in lines[0] and "찾을 수 없" in lines[0]
    assert "✓ https://github.com/o/good" in lines[1] and "LLM" in lines[1]
    assert "✓ https://github.com/o/stale" in lines[2] and "규칙 기본값" in lines[2]


def test_cli_analyze_passes_prompt(monkeypatch, tmp_path):  # make e2e PROMPT=…
    seen = {}

    def fake(repo, url, out_dir, _llm, **kw):
        seen.update(kw)
        return dict(GOOD)

    monkeypatch.setattr(llm, "get_llm", lambda: None)
    monkeypatch.setattr(scenario, "analyze", fake)
    out = tmp_path / "scenario.json"
    argv = ["analyze", "--repo", "r", "--url", "u", "--out", str(out), "--prompt", "톤은 발표용"]
    assert cli.main(argv) == 0
    assert seen["prompt"] == "톤은 발표용"
