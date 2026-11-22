"""공개 GitHub 레포에서 분석에 필요한 파일만 받아온다 (커밋 sha 단위 캐시)."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import httpx

from app import paths

API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"
MAX_FILES = 80
MAX_BYTES = 200_000

_URL = re.compile(r"^https?://(?:www\.)?github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?(?:/.*)?$")
_SKIP_DIRS = ("node_modules/", "dist/", ".next/", "build/", "out/", "coverage/")
_CODE_EXT = (".tsx", ".jsx", ".ts", ".js")
_ROUTE_HINTS = ("app/", "pages/", "routes", "router", "App.", "main.")
_TEST_HINT = re.compile(r"(\.test\.|\.spec\.|__tests__/)")


class RepoError(Exception):
    """사용자에게 그대로 보여줄 수 있는 레포 수집 오류."""


@dataclass
class RepoSnapshot:
    owner: str
    repo: str
    sha: str
    paths: list[str] = field(default_factory=list)
    files: dict[str, str] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str) -> RepoSnapshot:
        return cls(**json.loads(text))


def parse_repo_url(url: str) -> tuple[str, str]:
    m = _URL.match(url.strip())
    if not m:
        raise RepoError(f"GitHub 레포 URL이 아닙니다: {url}")
    return m.group(1), m.group(2)


def want_file(path: str) -> bool:
    if any(f"/{d}" in f"/{path}" for d in _SKIP_DIRS) or _TEST_HINT.search(path):
        return False
    name = path.rsplit("/", 1)[-1]
    if "/" not in path and name.lower().startswith("readme"):
        return True
    if name == "package.json":
        return True
    return path.endswith(_CODE_EXT) and any(h in path for h in _ROUTE_HINTS)


def _get(client: httpx.Client, url: str, headers: dict[str, str]) -> httpx.Response:
    try:
        res = client.get(url, headers=headers)
    except httpx.HTTPError as e:
        raise RepoError(f"GitHub 연결 실패: {e}") from e
    if res.status_code == 404:
        raise RepoError("레포를 찾을 수 없습니다 (공개 레포인지 확인하세요)")
    if res.status_code in (403, 429) and res.headers.get("x-ratelimit-remaining") == "0":
        raise RepoError("GitHub rate limit 초과 — 서버 .env 에 GITHUB_TOKEN 을 설정하세요")
    if res.status_code != 200:
        raise RepoError(f"GitHub 응답 오류 {res.status_code}: {url}")
    return res


def fetch_repo(
    url: str, *, client: httpx.Client | None = None, cache_dir: Path = paths.CACHE
) -> RepoSnapshot:
    owner, repo = parse_repo_url(url)
    client = client or httpx.Client(timeout=20, follow_redirects=True)
    headers = {"Accept": "application/vnd.github+json"}
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"

    branch = _get(client, f"{API}/repos/{owner}/{repo}", headers).json()["default_branch"]
    sha = _get(client, f"{API}/repos/{owner}/{repo}/commits/{branch}", headers).json()["sha"]

    cache = cache_dir / f"{owner}__{repo}__{sha}.json"
    if cache.exists():
        return RepoSnapshot.from_json(cache.read_text())

    tree = _get(client, f"{API}/repos/{owner}/{repo}/git/trees/{sha}?recursive=1", headers).json()
    blobs = [t for t in tree.get("tree", []) if t.get("type") == "blob"]
    all_paths = [t["path"] for t in blobs]
    targets = [t["path"] for t in blobs if want_file(t["path"]) and t.get("size", 0) <= MAX_BYTES][
        :MAX_FILES
    ]

    files = {p: _get(client, f"{RAW}/{owner}/{repo}/{sha}/{p}", {}).text for p in targets}
    snap = RepoSnapshot(owner=owner, repo=repo, sha=sha, paths=all_paths, files=files)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache.write_text(snap.to_json())
    return snap
