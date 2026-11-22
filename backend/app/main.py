"""FastAPI 진입점 (A 담당). 실행: make dev-api  — 엔드포인트 표는 backend/AGENTS.md."""

from __future__ import annotations

import json

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app import llm, paths, pipeline, runs, scenario
from app.contracts import schema_errors
from app.github import RepoError

load_dotenv(paths.ROOT / ".env")

app = FastAPI(title="DemoDay API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateRun(BaseModel):
    repo: str
    url: str
    totalSec: float = Field(default=60, gt=0)


class BuildRun(BaseModel):
    includeArchitecture: bool = True
    totalSec: float | None = Field(default=None, gt=0)


def _dir(rid: str):
    try:
        return runs.run_dir(rid)
    except KeyError:
        raise HTTPException(404, "run을 찾을 수 없습니다") from None


def _validated(kind: str, data: dict) -> dict:
    if errors := schema_errors(kind, data):
        raise HTTPException(422, errors)
    return data


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/runs")
def create_run(body: CreateRun) -> dict:
    rid = runs.new_run()
    try:
        sc = scenario.analyze(body.repo, body.url, runs.run_dir(rid), llm.get_llm())
    except RepoError as e:
        runs.write_status(rid, stage="error", error=str(e))
        raise HTTPException(400, str(e)) from None
    runs.write_status(rid, stage="analyzed", repo=body.repo, url=body.url, totalSec=body.totalSec)
    return {"id": rid, "scenario": sc}


@app.put("/api/runs/{rid}/scenario")
def put_scenario(rid: str, body: dict) -> dict:
    d = _dir(rid)
    (d / "scenario.json").write_text(json.dumps(_validated("scenario", body), ensure_ascii=False))
    return {"ok": True}


@app.post("/api/runs/{rid}/build")
def build_run(rid: str, body: BuildRun, tasks: BackgroundTasks) -> dict:
    _dir(rid)
    status = runs.read_status(rid)
    total = body.totalSec or status.get("totalSec", 60)
    runs.write_status(rid, stage="queued", totalSec=total)
    tasks.add_task(pipeline.build, rid, total, body.includeArchitecture)
    return {"id": rid, "stage": "queued"}


@app.get("/api/runs/{rid}")
def get_run(rid: str) -> dict:
    d = _dir(rid)
    out = {"id": rid, **runs.read_status(rid)}
    for name in ("scenario", "scene"):
        if (f := d / f"{name}.json").exists():
            out[name] = json.loads(f.read_text())
    if (d / "preview.mp4").exists():
        out["videoUrl"] = f"/api/runs/{rid}/files/preview.mp4"
    return out


@app.put("/api/runs/{rid}/scene")
def put_scene(rid: str, body: dict, tasks: BackgroundTasks) -> dict:
    d = _dir(rid)
    (d / "scene.json").write_text(json.dumps(_validated("scene", body), ensure_ascii=False))
    runs.write_status(rid, stage="queued")
    tasks.add_task(pipeline.rerender, rid)
    return {"id": rid, "stage": "queued"}


@app.get("/api/runs/{rid}/files/{path:path}")
def get_file(rid: str, path: str) -> FileResponse:
    d = _dir(rid).resolve()
    f = (d / path).resolve()
    if not f.is_relative_to(d) or not f.is_file():
        raise HTTPException(404, "파일 없음")
    return FileResponse(f)
