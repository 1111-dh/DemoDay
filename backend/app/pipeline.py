"""capture → scene → render 를 단계별 상태와 함께 실행 (FastAPI BackgroundTasks에서 호출)."""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

from app import llm, paths, runs, vision
from app.scene import build_scene

log = logging.getLogger(__name__)


CAPTURE_TIMEOUT = 300  # 단계당 5초 × 최대 7단계 + 브라우저 기동 여유
RENDER_TIMEOUT = 900


def _run(cmd: list[str], what: str, timeout: float, env: dict[str, str] | None = None) -> None:
    try:
        res = subprocess.run(
            cmd, cwd=paths.ROOT, capture_output=True, text=True, timeout=timeout, env=env
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{what} 시간 초과 ({timeout:g}초)") from None
    if res.returncode != 0:
        tail = "\n".join((res.stderr or res.stdout).strip().splitlines()[-20:])
        raise RuntimeError(f"{what} 실패:\n{tail}")


AGENT_CAPTURE_TIMEOUT = 600  # 에이전트 모드: 최대 10동작 × (판단 + 실행·녹화)


def agent_capture(run_dir: Path) -> tuple[list[str], dict[str, str] | None]:
    """CAPTURE_MODE=agent 면 캡처에 넘길 인자(--agent --goal)와 에이전트 환경변수(#53)."""
    if os.environ.get("CAPTURE_MODE", "").strip().lower() != "agent":
        return [], None
    from app.agent import goal_for
    from app.analyze.facts import RepoFacts

    facts = RepoFacts.from_json((run_dir / "facts.json").read_text())
    prompt_file = run_dir / "prompt.txt"
    prompt = prompt_file.read_text() if prompt_file.exists() else None
    # 에이전트 명령은 캡처 기본값(uv run --directory backend, Windows 호환 #70)을 쓴다
    env = {
        **os.environ,
        "DEMODAY_RUN_DIR": str(run_dir.resolve()),
    }
    return ["--agent", "--goal", goal_for(facts, prompt)], env


def run_capture(run_dir: Path) -> None:
    extra, env = agent_capture(run_dir)
    _run(
        [
            "pnpm",
            "--silent",
            "--filter",
            "@demoday/capture",
            "capture",
            str(run_dir / "scenario.json"),
            str(run_dir),
            *extra,
        ],
        "캡처",
        AGENT_CAPTURE_TIMEOUT if extra else CAPTURE_TIMEOUT,
        env,
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
            "--scale=1.5",
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
        build_scene(
            d, total_sec, include_architecture, llm.get_llm(), describer=vision.get_describer()
        )
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
