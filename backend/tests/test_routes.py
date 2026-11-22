from app.analyze.routes import find_app_root, next_routes
from tests.conftest import make_snap, pkg


def route_paths(routes):
    return [(r.path, r.dynamic) for r in routes]


def test_monorepo_web_subdir(demo_like_snap):
    root = find_app_root(demo_like_snap)
    assert root is not None
    assert (root.dir, root.framework) == ("web", "next-app")
    routes = next_routes(demo_like_snap, root)
    assert route_paths(routes) == [("/", False), ("/search", False)]
    assert routes[1].file == "web/src/app/search/page.tsx"


def test_next_special_segments():
    snap = make_snap(
        {"package.json": pkg({"next": "16"})},
        extra_paths=[
            "app/page.tsx",
            "app/(marketing)/about/page.tsx",
            "app/posts/[id]/page.tsx",
            "app/docs/[...slug]/page.tsx",
            "app/@modal/x/page.tsx",
            "app/(.)photo/page.tsx",
            "app/_lib/page.tsx",
            "app/layout.tsx",
        ],
    )
    root = find_app_root(snap)
    assert root.framework == "next-app"
    assert route_paths(next_routes(snap, root)) == [
        ("/", False),
        ("/about", False),
        ("/docs/[...slug]", True),
        ("/posts/[id]", True),
    ]


def test_next_pages_router():
    snap = make_snap(
        {"package.json": pkg({"next": "14"})},
        extra_paths=[
            "src/pages/index.tsx",
            "src/pages/about.tsx",
            "src/pages/blog/[slug].tsx",
            "src/pages/blog/index.tsx",
            "src/pages/_app.tsx",
            "src/pages/_document.tsx",
            "src/pages/api/hello.ts",
        ],
    )
    root = find_app_root(snap)
    assert (root.dir, root.framework) == ("", "next-pages")
    assert route_paths(next_routes(snap, root)) == [
        ("/", False),
        ("/about", False),
        ("/blog", False),
        ("/blog/[slug]", True),
    ]


def test_react_app_root():
    snap = make_snap({"client/package.json": pkg({"react": "18", "react-router-dom": "6"})})
    root = find_app_root(snap)
    assert (root.dir, root.framework) == ("client", "react")


def test_next_preferred_over_react():
    snap = make_snap(
        {
            "admin/package.json": pkg({"react": "18"}),
            "site/package.json": pkg({"next": "15", "react": "19"}),
        },
        extra_paths=["site/app/page.tsx"],
    )
    assert find_app_root(snap).dir == "site"


def test_no_app_returns_none():
    snap = make_snap({"package.json": pkg({"@angular/core": "18"})})
    assert find_app_root(snap) is None


def test_next_app_only_exact_page_files():  # 리뷰 #2
    snap = make_snap(
        {"package.json": pkg({"next": "16"})},
        extra_paths=[
            "app/page.tsx",
            "app/about/page.tsx",
            "app/components/Subpage.tsx",
            "app/landingpage.tsx",
        ],
    )
    assert [r.path for r in next_routes(snap, find_app_root(snap))] == ["/", "/about"]
