"""파이프라인 단계별 CLI — scripts/e2e.sh 와 FastAPI가 같은 함수를 호출한다.

  uv run python -m app.cli analyze --repo <github> --url <배포> --out runs/<id>/scenario.json
  uv run python -m app.cli scene   --run runs/<id> [--total-sec 60] [--no-architecture]
  uv run python -m app.cli facts   --repo <github>        # 분석 결과(RepoFacts)만 출력
  uv run python -m app.cli warm    [--file samples.json]  # 시연 레포 분석 캐시 채우기 (make warm)

각 단계는 결과 JSON을 쓰기 전에 schema_errors()로 검증하고, 위반이 있으면 exit 1.
"""

from __future__ import annotations

import argparse
import json
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


def warm(file: str) -> int:
    """시연 레포를 미리 분석해 runs/cache 를 채운다. 하나가 실패해도 계속. 실패가 있으면 1."""
    import tempfile
    import time

    from app import github
    from app.llm import get_llm
    from app.scenario import analyze as run_analyze

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
                scenario = run_analyze(s["repo"], s["url"], Path(tmp), get_llm(), fetch=fetch)
        except Exception as e:  # 시연 준비 — 하나가 깨져도 나머지는 데운다
            failed += 1
            print(f"✗ {s['repo']} — {e}")
            continue
        snap = snaps[-1]  # 지금 커밋의 시나리오 캐시가 있어야 시연 때 LLM 없이 즉시 나온다
        llm_made = any(paths.CACHE.glob(f"scenario__{snap.owner}__{snap.repo}__{snap.sha}__*.json"))
        kind = "LLM 시나리오 캐시됨" if llm_made else "규칙 기본값 (LLM 키 확인)"
        took = time.monotonic() - start
        print(f"✓ {s['repo']} — {len(scenario['steps'])}단계, {kind}, {took:.1f}s")
    print(f"{len(samples) - failed}/{len(samples)} 준비됨 → {paths.CACHE}")
    return 1 if failed else 0


def scene(run: str, total_sec: float, include_architecture: bool = True) -> None:
    from app.llm import get_llm
    from app.scene import build_scene

    doc = build_scene(Path(run), total_sec, include_architecture, get_llm())
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
    s.add_argument("--no-architecture", action="store_true")
    f = sub.add_parser("facts")
    f.add_argument("--repo", required=True)
    w = sub.add_parser("warm", help="시연 레포 분석 캐시 채우기")
    w.add_argument("--file", default=str(paths.ROOT / "backend" / "samples.json"))
    args = p.parse_args(argv)
    try:
        if args.cmd == "analyze":
            analyze(args.repo, args.url, args.out, args.auth, args.prompt)
        elif args.cmd == "facts":
            facts(args.repo)
        elif args.cmd == "warm":
            return warm(args.file)
        else:
            scene(args.run, args.total_sec, not args.no_architecture)
    except (RepoError, ContractError) as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
    except NotImplementedError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
