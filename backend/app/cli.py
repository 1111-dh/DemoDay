"""파이프라인 단계별 CLI — scripts/e2e.sh 와 FastAPI가 같은 함수를 호출한다.

  uv run python -m app.cli analyze --repo <github> --url <배포> --out runs/<id>/scenario.json
  uv run python -m app.cli scene   --run runs/<id> [--total-sec 60] [--no-architecture]
  uv run python -m app.cli facts   --repo <github>        # 분석 결과(RepoFacts)만 출력

각 단계는 결과 JSON을 쓰기 전에 schema_errors()로 검증하고, 위반이 있으면 exit 1.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from app import paths
from app.github import RepoError


def analyze(repo: str, url: str, out: str) -> None:
    from app.llm import get_llm
    from app.scenario import analyze as run_analyze

    scenario = run_analyze(repo, url, Path(out).parent, get_llm())
    print(f"✓ scenario {len(scenario['steps'])}단계 → {out}")


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
    s = sub.add_parser("scene")
    s.add_argument("--run", required=True)
    s.add_argument("--total-sec", type=float, default=60)
    s.add_argument("--no-architecture", action="store_true")
    f = sub.add_parser("facts")
    f.add_argument("--repo", required=True)
    args = p.parse_args(argv)
    try:
        if args.cmd == "analyze":
            analyze(args.repo, args.url, args.out)
        elif args.cmd == "facts":
            facts(args.repo)
        else:
            scene(args.run, args.total_sec, not args.no_architecture)
    except RepoError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
    except NotImplementedError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
