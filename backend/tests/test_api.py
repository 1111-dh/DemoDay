import json
import shutil

import pytest
from fastapi.testclient import TestClient

from app import llm, paths, pipeline, runs, scenario
from app.analyze.elements import Element
from app.analyze.facts import PageFacts, RepoFacts
from app.github import RepoError
from app.main import app

FIXTURES = paths.ROOT / "contracts" / "fixtures"
FACTS = RepoFacts("Demo", "소개", ["next"], "", "next-app", [])
LOGIN_FACTS = RepoFacts(
    "Demo",
    "소개",
    ["next"],
    "",
    "next-app",
    [
        PageFacts(
            "/login",
            False,
            "f",
            [
                Element("input", "email", "input[name=email]"),
                Element("input", "password", "input[name=password]"),
                Element("button", "로그인", "text=로그인"),
            ],
        )
    ],
)
SEEN: dict = {}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(llm, "get_llm", lambda: None)

    def fake_analyze(repo, url, out_dir, _llm, **kw):
        SEEN.clear()
        SEEN.update(kw)
        if "nope" in repo:
            raise RepoError("레포를 찾을 수 없습니다")
        sc = json.loads((FIXTURES / "scenario.json").read_text())
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "scenario.json").write_text(json.dumps(sc))
        facts = LOGIN_FACTS if "login" in repo else FACTS
        (out_dir / "facts.json").write_text(facts.to_json())
        return sc

    def fake_capture(run_dir):
        shutil.copy(FIXTURES / "capture.json", run_dir / "capture.json")
        shutil.copytree(FIXTURES / "shots", run_dir / "shots", dirs_exist_ok=True)

    def fake_render(run_dir):
        (run_dir / "preview.mp4").write_bytes(b"mp4")

    monkeypatch.setattr(scenario, "analyze", fake_analyze)
    monkeypatch.setattr(pipeline, "run_capture", fake_capture)
    monkeypatch.setattr(pipeline, "run_render", fake_render)
    return TestClient(app)


def create(client):
    res = client.post(
        "/api/runs",
        json={"repo": "https://github.com/o/r", "url": "https://x.dev", "totalSec": 60},
    )
    assert res.status_code == 200, res.text
    return res.json()


def test_create_run_returns_scenario(client):
    body = create(client)
    assert body["scenario"]["baseUrl"] == "https://sample.vercel.app"
    assert client.get(f"/api/runs/{body['id']}").json()["stage"] == "analyzed"


def test_bad_repo_url_400(client):
    res = client.post(
        "/api/runs", json={"repo": "https://github.com/o/nope", "url": "https://x.dev"}
    )
    assert res.status_code == 400
    assert "찾을 수 없" in res.json()["detail"]


def test_put_scenario_rejects_invalid(client):
    rid = create(client)["id"]
    bad = {"baseUrl": "https://x.dev", "steps": [{"id": 1, "action": "click", "caption": "c"}]}
    res = client.put(f"/api/runs/{rid}/scenario", json=bad)
    assert res.status_code == 422
    assert any("selector" in e for e in res.json()["detail"])


def test_put_scenario_saves(client):
    rid = create(client)["id"]
    sc = {
        "baseUrl": "https://x.dev",
        "steps": [{"id": 1, "action": "goto", "path": "/", "caption": "c"}],
    }
    assert client.put(f"/api/runs/{rid}/scenario", json=sc).status_code == 200
    assert json.loads((runs.run_dir(rid) / "scenario.json").read_text()) == sc


def test_build_flow_sets_done(client):
    rid = create(client)["id"]
    res = client.post(f"/api/runs/{rid}/build", json={"includeArchitecture": False})
    assert res.status_code == 200
    run = client.get(f"/api/runs/{rid}").json()
    assert run["stage"] == "done"
    assert [s["type"] for s in run["scene"]["scenes"]] == ["title", "screen", "screen"]
    assert run["videoUrl"] == f"/api/runs/{rid}/files/preview.mp4"
    assert client.get(run["videoUrl"]).content == b"mp4"


def test_capture_failure_still_makes_video(client, monkeypatch):  # 실패해도 영상은 나와야 한다
    def boom(run_dir):
        raise RuntimeError("캡처 실패: timeout")

    monkeypatch.setattr(pipeline, "run_capture", boom)
    rid = create(client)["id"]
    client.post(f"/api/runs/{rid}/build", json={})
    run = client.get(f"/api/runs/{rid}").json()
    assert run["stage"] == "done" and "error" not in run
    assert "캡처 실패" in run["warning"]
    assert all(s["type"] != "screen" for s in run["scene"]["scenes"])
    assert run["videoUrl"] == f"/api/runs/{rid}/files/preview.mp4"


def test_warning_cleared_on_next_build(client, monkeypatch):
    real = pipeline.run_capture

    def boom(run_dir):
        raise RuntimeError("캡처 실패: timeout")

    monkeypatch.setattr(pipeline, "run_capture", boom)
    rid = create(client)["id"]
    client.post(f"/api/runs/{rid}/build", json={})
    monkeypatch.setattr(pipeline, "run_capture", real)
    client.post(f"/api/runs/{rid}/build", json={})
    assert "warning" not in client.get(f"/api/runs/{rid}").json()


def test_render_failure_sets_error_stage(client, monkeypatch):
    def boom(run_dir):
        raise RuntimeError("렌더 실패: oom")

    monkeypatch.setattr(pipeline, "run_render", boom)
    rid = create(client)["id"]
    client.post(f"/api/runs/{rid}/build", json={})
    run = client.get(f"/api/runs/{rid}").json()
    assert (run["stage"], run["error"]) == ("error", "렌더 실패: oom")


def test_put_scene_rerenders(client):
    rid = create(client)["id"]
    client.post(f"/api/runs/{rid}/build", json={})
    (runs.run_dir(rid) / "preview.mp4").unlink()
    doc = client.get(f"/api/runs/{rid}").json()["scene"]
    doc["scenes"][0]["text"] = "새 제목"
    assert client.put(f"/api/runs/{rid}/scene", json=doc).status_code == 200
    run = client.get(f"/api/runs/{rid}").json()
    assert run["stage"] == "done" and run["scene"]["scenes"][0]["text"] == "새 제목"
    assert (runs.run_dir(rid) / "preview.mp4").exists()


def test_put_scene_rejects_invalid(client):
    rid = create(client)["id"]
    res = client.put(f"/api/runs/{rid}/scene", json={"fps": 30, "totalSec": 10, "scenes": []})
    assert res.status_code == 422


def test_unknown_run_404(client):
    assert client.get("/api/runs/0000-000000-zzzz").status_code == 404


def test_files_blocks_traversal(client):
    rid = create(client)["id"]
    assert client.get(f"/api/runs/{rid}/files/%2e%2e%2f%2e%2e%2f.env").status_code == 404
    with pytest.raises(KeyError):
        runs.run_dir("../cache")


def test_build_and_scene_rejected_while_busy(client):  # 리뷰 #5
    rid = create(client)["id"]
    runs.write_status(rid, stage="capturing")
    assert client.post(f"/api/runs/{rid}/build", json={}).status_code == 409
    doc = json.loads((FIXTURES / "scene.json").read_text())
    assert client.put(f"/api/runs/{rid}/scene", json=doc).status_code == 409


def test_status_written_atomically(client, monkeypatch):  # 리뷰 #5
    import os

    replaced = []
    real = os.replace
    monkeypatch.setattr(os, "replace", lambda a, b: (replaced.append(str(b)), real(a, b)))
    rid = create(client)["id"]
    runs.write_status(rid, stage="analyzed")
    assert any(p.endswith("status.json") for p in replaced)


def test_create_run_unexpected_error_has_detail(client, monkeypatch):  # 리뷰 #7
    def boom(*a, **k):
        raise ValueError("깨진 캐시")

    monkeypatch.setattr(scenario, "analyze", boom)
    res = client.post("/api/runs", json={"repo": "https://github.com/o/r", "url": "https://x.dev"})
    assert res.status_code == 500
    assert "깨진 캐시" in res.json()["detail"]


def test_get_run_tolerates_half_written_scene(client):  # 리뷰 #5
    rid = create(client)["id"]
    (runs.run_dir(rid) / "scene.json").write_text('{"fps": 3')
    res = client.get(f"/api/runs/{rid}")
    assert res.status_code == 200 and "scene" not in res.json()


AUTH = {
    "steps": [
        {"id": 1, "action": "goto", "path": "/api/demo/login?secret=abc123", "caption": "로그인"},
        {
            "id": 2,
            "action": "type",
            "selector": "input[name=pw]",
            "value": "pw!",
            "caption": "비번",
        },
    ]
}


def create_with_auth(client, auth=AUTH):
    return client.post(
        "/api/runs", json={"repo": "https://github.com/o/r", "url": "https://x.dev", "auth": auth}
    )


def test_create_run_with_auth_saves_real_and_returns_redacted(client):
    res = create_with_auth(client)
    assert res.status_code == 200, res.text
    rid, shown = res.json()["id"], res.json()["scenario"]["auth"]["steps"]
    assert (shown[0]["path"], shown[1]["value"]) == ("/api/demo/login?***", "***")
    saved = json.loads((runs.run_dir(rid) / "scenario.json").read_text())
    assert saved["auth"] == AUTH
    assert client.get(f"/api/runs/{rid}").json()["scenario"]["auth"]["steps"][1]["value"] == "***"


def test_put_redacted_scenario_keeps_stored_secrets(client):
    rid = create_with_auth(client).json()["id"]
    sc = client.get(f"/api/runs/{rid}").json()["scenario"]
    sc["steps"][0]["caption"] = "바꾼 자막"
    assert client.put(f"/api/runs/{rid}/scenario", json=sc).status_code == 200
    saved = json.loads((runs.run_dir(rid) / "scenario.json").read_text())
    assert saved["auth"] == AUTH and saved["steps"][0]["caption"] == "바꾼 자막"


def test_create_run_invalid_auth_422(client):
    assert create_with_auth(client, {"steps": []}).status_code == 422


def _post(client, **extra):
    body = {"repo": "https://github.com/o/r", "url": "https://x.dev", **extra}
    return client.post("/api/runs", json=body)


def test_create_run_with_login(client):
    res = _post(
        client,
        repo="https://github.com/o/login-app",
        login={"username": "demo@x.dev", "password": "pw-123"},
    )
    assert res.status_code == 200, res.text
    steps = res.json()["scenario"]["auth"]["steps"]
    assert [s["action"] for s in steps] == ["goto", "type", "type", "click", "wait", "wait"]
    assert steps[2]["value"] == "***"
    stored = json.loads((runs.run_dir(res.json()["id"]) / "scenario.json").read_text())
    assert stored["auth"]["steps"][2]["value"] == "pw-123"


def test_create_run_login_not_found_is_400(client):
    res = _post(client, login={"username": "u", "password": "p"})
    assert res.status_code == 400
    assert "로그인 URL" in res.json()["detail"]


def test_create_run_login_and_auth_conflict_422(client):
    auth = {"steps": [{"id": 1, "action": "goto", "path": "/l", "caption": "로그인"}]}
    res = _post(client, login={"username": "u", "password": "p"}, auth=auth)
    assert res.status_code == 422


def test_create_run_prompt_too_long_422(client):
    assert _post(client, prompt="가" * 501).status_code == 422


def test_create_run_passes_prompt(client):
    assert _post(client, prompt="검색 위주").status_code == 200
    assert SEEN["prompt"] == "검색 위주"


def test_files_endpoint_never_serves_secrets(client):  # 최종 리뷰 #1
    res = _post(
        client,
        repo="https://github.com/o/login-app",
        login={"username": "demo@x.dev", "password": "pw-123"},
    )
    rid = res.json()["id"]
    (runs.run_dir(rid) / "prompt.txt").write_text("p")
    for name in ["scenario.json", "facts.json", "status.json", "prompt.txt"]:
        assert client.get(f"/api/runs/{rid}/files/{name}").status_code == 404, name


def test_capture_warning_includes_detail_line(client, monkeypatch):
    def boom(run_dir):
        raise RuntimeError(
            "캡처 실패:\n! step 1 (goto) fallback\n"
            "✗ page.screenshot: Timeout 5000ms exceeded.\nCall log:"
        )

    monkeypatch.setattr(pipeline, "run_capture", boom)
    rid = create(client)["id"]
    client.post(f"/api/runs/{rid}/build", json={})
    warning = client.get(f"/api/runs/{rid}").json()["warning"]
    assert warning.startswith("캡처 실패: page.screenshot: Timeout 5000ms exceeded.")


def test_create_run_empty_login_is_422(client):
    assert _post(client, login={"username": "", "password": "p"}).status_code == 422
    assert _post(client, login={"username": "u", "password": ""}).status_code == 422


def test_architecture_scene_is_off_by_default(client, monkeypatch):  # 임시 뼈대 장면이라 기본 끔
    from app import pipeline

    seen = []
    monkeypatch.setattr(pipeline, "build", lambda rid, total, arch: seen.append(arch))
    client.post(f"/api/runs/{create(client)['id']}/build", json={})
    client.post(f"/api/runs/{create(client)['id']}/build", json={"includeArchitecture": True})
    assert seen == [False, True]


def test_site_unreachable_is_treated_like_capture_failure(client, monkeypatch):
    """배포 사이트가 죽어 있으면 goto 는 전부 실패인데, 오류 페이지에서 한 scroll 은 ok 로 남는다.
    그 오류 페이지가 영상에 들어가지 않고, 경고가 남아야 한다(11/24 Vercel 404 실측)."""
    import json

    def dead_site(run_dir):
        sc = json.loads((run_dir / "scenario.json").read_text())
        shots = []
        for s in sc["steps"]:
            ok = s["action"] == "scroll"  # 오류 페이지에서 스크롤만 '성공'
            shots.append(
                {
                    "stepId": s["id"],
                    "image": "shots/1.png",
                    "click": None,
                    "status": "ok" if ok else "fallback",
                }
            )
        (run_dir / "shots").mkdir(exist_ok=True)
        (run_dir / "shots" / "1.png").write_bytes(b"png")
        (run_dir / "capture.json").write_text(
            json.dumps({"viewport": {"w": 1280, "h": 720}, "shots": shots})
        )

    monkeypatch.setattr(pipeline, "run_capture", dead_site)
    rid = create(client)["id"]
    client.post(f"/api/runs/{rid}/build", json={})
    run = client.get(f"/api/runs/{rid}").json()
    assert run["stage"] == "done"
    assert "접속" in run["warning"]
    assert all(s["type"] != "screen" for s in run["scene"]["scenes"])
