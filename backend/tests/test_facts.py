from app.analyze.facts import RepoFacts, build_facts
from app.analyze.routes import find_app_root, react_routes
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
    snap = make_snap({"package.json": pkg({"vue": "3"})})
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
