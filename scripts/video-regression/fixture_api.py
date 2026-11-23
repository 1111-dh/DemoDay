"""Isolated test API. Only the repository source is substituted."""

import os
from functools import partial
from pathlib import Path

from fastapi.responses import HTMLResponse

from app import paths, scenario
from app.github import RepoSnapshot
from app.main import app

paths.RUNS = Path(os.environ["VIDEO_TEST_OUTPUT"])
repo = "https://github.com/demo/local-example"


def snapshot(url):
    if url != repo:
        raise ValueError(f"Unexpected repository: {url}")
    files = {"README.md": "# Demo Board\nA local project board."}
    return RepoSnapshot("demo", "local-example", "fixture-v1", list(files), files)


scenario.analyze = partial(scenario.analyze, fetch=snapshot, cache_dir=paths.RUNS / "cache")


@app.get("/", response_class=HTMLResponse)
def example():
    return (
        "<html lang=en><title>Demo Board</title><h1>Demo Board</h1><p>Ready for review</p></html>"
    )
