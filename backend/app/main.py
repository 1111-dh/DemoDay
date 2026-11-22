"""FastAPI 진입점 (A 담당). 실행: make dev-api  — 엔드포인트 표는 backend/AGENTS.md."""

from __future__ import annotations

import json
import logging

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app import auth, llm, paths, pipeline, runs, scenario
from app.analyze.facts import RepoFacts
from app.contracts import schema_errors
from app.github import RepoError
from app.login import login_steps
from app.scenario import MAX_PROMPT

load_dotenv(paths.ROOT / ".env")
log = logging.getLogger(__name__)

app = FastAPI(title="DemoDay API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class Login(BaseModel):
    username: str
    password: str


class CreateRun(BaseModel):
    repo: str
    url: str
    totalSec: float = Field(default=60, gt=0)
    auth: dict | None = None  # scenario.auth — 캡처 전 로그인 (응답에서는 가림)
    login: Login | None = None  # 테스트 계정 — A가 로그인 폼에서 auth 단계를 만든다
    prompt: str | None = Field(default=None, max_length=MAX_PROMPT)  # 영상에 바라는 점


class BuildRun(BaseModel):
    includeArchitecture: bool = True
    totalSec: float | None = Field(default=None, gt=0)


def _dir(rid: str):
    try:
        return runs.run_dir(rid)
    except KeyError:
        raise HTTPException(404, "run을 찾을 수 없습니다") from None


LOGIN_NOT_FOUND = (
    "로그인 입력칸을 찾지 못했습니다 — "
    "소셜 로그인만 있는 앱이면 로그인 URL을 직접 넣어 주세요(auth)"
)
_PROBE_STEP = {"id": 1, "action": "goto", "path": "/", "caption": "-"}


def _not_busy(rid: str) -> None:
    if runs.is_busy(rid):
        raise HTTPException(409, "이미 작업 중입니다 — 끝난 뒤 다시 시도하세요")


def _validated(kind: str, data: dict) -> dict:
    if errors := schema_errors(kind, data):
        raise HTTPException(422, errors)
    return data


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/runs")
def create_run(body: CreateRun) -> dict:
    if body.login is not None and body.auth is not None:
        raise HTTPException(422, "login 과 auth 중 하나만 보내세요")
    if body.auth is not None:
        probe = {"baseUrl": body.url, "auth": body.auth, "steps": [_PROBE_STEP]}
        if errors := schema_errors("scenario", probe):
            raise HTTPException(422, errors)
    rid = runs.new_run()
    try:
        sc = scenario.analyze(
            body.repo, body.url, runs.run_dir(rid), llm.get_llm(), prompt=body.prompt
        )
    except RepoError as e:
        runs.write_status(rid, stage="error", error=str(e))
        raise HTTPException(400, str(e)) from None
    except Exception as e:  # 예상 못 한 분석 실패도 웹이 메시지를 보여줄 수 있게
        log.exception("analyze 실패 %s", rid)
        runs.write_status(rid, stage="error", error=f"분석 실패: {e}")
        raise HTTPException(500, f"분석 실패: {e}") from None
    login_auth = None
    if body.login is not None:
        facts = RepoFacts.from_json((runs.run_dir(rid) / "facts.json").read_text())
        login_auth = login_steps(facts, body.login.username, body.login.password)
        if login_auth is None:
            msg = LOGIN_NOT_FOUND
            runs.write_status(rid, stage="error", error=msg)
            raise HTTPException(400, msg)
    if (auth_block := body.auth or login_auth) is not None:
        # LLM·캐시를 거친 뒤에 붙인다 — 비밀값은 run 디렉터리에만
        sc = {**sc, "auth": auth_block}
        runs.write_json(runs.run_dir(rid) / "scenario.json", sc)
    runs.write_status(rid, stage="analyzed", repo=body.repo, url=body.url, totalSec=body.totalSec)
    return {"id": rid, "scenario": auth.redact(sc)}


@app.put("/api/runs/{rid}/scenario")
def put_scenario(rid: str, body: dict) -> dict:
    d = _dir(rid)
    _not_busy(rid)
    stored = json.loads((d / "scenario.json").read_text()) if (d / "scenario.json").exists() else {}
    runs.write_json(d / "scenario.json", _validated("scenario", auth.restore(body, stored)))
    return {"ok": True}


@app.post("/api/runs/{rid}/build")
def build_run(rid: str, body: BuildRun, tasks: BackgroundTasks) -> dict:
    _dir(rid)
    _not_busy(rid)
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
            try:
                data = json.loads(f.read_text())
                out[name] = auth.redact(data) if name == "scenario" else data
            except json.JSONDecodeError:  # 백그라운드 단계가 쓰는 중 — 다음 폴링에서 읽힌다
                pass
    if (d / "preview.mp4").exists():
        out["videoUrl"] = f"/api/runs/{rid}/files/preview.mp4"
    return out


@app.put("/api/runs/{rid}/scene")
def put_scene(rid: str, body: dict, tasks: BackgroundTasks) -> dict:
    d = _dir(rid)
    _not_busy(rid)
    runs.write_json(d / "scene.json", _validated("scene", body))
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
