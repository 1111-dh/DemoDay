"""capture → scene → render 를 단계별 상태와 함께 실행 (FastAPI BackgroundTasks에서 호출)."""

from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path

import httpx

from app import llm, paths, runs, vision
from app.scene import build_scene

log = logging.getLogger(__name__)


CAPTURE_TIMEOUT = 300  # 최소 제한 — 단계가 많으면 단계당 15초씩 늘린다(_capture_timeout)
SEC_PER_CAPTURE_STEP = 15  # 녹화 1.5초 + 대기 2초 + 커서 0.8초 + 느린 이동·실패 대기 여유
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


AUTO_AGENT_BELOW = 4  # 코드 분석 시나리오가 이보다 짧으면 에이전트 녹화로 바꾼다
ANALYZED = "scenario.analyzed.json"  # analyze 직후 시나리오 — 사용자가 고쳤는지 비교한다


def use_agent(run_dir: Path) -> bool:
    """에이전트 녹화를 쓸지. CAPTURE_MODE=agent 면 항상, plan 이면 안 쓴다.

    비어 있으면(auto) 코드 분석이 빈약할 때만 쓴다 — 라우터 없는 SPA처럼 처음 보는 레포도
    실제 화면을 보고 눌러 보며 영상을 채운다(11/24). 판단 모델(BAZE) 키가 있어야 한다.
    """
    mode = os.environ.get("CAPTURE_MODE", "").strip().lower()
    if mode in ("agent", "plan"):
        return mode == "agent"
    if not os.environ.get("BAZE_API_KEY"):
        return False
    try:
        now = json.loads((run_dir / "scenario.json").read_text())
        analyzed = json.loads((run_dir / ANALYZED).read_text())
    except (OSError, ValueError):
        return False
    if now.get("auth"):  # 로그인이 필요한 서비스 — 에이전트가 로그인 화면을 녹화하지 않게
        return False
    # 사용자가 웹에서 고친 시나리오(단계를 지운 것 포함)는 그대로 녹화한다
    if now.get("steps") != analyzed.get("steps"):
        return False
    return len(analyzed.get("steps") or []) < AUTO_AGENT_BELOW


def _capture_timeout(run_dir: Path) -> float:
    try:
        n = len(json.loads((run_dir / "scenario.json").read_text())["steps"])
    except (OSError, ValueError, KeyError, TypeError):
        n = 0
    return max(CAPTURE_TIMEOUT, 60 + SEC_PER_CAPTURE_STEP * n)


def agent_capture(run_dir: Path) -> tuple[list[str], dict[str, str] | None]:
    """에이전트 녹화(use_agent)면 캡처에 넘길 인자(--agent --goal)와 에이전트 환경변수(#53)."""
    if not use_agent(run_dir):
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
        AGENT_CAPTURE_TIMEOUT if extra else _capture_timeout(run_dir),
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


SITE_DOWN = "배포 주소에 접속하지 못했어요(모든 페이지 이동 실패)"


def _site_alive(url: str) -> bool:
    """배포 주소가 응답하는지. 연결 실패·404·410·5xx(Vercel DEPLOYMENT_NOT_FOUND 등)면 False.

    401·403·429(로그인 필요·봇 차단)는 서버가 살아 있다는 뜻이라 True — 화면을 버리지 않는다.
    """
    try:
        res = httpx.get(url, timeout=10, follow_redirects=True)
    except (httpx.HTTPError, httpx.InvalidURL, ValueError):
        return False
    return not (res.status_code in (404, 410) or res.status_code >= 500)


def _site_unreachable(d: Path) -> bool:
    """사이트가 죽어 있다 — 페이지 이동(goto)이 하나도 성공하지 못했고, 배포 주소도 응답하지 않는다.

    이때 오류 페이지(Vercel 404 등)에서 한 scroll·click 이 'ok' 로 남아 오류 화면이 영상에
    들어간다(11/24 실측). goto 는 로딩 화면에서 멈춤·로그인 리다이렉트로도 실패하니
    (사이트는 산 경우) 주소에 직접 물어서 정말 죽었을 때만 True — 에이전트 모드처럼
    goto 가 하나뿐일 때 오판하지 않게.
    """
    try:
        scenario = json.loads((d / "scenario.json").read_text())
        shots = json.loads((d / "capture.json").read_text())["shots"]
    except (OSError, ValueError, KeyError):
        return False
    gotos = {s["id"] for s in scenario.get("steps", []) if s.get("action") == "goto"}
    tried = [s for s in shots if s.get("stepId") in gotos]
    all_failed = bool(tried) and all(
        s.get("status", "ok") != "ok" for s in tried
    )  # 없으면 ok(계약)
    return all_failed and not _site_alive(scenario.get("baseUrl", ""))


def _capture_or_empty(rid: str, d: Path) -> None:
    """캡처가 통째로 실패해도(사이트 응답 없음 등) 영상은 나오게 — 카드만으로."""
    hint = "실제 화면 없이 만들었어요. 사이트가 열리는지 확인하세요."
    try:
        run_capture(d)
    except Exception as e:
        log.warning("캡처 실패 %s — 화면 없이 계속: %s", rid, e)
        runs.write_json(d / "capture.json", EMPTY_CAPTURE)
        runs.write_status(rid, warning=f"{_summary(e)} — {hint}")
        return
    if _site_unreachable(d):
        log.warning("사이트 접속 실패 %s — 화면 없이 계속", rid)
        runs.write_json(d / "capture.json", EMPTY_CAPTURE)
        runs.write_status(rid, warning=f"{SITE_DOWN} — {hint}")


def save_logo(run_dir: Path) -> None:
    """배포 사이트 로고를 run 에 받아 둔다(연결·마무리 장면용, 실패해도 계속)."""
    from app.logo import fetch_logo

    try:
        base = json.loads((run_dir / "scenario.json").read_text())["baseUrl"]
    except (OSError, ValueError, KeyError, TypeError):
        return
    fetch_logo(base, run_dir)


def build(rid: str, total_sec: float, include_architecture: bool) -> None:
    try:
        d = runs.run_dir(rid)
        runs.write_status(rid, stage="capturing", warning=None)
        _capture_or_empty(rid, d)
        runs.write_status(rid, stage="scening")
        save_logo(d)
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
