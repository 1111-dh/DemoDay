import httpx
import pytest

from app.github import RepoError, fetch_repo, parse_repo_url, select_files, want_file

TREE = [
    {"path": "README.md", "type": "blob", "size": 100},
    {"path": "package.json", "type": "blob", "size": 50},
    {"path": "web", "type": "tree"},
    {"path": "web/package.json", "type": "blob", "size": 80},
    {"path": "web/src/app/page.tsx", "type": "blob", "size": 300},
    {"path": "web/src/app/search/page.tsx", "type": "blob", "size": 300},
    {"path": "web/src/lib/util.ts", "type": "blob", "size": 300},
    {"path": "web/node_modules/next/package.json", "type": "blob", "size": 80},
    {"path": "web/public/logo.png", "type": "blob", "size": 9000},
]


def make_transport(calls: list[str], *, status: int = 200, headers: dict | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if status != 200:
            return httpx.Response(status, headers=headers or {}, json={"message": "x"})
        host, path = request.url.host, request.url.path
        if host == "api.github.com":
            if path == "/repos/o/r":
                return httpx.Response(200, json={"default_branch": "main"})
            if path == "/repos/o/r/commits/main":
                return httpx.Response(200, json={"sha": "abc123"})
            if path == "/repos/o/r/git/trees/abc123":
                return httpx.Response(200, json={"tree": TREE, "truncated": False})
        if host == "raw.githubusercontent.com":
            return httpx.Response(200, text=f"content of {path}")
        return httpx.Response(404)

    return httpx.MockTransport(handler)


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/1111-dh/DemoDay",
        "https://github.com/1111-dh/DemoDay.git",
        "https://github.com/1111-dh/DemoDay/",
        "https://github.com/1111-dh/DemoDay/tree/main/web",
        "http://www.github.com/1111-dh/DemoDay",
    ],
)
def test_parse_repo_url_variants(url):
    assert parse_repo_url(url) == ("1111-dh", "DemoDay")


def test_parse_repo_url_rejects_non_github():
    with pytest.raises(RepoError):
        parse_repo_url("https://gitlab.com/a/b")


def test_want_file():
    assert want_file("README.md")
    assert want_file("web/package.json")
    assert want_file("web/src/app/page.tsx")
    assert want_file("src/App.tsx")
    assert want_file("src/routes.tsx")
    assert not want_file("web/src/lib/util.ts")
    assert not want_file("web/node_modules/next/package.json")
    assert not want_file("web/src/app/page.test.tsx")
    assert not want_file("web/public/logo.png")


def test_fetch_repo_uses_tree_and_raw(tmp_path):
    calls: list[str] = []
    client = httpx.Client(transport=make_transport(calls))
    snap = fetch_repo("https://github.com/o/r", client=client, cache_dir=tmp_path)
    assert (snap.owner, snap.repo, snap.sha) == ("o", "r", "abc123")
    assert "web/src/lib/util.ts" in snap.paths
    assert "web" not in snap.paths  # tree 항목 제외
    assert set(snap.files) == {
        "README.md",
        "package.json",
        "web/package.json",
        "web/src/app/page.tsx",
        "web/src/app/search/page.tsx",
    }
    assert snap.files["README.md"] == "content of /o/r/abc123/README.md"


def test_fetch_repo_cache_hit_skips_raw_downloads(tmp_path):
    calls: list[str] = []
    client = httpx.Client(transport=make_transport(calls))
    fetch_repo("https://github.com/o/r", client=client, cache_dir=tmp_path)
    calls.clear()
    snap = fetch_repo("https://github.com/o/r", client=client, cache_dir=tmp_path)
    assert not any("raw.githubusercontent.com" in c for c in calls)
    assert not any("/git/trees/" in c for c in calls)
    assert "web/package.json" in snap.files


def test_errors_are_readable(tmp_path):
    client = httpx.Client(transport=make_transport([], status=404))
    with pytest.raises(RepoError, match="찾을 수 없"):
        fetch_repo("https://github.com/o/r", client=client, cache_dir=tmp_path)

    limited = make_transport([], status=403, headers={"x-ratelimit-remaining": "0"})
    with pytest.raises(RepoError, match="GITHUB_TOKEN"):
        fetch_repo(
            "https://github.com/o/r", client=httpx.Client(transport=limited), cache_dir=tmp_path
        )


def test_want_file_skips_test_dirs():
    assert not want_file("frontend/src/app/test/renderApp.tsx")
    assert not want_file("src/__mocks__/handlers.ts")


def test_select_files_prefers_routers_and_pages():
    blobs = [
        {"path": p, "size": 100}
        for p in [
            "frontend/src/app/splash/SplashHost.tsx",
            "frontend/src/app/bootQueries.ts",
            "frontend/src/pages/login/ui/LoginPageSkeleton.tsx",
            "frontend/src/pages/dashboard/ui/DashboardPage.tsx",
            "frontend/src/app/router/routes.tsx",
            "frontend/package.json",
            "README.md",
        ]
    ] + [{"path": "src/pages/Huge.tsx", "size": 10_000_000}]
    assert select_files(blobs, limit=4) == [
        "frontend/package.json",
        "README.md",
        "frontend/src/app/router/routes.tsx",
        "frontend/src/pages/dashboard/ui/DashboardPage.tsx",
    ]


def _repo_transport(tree: list[dict], raw: dict[str, tuple[int, str]], calls: list[str]):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.raw_path.decode())
        host, path = request.url.host, request.url.path
        if host == "api.github.com":
            if path == "/repos/o/r":
                return httpx.Response(200, json={"default_branch": "main"})
            if path == "/repos/o/r/commits/main":
                return httpx.Response(200, json={"sha": "abc123"})
            if path == "/repos/o/r/git/trees/abc123":
                return httpx.Response(200, json={"tree": tree})
        if host == "raw.githubusercontent.com":
            status, text = raw.get(path.removeprefix("/o/r/abc123/"), (200, "x"))
            return httpx.Response(status, text=text)
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def _blobs(*paths):
    return [{"path": p, "type": "blob", "size": 10} for p in paths]


def test_fetch_skips_failed_file_and_quotes_path(tmp_path):  # 리뷰 #3
    calls: list[str] = []
    tree = _blobs("README.md", "src/App.tsx", "src/pages/C#Guide.tsx", "src/pages/Bad.tsx")
    client = httpx.Client(transport=_repo_transport(tree, {"src/pages/Bad.tsx": (500, "")}, calls))
    snap = fetch_repo("https://github.com/o/r", client=client, cache_dir=tmp_path)
    assert "src/pages/Bad.tsx" not in snap.files
    assert "src/pages/C#Guide.tsx" in snap.files
    assert "/o/r/abc123/src/pages/C%23Guide.tsx" in calls


def test_fetch_downloads_router_imports(tmp_path):  # 리뷰 #6
    app = "import Search from './views/Search'\nconst S = lazy(() => import('@/screens/Home'))"
    tree = _blobs("src/App.tsx", "src/views/Search.tsx", "src/screens/Home/index.tsx")
    client = httpx.Client(transport=_repo_transport(tree, {"src/App.tsx": (200, app)}, []))
    snap = fetch_repo("https://github.com/o/r", client=client, cache_dir=tmp_path)
    assert {"src/views/Search.tsx", "src/screens/Home/index.tsx"} <= set(snap.files)


def test_fetch_ignores_corrupt_cache(tmp_path):  # 리뷰 #7
    (tmp_path / "o__r__abc123.json").write_text('{"owner": "o", "rep')
    client = httpx.Client(transport=_repo_transport(_blobs("README.md"), {}, []))
    snap = fetch_repo("https://github.com/o/r", client=client, cache_dir=tmp_path)
    assert snap.files == {"README.md": "x"}
