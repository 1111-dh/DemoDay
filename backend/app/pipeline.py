"""capture → scene → render 를 단계별 상태와 함께 실행 (FastAPI BackgroundTasks에서 호출)."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from app import llm, paths, runs
from app.scene import build_scene

log = logging.getLogger(__name__)


CAPTURE_TIMEOUT = 300  # 단계당 5초 × 최대 7단계 + 브라우저 기동 여유
RENDER_TIMEOUT = 900


def _run(cmd: list[str], what: str, timeout: float) -> None:
    try:
        res = subprocess.run(cmd, cwd=paths.ROOT, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{what} 시간 초과 ({timeout:g}초)") from None
    if res.returncode != 0:
        tail = "\n".join((res.stderr or res.stdout).strip().splitlines()[-20:])
        raise RuntimeError(f"{what} 실패:\n{tail}")


def run_capture(run_dir: Path) -> None:
    _run(
        [
            "pnpm",
            "--silent",
            "--filter",
            "@demoday/capture",
            "capture",
            str(run_dir / "scenario.json"),
            str(run_dir),
        ],
        "캡처",
        CAPTURE_TIMEOUT,
    )


def run_render(run_dir: Path) -> None:
    _run(
        [
            "pnpm",
            "--silent",
            "--filter",
            "@demoday/render",
            "render",
            str(run_dir),
            str(run_dir / "preview.mp4"),
            "--scale=0.5",
        ],
        "렌더",
        RENDER_TIMEOUT,
    )


def build(rid: str, total_sec: float, include_architecture: bool) -> None:
    try:
        d = runs.run_dir(rid)
        runs.write_status(rid, stage="capturing")
        run_capture(d)
        runs.write_status(rid, stage="scening")
        build_scene(d, total_sec, include_architecture, llm.get_llm())
        runs.write_status(rid, stage="rendering")
        run_render(d)
        runs.write_status(rid, stage="done")
    except Exception as e:  # 어떤 실패든 상태로 남겨 웹이 보여줄 수 있게
        log.exception("build 실패 %s", rid)
        runs.write_status(rid, stage="error", error=str(e))


def rerender(rid: str) -> None:
    try:
        runs.write_status(rid, stage="rendering")
        run_render(runs.run_dir(rid))
        runs.write_status(rid, stage="done")
    except Exception as e:
        log.exception("rerender 실패 %s", rid)
        runs.write_status(rid, stage="error", error=str(e))
