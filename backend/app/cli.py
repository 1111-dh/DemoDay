"""파이프라인 단계별 CLI — scripts/e2e.sh 와 FastAPI가 같은 함수를 호출한다.

  uv run python -m app.cli analyze --repo <github> --url <배포> --out runs/<id>/scenario.json
  uv run python -m app.cli scene   --run runs/<id> [--total-sec 60]

각 단계는 결과 JSON을 쓰기 전에 schema_errors()로 검증하고, 위반이 있으면 exit 1.
"""

from __future__ import annotations

import argparse
import sys


def analyze(repo: str, url: str, out: str) -> None:
    # TODO(A): GitHub API로 라우트·README 수집 → LLM → scenario.json
    raise NotImplementedError("analyze 단계 미구현 (A)")


def scene(run: str, total_sec: float) -> None:
    # TODO(A): run/scenario.json + run/capture.json → LLM → run/scene.json
    #          LLM 출력은 schema_errors('scene', ...) 로 검증, 실패 시 에러를 붙여 재시도(최대 2회)
    raise NotImplementedError("scene 단계 미구현 (A)")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="app.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze")
    a.add_argument("--repo", required=True)
    a.add_argument("--url", required=True)
    a.add_argument("--out", required=True)
    s = sub.add_parser("scene")
    s.add_argument("--run", required=True)
    s.add_argument("--total-sec", type=float, default=60)
    args = p.parse_args(argv)
    try:
        if args.cmd == "analyze":
            analyze(args.repo, args.url, args.out)
        else:
            scene(args.run, args.total_sec)
    except NotImplementedError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
