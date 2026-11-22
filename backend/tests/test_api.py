import json
import shutil

import pytest
from fastapi.testclient import TestClient

from app import llm, paths, pipeline, runs, scenario
from app.analyze.facts import RepoFacts
from app.github import RepoError
from app.main import app

FIXTURES = paths.ROOT / "contracts" / "fixtures"
FACTS = RepoFacts("Demo", "소개", ["next"], "", "next-app", [])


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(llm, "get_llm", lambda: None)

    def fake_analyze(repo, url, out_dir, _llm):
        if "nope" in repo:
            raise RepoError("레포를 찾을 수 없습니다")
        sc = json.loads((FIXTURES / "scenario.json").read_text())
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "scenario.json").write_text(json.dumps(sc))
        (out_dir / "facts.json").write_text(FACTS.to_json())
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


def test_build_error_sets_error_stage(client, monkeypatch):
    def boom(run_dir):
        raise RuntimeError("캡처 실패: timeout")

    monkeypatch.setattr(pipeline, "run_capture", boom)
    rid = create(client)["id"]
    client.post(f"/api/runs/{rid}/build", json={})
    run = client.get(f"/api/runs/{rid}").json()
    assert (run["stage"], run["error"]) == ("error", "캡처 실패: timeout")


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
