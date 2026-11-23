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
        {"repo": "https://github.com/o/oldver", "url": "https://d.dev"},
    ]
    (tmp_path / "samples.json").write_text(json.dumps(samples))
    monkeypatch.setattr(paths, "CACHE", tmp_path / "cache")
    (tmp_path / "cache").mkdir()
    from app.analyze.facts import RepoFacts
    from app.scenario import scenario_cache_path

    facts = RepoFacts("n", "s", [], "", "next-app", [])
    good = RepoSnapshot(owner="o", repo="good", sha="new")
    scenario_cache_path(good, "https://b.dev", None, facts, tmp_path / "cache").write_text("{}")
    (tmp_path / "cache" / "scenario__o__stale__old__k.json").write_text("{}")  # 이전 커밋 것
    # 같은 커밋이지만 이전 버전·다른 프롬프트 키 — 지금 시연에는 안 쓰인다
    (tmp_path / "cache" / "scenario__o__oldver__new__deadbeef.json").write_text("{}")
    monkeypatch.setattr(
        github,
        "fetch_repo",
        lambda u: RepoSnapshot(owner="o", repo=u.rsplit("/", 1)[1], sha="new"),
    )
    seen = []

    def fake(repo, url, out_dir, _llm, *, fetch, **_):
        seen.append(repo)
        if "broken" in repo:
            raise RepoError("레포를 찾을 수 없습니다")
        fetch(repo)
        (out_dir / "facts.json").write_text(facts.to_json())  # analyze 가 남기는 분석 결과
        return GOOD

    monkeypatch.setattr(llm, "get_llm", lambda: None)
    monkeypatch.setattr(scenario, "analyze", fake)
    assert cli.main(["warm", "--file", str(tmp_path / "samples.json")]) == 1
    assert seen == [s["repo"] for s in samples]
    lines = capsys.readouterr().out.splitlines()
    assert "✗ https://github.com/o/broken" in lines[0] and "찾을 수 없" in lines[0]
    assert "✓ https://github.com/o/good" in lines[1] and "LLM" in lines[1]
    assert "✓ https://github.com/o/stale" in lines[2] and "규칙 기본값" in lines[2]
    assert "✓ https://github.com/o/oldver" in lines[3] and "규칙 기본값" in lines[3]


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


def test_warm_passes_sample_prompt(monkeypatch, tmp_path):  # 시연 때 쓸 프롬프트로 미리 캐시
    from app import github
    from app.github import RepoSnapshot

    samples = [
        {"repo": "https://github.com/o/r", "url": "https://a.dev", "prompt": "예시 리포트 위주"}
    ]
    (tmp_path / "samples.json").write_text(json.dumps(samples, ensure_ascii=False))
    monkeypatch.setattr(github, "fetch_repo", lambda u: RepoSnapshot(owner="o", repo="r", sha="s"))
    seen = {}

    def fake(repo, url, out_dir, _llm, **kw):
        seen.update(kw)
        kw["fetch"](repo)
        (out_dir / "facts.json").write_text(
            json.dumps(
                {
                    "name": "n",
                    "summary": "s",
                    "stack": [],
                    "app_dir": None,
                    "framework": None,
                    "pages": [],
                }
            )
        )
        return GOOD

    monkeypatch.setattr(llm, "get_llm", lambda: None)
    monkeypatch.setattr(scenario, "analyze", fake)
    cli.main(["warm", "--file", str(tmp_path / "samples.json")])
    assert seen["prompt"] == "예시 리포트 위주"
