"""레포 기준 경로. runs/ 는 git 제외 실행 산출물."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "runs"
CACHE = RUNS / "cache"
