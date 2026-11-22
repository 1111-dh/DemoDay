import json

import pytest

from app.github import RepoSnapshot


def make_snap(
    files: dict[str, str], extra_paths: list[str] | None = None, loader=None
) -> RepoSnapshot:
    """loader(path) -> str|None 를 주면 files 에 없는 경로를 snap.read 가 그걸로 받는다."""
    paths = sorted(set(files) | set(extra_paths or []))
    snap = RepoSnapshot(owner="o", repo="r", sha="s", paths=paths, files=dict(files))
    snap.loader = loader
    return snap


def pkg(deps: dict[str, str] | None = None, dev: dict[str, str] | None = None) -> str:
    return json.dumps({"dependencies": deps or {}, "devDependencies": dev or {}})


@pytest.fixture
def demo_like_snap() -> RepoSnapshot:
    """DemoDay 자체처럼 Next 앱이 web/ 하위에 있는 모노레포."""
    return make_snap(
        {
            "README.md": "# DemoDay\n2026 해커톤\n\n레포를 넣으면 데모 영상을 만든다.\n",
            "package.json": pkg(dev={"typescript": "5"}),
            "web/package.json": pkg({"next": "16", "react": "19"}),
            "web/src/app/page.tsx": (
                '<main><Link href="/search">검색하러 가기</Link><button>시작하기</button></main>'
            ),
            "web/src/app/search/page.tsx": (
                '<form><input name="q" placeholder="키워드" /><button>검색</button></form>'
            ),
        },
        extra_paths=["web/src/lib/util.ts"],
    )
