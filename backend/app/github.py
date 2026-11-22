"""공개 GitHub 레포에서 분석에 필요한 파일만 받아온다 (커밋 sha 단위 캐시)."""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import quote

import httpx

from app import paths

API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"
MAX_FILES = 80
MAX_BYTES = 200_000
EXTRA_FILES = 40  # 라우터가 import 하는 페이지 컴포넌트 (views/·screens/ 등 힌트 밖 경로)

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
)
_CODE_EXT = (".tsx", ".jsx", ".ts", ".js")
_ROUTE_HINTS = ("app/", "pages/", "routes", "router", "App.", "main.")
_IMPORT_SPEC = re.compile(r"""(?:from\s+|import\s*\(\s*)["'](\.{1,2}/[^"']+|@/[^"']+)["']""")
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


def _rank(path: str) -> int:
    """받을 순서. 0 README·package.json → 1 라우터 → 2 페이지 → 3 기타 → 4 스켈레톤·스타일."""
    name = path.rsplit("/", 1)[-1]
    stem = name.split(".", 1)[0]
    low = stem.lower()
    if name == "package.json" or ("/" not in path and low.startswith("readme")):
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


def _resolve(spec: str, from_file: str, known: set[str]) -> str | None:
    """`./x`·`../x`·`@/x`(가장 가까운 src/ 기준) → 레포 안 실제 코드 파일."""
    if spec.startswith("@/"):
        parts = from_file.split("/")[:-1]
        while parts and parts[-1] != "src":
            parts.pop()
        if not parts:
            return None
        parts += spec[2:].split("/")
    else:
        parts = from_file.split("/")[:-1]
        for seg in spec.split("/"):
            if seg == "..":
                parts = parts[:-1]
            elif seg != ".":
                parts.append(seg)
    base = "/".join(parts)
    for cand in [base, *(base + e for e in _CODE_EXT), *(f"{base}/index{e}" for e in _CODE_EXT)]:
        if cand in known and cand.endswith(_CODE_EXT):
            return cand
    return None


def router_imports(files: dict[str, str], blobs: list[dict]) -> list[str]:
    """받은 라우터 파일(_rank 1)이 import 하는 아직 안 받은 코드 파일."""
    sizes = {b["path"]: b.get("size", 0) for b in blobs}
    known = set(sizes)
    out: list[str] = []
    for path, src in files.items():
        if _rank(path) != 1:
            continue
        for spec in _IMPORT_SPEC.findall(src):
            target = _resolve(spec, path, known)
            if (
                target
                and target not in files
                and target not in out
                and sizes[target] <= MAX_BYTES
                and not any(f"/{d}" in f"/{target}" for d in _SKIP_DIRS)
                and not _TEST_HINT.search(target)
            ):
                out.append(target)
    return out[:EXTRA_FILES]


def _download(client: httpx.Client, owner: str, repo: str, sha: str, paths: list[str]) -> dict:
    """파일 하나가 실패해도 전체를 멈추지 않는다 — 그 파일만 빼고 기록."""
    files: dict[str, str] = {}
    for p in paths:
        try:
            files[p] = _get(client, f"{RAW}/{owner}/{repo}/{sha}/{quote(p)}", {}).text
        except RepoError as e:
            log.warning("파일 건너뜀 %s: %s", p, e)
    return files


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
        try:
            return RepoSnapshot.from_json(cache.read_text())
        except (ValueError, TypeError):
            log.warning("깨진 캐시 무시: %s", cache.name)

    tree = _get(client, f"{API}/repos/{owner}/{repo}/git/trees/{sha}?recursive=1", headers).json()
    blobs = [t for t in tree.get("tree", []) if t.get("type") == "blob"]
    all_paths = [t["path"] for t in blobs]
    targets = select_files(blobs)

    files = _download(client, owner, repo, sha, targets)
    files |= _download(client, owner, repo, sha, router_imports(files, blobs))
    snap = RepoSnapshot(owner=owner, repo=repo, sha=sha, paths=all_paths, files=files)
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(".tmp")
    tmp.write_text(snap.to_json())
    os.replace(tmp, cache)
    return snap
