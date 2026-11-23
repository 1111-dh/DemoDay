"""파이프라인 단계별 CLI — scripts/e2e.sh 와 FastAPI가 같은 함수를 호출한다.

  uv run python -m app.cli analyze --repo <github> --url <배포> --out runs/<id>/scenario.json
  uv run python -m app.cli scene   --run runs/<id> [--total-sec 60] [--architecture]
  uv run python -m app.cli facts   --repo <github>        # 분석 결과(RepoFacts)만 출력
  uv run python -m app.cli warm    [--file samples.json]  # 시연 레포 분석 캐시 채우기 (make warm)

각 단계는 결과 JSON을 쓰기 전에 schema_errors()로 검증하고, 위반이 있으면 exit 1.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

from app import paths
from app.contracts import schema_errors
from app.github import RepoError


class ContractError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("계약 위반:\n" + "\n".join(f"- {e}" for e in errors))


def analyze(
    repo: str, url: str, out: str, auth_file: str | None = None, prompt: str | None = None
) -> None:
    from app.llm import get_llm
    from app.scenario import analyze as run_analyze

    out_path = Path(out)
    scenario = run_analyze(repo, url, out_path.parent, get_llm(), prompt=prompt)
    if auth_file:  # 캡처 전 로그인 — LLM·캐시를 거친 뒤에 붙인다
        scenario = {**scenario, "auth": json.loads(Path(auth_file).read_text())}
    if errors := schema_errors("scenario", scenario):
        raise ContractError(errors)
    out_path.write_text(json.dumps(scenario, ensure_ascii=False, indent=2))
    print(f"✓ scenario {len(scenario['steps'])}단계 → {out}")


def _replayable(selector: str) -> str:
    """캡처가 접근성 이름에서 '→' 같은 기호를 지워 공백 두 칸이 남은 셀렉터
    (실제 이름 'CS 질문·해설 →개념을 이어 읽는 질문 지도')는 재생 때 못 찾는다.
    role 셀렉터의 name="…"은 전체 일치라서, 끊긴 조각 중 가장 긴 것을 정규식(부분 일치)으로 바꾼다.
    """

    def to_regex(m: re.Match) -> str:
        parts = [p.strip() for p in re.split(r"\s{2,}", m.group(1)) if p.strip()]
        if not parts:
            return m.group(0)
        return "name=/" + re.sub(r"([\\^$.|?*+()\[\]{}/])", r"\\\1", max(parts, key=len)) + "/"

    return re.sub(r'name="([^"]*\s{2,}[^"]*)"', to_regex, selector)


def _warm_agent(run_dir: Path, snap, sample: dict, facts) -> str:
    """에이전트 모드로 캡처를 한 번 돌리고, 에이전트가 실제로 한 동작을 시나리오 캐시에 쓴다."""
    import os

    from app import pipeline
    from app.scenario import scenario_cache_path

    before = os.environ.get("CAPTURE_MODE")
    os.environ["CAPTURE_MODE"] = "agent"
    try:
        pipeline.run_capture(run_dir)
    finally:
        if before is None:
            os.environ.pop("CAPTURE_MODE", None)
        else:
            os.environ["CAPTURE_MODE"] = before
    # 캡처는 에이전트가 동작했을 때만 원래 계획을 scenario.plan.json 으로 남기고
    # scenario.json 을 에이전트가 한 동작으로 덮어쓴다
    if not (run_dir / "scenario.plan.json").exists():
        return " (에이전트 실패 — 계획 시나리오 유지)"
    done = json.loads((run_dir / "scenario.json").read_text())
    done.pop("auth", None)  # 캐시에는 로그인 값을 넣지 않는다
    for step in done["steps"]:
        if sel := step.get("selector"):
            step["selector"] = _replayable(sel)
    if errors := schema_errors("scenario", done):
        return f" (에이전트 결과 계약 위반 — 계획 유지: {errors[0]})"
    cache = scenario_cache_path(snap, sample["url"], sample.get("prompt"), facts, paths.CACHE)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(done, ensure_ascii=False))
    return f", 에이전트 {len(done['steps'])}동작 캐시됨"


def warm(file: str, agent: bool = False) -> int:
    """시연 레포를 미리 분석해 runs/cache 를 채운다. 하나가 실패해도 계속. 실패가 있으면 1.

    agent 면 에이전트 녹화(#53)를 한 번 실제로 돌려, 에이전트가 한 동작을 시나리오 캐시에 덮어쓴다 —
    시연 때는 일반 모드로 그 동작을 재생한다(빠르고 매번 같다).
    """
    import tempfile
    import time

    from app import github
    from app.analyze.facts import RepoFacts
    from app.llm import get_llm
    from app.scenario import analyze as run_analyze
    from app.scenario import scenario_cache_path

    samples = json.loads(Path(file).read_text())
    snaps: list[github.RepoSnapshot] = []  # 분석이 쓴 스냅샷 (커밋 sha 확인용)

    def fetch(url: str) -> github.RepoSnapshot:
        snaps.append(github.fetch_repo(url))
        return snaps[-1]

    failed = 0
    for s in samples:
        start = time.monotonic()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                scenario = run_analyze(
                    s["repo"], s["url"], Path(tmp), get_llm(), prompt=s.get("prompt"), fetch=fetch
                )
                facts = RepoFacts.from_json((Path(tmp) / "facts.json").read_text())
                agent_note = _warm_agent(Path(tmp), snaps[-1], s, facts) if agent else ""
        except Exception as e:  # 시연 준비 — 하나가 깨져도 나머지는 데운다
            failed += 1
            print(f"✗ {s['repo']} — {e}")
            continue
        snap = snaps[-1]  # 지금 커밋의 시나리오 캐시가 있어야 시연 때 LLM 없이 즉시 나온다
        cache = scenario_cache_path(snap, s["url"], s.get("prompt"), facts, paths.CACHE)
        llm_made = cache.exists()
        kind = "LLM 시나리오 캐시됨" if llm_made else "규칙 기본값 (LLM 키 확인)"
        took = time.monotonic() - start
        if agent and not agent_note.startswith(
            ", 에이전트"
        ):  # 에이전트를 원했는데 못 했으면 실패로 센다
            failed += 1
            print(f"✗ {s['repo']} — 에이전트 캐시 실패{agent_note}, {took:.1f}s")
            continue
        print(f"✓ {s['repo']} — {len(scenario['steps'])}단계, {kind}{agent_note}, {took:.1f}s")
    print(f"{len(samples) - failed}/{len(samples)} 준비됨 → {paths.CACHE}")
    return 1 if failed else 0


def scene(run: str, total_sec: float, include_architecture: bool = False) -> None:
    from app.llm import get_llm
    from app.scene import build_scene
    from app.vision import get_describer

    doc = build_scene(
        Path(run), total_sec, include_architecture, get_llm(), describer=get_describer()
    )
    print(f"✓ scene {len(doc['scenes'])}장면 → {run}/scene.json")


def facts(repo: str) -> None:
    from app.analyze.facts import build_facts
    from app.github import fetch_repo

    print(build_facts(fetch_repo(repo)).to_json())


def main(argv: list[str] | None = None) -> int:
    load_dotenv(paths.ROOT / ".env")
    p = argparse.ArgumentParser(prog="app.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze")
    a.add_argument("--repo", required=True)
    a.add_argument("--url", required=True)
    a.add_argument("--out", required=True)
    a.add_argument("--auth", help="scenario.auth JSON 파일 (캡처 전 로그인 단계)")
    a.add_argument("--prompt", help="영상에 바라는 점 (화면 순서·자막 말투·강조, 500자)")
    s = sub.add_parser("scene")
    s.add_argument("--run", required=True)
    s.add_argument("--total-sec", type=float, default=60)
    s.add_argument("--architecture", action="store_true", help="마지막에 아키텍처 장면 넣기")
    g = sub.add_parser("goal", help="에이전트 녹화 목표 한 줄 (CAPTURE_MODE=agent)")
    g.add_argument("--run", required=True)
    f = sub.add_parser("facts")
    f.add_argument("--repo", required=True)
    w = sub.add_parser("warm", help="시연 레포 분석 캐시 채우기")
    w.add_argument("--file", default=str(paths.ROOT / "backend" / "samples.json"))
    w.add_argument("--agent", action="store_true", help="에이전트 녹화로 동작을 정해 캐시(#53)")
    args = p.parse_args(argv)
    try:
        if args.cmd == "analyze":
            analyze(args.repo, args.url, args.out, args.auth, args.prompt)
        elif args.cmd == "facts":
            facts(args.repo)
        elif args.cmd == "warm":
            return warm(args.file, args.agent)
        elif args.cmd == "goal":
            from app.pipeline import agent_capture

            os.environ["CAPTURE_MODE"] = "agent"
            print(agent_capture(Path(args.run))[0][2])
        else:
            scene(args.run, args.total_sec, args.architecture)
    except (RepoError, ContractError) as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
    except NotImplementedError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
