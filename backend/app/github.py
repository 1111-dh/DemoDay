"""공개 GitHub 레포에서 분석에 필요한 파일만 받아온다 (커밋 sha 단위 캐시)."""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

import httpx

from app import paths

API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"
MAX_FILES = 80
MAX_BYTES = 200_000
LAZY_FILES = 150  # 분석 중 snap.read 로 추가로 받는 파일 상한 (컴포넌트 따라가기)

_URL = re.compile(r"^https?://(?:www\.)?github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?(?:/.*)?$")
_SKIP_DIRS = (
    "node_modules/",
    "dist/",
    ".next/",
    "build/",
    "out/",
    "coverage/",
    "test/",
    "tests/",
    "__mocks__/",
    "mocks/",
    "stories/",
    ".nuxt/",
    ".output/",
    ".svelte-kit/",
    ".dart_tool/",
)
CODE_EXT = (".tsx", ".jsx", ".ts", ".js", ".vue", ".svelte", ".dart")
_MANIFESTS = ("package.json", "pubspec.yaml")
_ROUTE_HINTS = ("app/", "pages/", "routes", "router", "App.", "main.")
log = logging.getLogger(__name__)
_TEST_HINT = re.compile(r"(\.test\.|\.spec\.|\.stories\.|__tests__/)")


class RepoError(Exception):
    """사용자에게 그대로 보여줄 수 있는 레포 수집 오류."""


@dataclass
class RepoSnapshot:
    owner: str
    repo: str
    sha: str
    paths: list[str] = field(default_factory=list)
    files: dict[str, str] = field(default_factory=dict)
    # 직렬화하지 않는 런타임 필드: 처음에 안 받은 파일을 분석 중에 받는 함수, 저장 위치
    loader: Callable[[str], str | None] | None = field(default=None, repr=False, compare=False)
    cache_path: Path | None = field(default=None, repr=False, compare=False)

    def read(self, path: str) -> str | None:
        """받아 둔 파일, 없으면 레포에 있는 경로일 때만 loader 로 받아 기록한다."""
        if path in self.files:
            return self.files[path]
        if self.loader is None or path not in self._known():
            return None
        text = self.loader(path)
        if text is not None:
            self.files[path] = text
        return text

    def _known(self) -> set[str]:
        if getattr(self, "_known_set", None) is None or len(self._known_set) != len(self.paths):
            self._known_set = set(self.paths)
        return self._known_set

    def save(self) -> None:
        """분석 중 더 받은 파일까지 캐시에 남긴다 (원자적 교체)."""
        if self.cache_path is None:
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.cache_path.with_suffix(".tmp")
        tmp.write_text(self.to_json())
        os.replace(tmp, self.cache_path)

    def to_json(self) -> str:
        data = {k: getattr(self, k) for k in ("owner", "repo", "sha", "paths", "files")}
        return json.dumps(data, ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str) -> RepoSnapshot:
        d = json.loads(text)
        return cls(**{k: d[k] for k in ("owner", "repo", "sha", "paths", "files")})


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
    if name in _MANIFESTS:
        return True
    return path.endswith(CODE_EXT) and any(h in path for h in _ROUTE_HINTS)


def _rank(path: str) -> int:
    """받을 순서. 0 README·매니페스트 → 1 라우터 → 2 페이지 → 3 기타 → 4 스켈레톤·스타일."""
    name = path.rsplit("/", 1)[-1]
    stem = name.split(".", 1)[0].lstrip("+")  # SvelteKit +page.svelte
    low = stem.lower()
    if name in _MANIFESTS or ("/" not in path and low.startswith("readme")):
        return 0
    if low in ("app", "main", "routes", "router") or low.endswith(("routes", "router")):
        return 1
    if "skeleton" in low or low in ("styles", "shell"):
        return 4
    if low == "page" or stem.endswith("Page") or re.search(r"(?:^|/)pages/[^/]+$", path):
        return 2
    return 3


def select_files(blobs: list[dict], limit: int = MAX_FILES) -> list[str]:
    """트리 blob 중 분석에 쓸 파일을 우선순위대로 최대 limit개."""
    wanted = [b["path"] for b in blobs if want_file(b["path"]) and b.get("size", 0) <= MAX_BYTES]
    return sorted(wanted, key=_rank)[:limit]


def _raw(client: httpx.Client, owner: str, repo: str, sha: str, path: str) -> str | None:
    """파일 하나가 실패해도 전체를 멈추지 않는다 — None 을 돌려주고 그 파일만 뺀다."""
    try:
        return _get(client, f"{RAW}/{owner}/{repo}/{sha}/{quote(path)}", {}).text
    except RepoError as e:
        log.warning("파일 건너뜀 %s: %s", path, e)
        return None


def _lazy_loader(
    client: httpx.Client, owner: str, repo: str, sha: str, sizes: dict[str, int]
) -> Callable[[str], str | None]:
    budget = [LAZY_FILES]

    def load(path: str) -> str | None:
        if budget[0] <= 0 or not path.endswith(CODE_EXT) or sizes.get(path, 0) > MAX_BYTES:
            return None
        budget[0] -= 1
        return _raw(client, owner, repo, sha, path)

    return load


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
    snap = None
    if cache.exists():
        try:
            snap = RepoSnapshot.from_json(cache.read_text())
        except (ValueError, TypeError, KeyError):
            log.warning("깨진 캐시 무시: %s", cache.name)

    sizes: dict[str, int] = {}
    if snap is None:
        tree_url = f"{API}/repos/{owner}/{repo}/git/trees/{sha}?recursive=1"
        blobs = [t for t in _get(client, tree_url, headers).json().get("tree", [])]
        blobs = [t for t in blobs if t.get("type") == "blob"]
        sizes = {t["path"]: t.get("size", 0) for t in blobs}
        files = {}
        for p in select_files(blobs):
            if (text := _raw(client, owner, repo, sha, p)) is not None:
                files[p] = text
        snap = RepoSnapshot(owner=owner, repo=repo, sha=sha, paths=list(sizes), files=files)
    snap.loader = _lazy_loader(client, owner, repo, sha, sizes)
    snap.cache_path = cache
    snap.save()
    return snap
