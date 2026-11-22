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


EMPTY_CAPTURE = {"viewport": {"w": 1280, "h": 720}, "shots": []}


def _summary(e: Exception) -> str:
    """'캡처 실패:' + 캡처 로그의 ✗ 줄(없으면 마지막 줄) 한 줄."""
    lines = [ln.strip() for ln in str(e).splitlines() if ln.strip()]
    if not lines:
        return type(e).__name__
    head, rest = lines[0], lines[1:]
    detail = next((ln for ln in rest if ln.startswith("✗")), rest[-1] if rest else "")
    return f"{head} {detail.removeprefix('✗').strip()}".strip()[:200]


def _capture_or_empty(rid: str, d: Path) -> None:
    """캡처가 통째로 실패해도(사이트 응답 없음 등) 영상은 나오게 — 카드·아키텍처로만."""
    try:
        run_capture(d)
    except Exception as e:
        log.warning("캡처 실패 %s — 화면 없이 계속: %s", rid, e)
        runs.write_json(d / "capture.json", EMPTY_CAPTURE)
        msg = _summary(e)
        hint = "실제 화면 없이 만들었어요. 사이트가 열리는지 확인하세요."
        runs.write_status(rid, warning=f"{msg} — {hint}")


def build(rid: str, total_sec: float, include_architecture: bool) -> None:
    try:
        d = runs.run_dir(rid)
        runs.write_status(rid, stage="capturing", warning=None)
        _capture_or_empty(rid, d)
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
