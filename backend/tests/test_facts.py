from app.analyze.code_routes import react_routes
from app.analyze.facts import RepoFacts, build_facts
from app.analyze.routes import find_app_root
from tests.conftest import make_snap, pkg

ROUTER_JSX = """
import Home from "./pages/Home";
import Search from "./pages/Search";
export default function App() {
  return (<Routes>
    <Route path="/" element={<Home />} />
    <Route path="/search" element={<Search />} />
    <Route path="/items/:id" element={<Item />} />
  </Routes>);
}
"""

ROUTER_OBJ = """
import About from './routes/About'
const router = createBrowserRouter([
  { path: "/", element: <Root /> },
  { path: "about", element: <About /> },
]);
"""


def test_react_router_jsx_style():
    snap = make_snap(
        {
            "package.json": pkg({"react": "18", "react-router-dom": "6"}),
            "src/App.tsx": ROUTER_JSX,
            "src/pages/Search.tsx": "<button>찾기</button>",
        },
        extra_paths=["src/pages/Home.tsx"],
    )
    routes = react_routes(snap, find_app_root(snap))
    assert [(r.path, r.dynamic, r.file) for r in routes] == [
        ("/", False, "src/pages/Home.tsx"),
        ("/search", False, "src/pages/Search.tsx"),
        ("/items/:id", True, "src/App.tsx"),
    ]


def test_react_router_object_style():
    snap = make_snap(
        {"package.json": pkg({"react": "18"}), "src/main.tsx": ROUTER_OBJ},
        extra_paths=["src/routes/About.jsx"],
    )
    routes = react_routes(snap, find_app_root(snap))
    assert [(r.path, r.file) for r in routes] == [
        ("/", "src/main.tsx"),
        ("/about", "src/routes/About.jsx"),
    ]


def test_build_facts_demo_like_repo(demo_like_snap):
    facts = build_facts(demo_like_snap)
    assert facts.name == "DemoDay"
    assert facts.summary == "2026 해커톤"
    assert (facts.app_dir, facts.framework) == ("web", "next-app")
    assert facts.stack == ["next", "react"]
    assert [p.path for p in facts.pages] == ["/", "/search"]
    search = facts.pages[1]
    assert [e.selector for e in search.elements] == [
        "input[name=q]",
        "text=검색",
    ]
    assert RepoFacts.from_json(facts.to_json()) == facts


def test_build_facts_no_app():
    snap = make_snap({"package.json": pkg({"@angular/core": "18"})})
    facts = build_facts(snap)
    assert (facts.app_dir, facts.framework, facts.pages) == (None, None, [])
    assert facts.name == "r"


ROUTER_NESTED = """
export const appRoutes = (
  <Route path="/" element={<Root />}>
    <Route element={<Guard />}>
      <Route index element={screen(landing)} />
      <Route path="login" element={screen(login)} />
    </Route>
    <Route path="workspaces/:id" element={<Team />}>
      <Route element={<Layout />}>
        <Route path="dashboard" element={screen(dash)} />
        <Route path="meetings/upload" element={<PM />}>
          <Route index element={screen(up)} />
        </Route>
      </Route>
    </Route>
    <Route path="*" element={<NotFound />} />
  </Route>
)
"""


def test_react_router_nested_paths_join_parents():
    snap = make_snap({"package.json": pkg({"react": "18"}), "src/routes.tsx": ROUTER_NESTED})
    routes = react_routes(snap, find_app_root(snap))
    assert [r.path for r in routes] == [
        "/",
        "/login",
        "/workspaces/:id",
        "/workspaces/:id/dashboard",
        "/workspaces/:id/meetings/upload",
    ]


def test_readme_body_strips_markup_and_limits():
    from app.analyze.facts import README_LIMIT, readme_body

    readme = (
        '<div align="center">\n<img src="x.png" />\n\n# 안정형\n\n'
        "[![Flutter](https://img.shields.io/x)](f)\n\n**내 상황에 맞는 자산관리**\n\n"
        "## 서비스 소개\n회의록을 손으로 옮기는 일은 PM의 몫입니다.\n" + "가" * 3000
    )
    body = readme_body(readme)
    assert "서비스 소개" in body and "PM의 몫" in body
    assert "<img" not in body and "img.shields.io" not in body
    assert len(body) <= README_LIMIT == 2000


def test_build_facts_keeps_readme(demo_like_snap):
    assert "레포를 넣으면 데모 영상을 만든다." in build_facts(demo_like_snap).readme


def test_from_json_without_readme_field():  # 이전 run 의 facts.json
    import json
    from dataclasses import asdict

    d = asdict(RepoFacts("n", "s", [], None, None, []))
    d.pop("readme")
    assert RepoFacts.from_json(json.dumps(d)).readme == ""


def test_readme_body_tilde_fence_and_inline_html():  # PR #10 리뷰 (B)
    from app.analyze.facts import readme_body

    body = readme_body(
        '<p align="center">핵심 문장</p>\n<img src="a.png" />\n~~~bash\nnpm i\n~~~\n본문\n'
    )
    assert body == "핵심 문장\n본문"
