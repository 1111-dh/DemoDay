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


def test_name_from_html_h1_not_code_comment():  # nuxt/movies README
    from app.analyze.facts import _name_and_summary

    readme = (
        '<p align="center"><img src="a.webp" /></p>\n\n'
        '<h1 align="center">Nuxt Movies with tests</h1>\n<br>\n\n'
        "> Movies app demo built using [Nuxt](https://nuxt.com) and [Vue](https://vuejs.org).\n\n"
        "## Setup\n\n```bash\n# Enable pnpm\ncorepack enable\n```\n"
    )
    name, summary = _name_and_summary(readme, "movies")
    assert name == "Nuxt Movies with tests"
    assert summary == "Movies app demo built using Nuxt and Vue."


def test_markdown_h1_inside_code_fence_is_ignored():
    from app.analyze.facts import _name_and_summary

    name, _ = _name_and_summary("intro text\n\n```sh\n# install\nnpm i\n```\n", "fallback")
    assert name == "fallback"


def test_summary_strips_markdown_emphasis():
    from app.analyze.facts import _name_and_summary

    _, summary = _name_and_summary("# 안정형\n\n**내 상황에 맞는 _안전_ 자산 관리**\n", "x")
    assert summary == "내 상황에 맞는 안전 자산 관리"


def test_summary_keeps_snake_case_and_math():
    from app.analyze.facts import _name_and_summary

    _, summary = _name_and_summary("# A\n\nuse snake_case_names and 2*3*4 math\n", "x")
    assert summary == "use snake_case_names and 2*3*4 math"


def test_dynamic_route_pages_get_elements():  # 클릭으로 들어가는 동적 화면도 요소를 뽑는다
    snap = make_snap(
        {
            "package.json": pkg({"react": "19", "react-router-dom": "7"}),
            "src/App.tsx": (
                'import Home from "./pages/Home";\nimport Item from "./pages/Item";\n'
                '<Routes><Route path="/" element={<Home />} />'
                '<Route path="/items/:id" element={<Item />} /></Routes>'
            ),
            "src/pages/Home.tsx": '<a href="/items/1">첫 상품</a>',
            "src/pages/Item.tsx": "<button>장바구니 담기</button>",
        }
    )
    page = next(p for p in build_facts(snap).pages if p.path == "/items/:id")
    assert page.dynamic and [e.text for e in page.elements] == ["장바구니 담기"]


def test_layout_route_elements_join_child_pages():  # <Route element={<WorkspaceLayout />}>
    snap = make_snap(
        {
            "package.json": pkg({"react": "19", "react-router-dom": "7"}),
            "src/App.tsx": (
                'import Layout from "./Layout";\nimport Dash from "./pages/Dash";\n'
                'import RequireAuth from "./RequireAuth";\n'
                "<Routes><Route element={<RequireAuth />}>"
                '<Route path="w/:id" element={<Layout />}>'
                '<Route path="dashboard" element={<Dash />} />'
                "</Route></Route></Routes>"
            ),
            "src/Layout.tsx": (
                '<nav><a href="meetings">회의록</a><a href="tasks">태스크</a></nav><Outlet />'
            ),
            "src/RequireAuth.tsx": "return <Outlet />",
            "src/pages/Dash.tsx": "<button>전체 보기</button>",
        }
    )
    page = next(p for p in build_facts(snap).pages if p.path == "/w/:id/dashboard")
    assert [e.text for e in page.elements] == ["전체 보기", "회의록", "태스크"]


def test_layout_tabs_from_model_config_and_hooks_skipped():  # AppHeader → ../model/shellTabs
    hooks = {f"src/lib/h{i}.ts": f"export const useH{i} = () => 1" for i in range(14)}
    hook_imports = "".join(f'import {{ useH{i} }} from "./lib/h{i}";\n' for i in range(14))
    snap = make_snap(
        {
            **hooks,
            "package.json": pkg({"react": "19", "react-router-dom": "7"}),
            "src/App.tsx": (
                'import Layout from "./Layout";\nimport Dash from "./pages/Dash";\n'
                '<Routes><Route path="w/:id" element={<Layout />}>'
                '<Route path="dashboard" element={<Dash />} /></Route></Routes>'
            ),
            "src/Layout.tsx": hook_imports
            + 'import { AppHeader } from "./shell/AppHeader";\n<AppHeader />',
            "src/shell/AppHeader.tsx": (
                'import { TABS } from "../model/shellTabs";\n'
                "TABS.map(t => <NavLink to={t.to}>{t.label}</NavLink>)"
            ),
            "src/model/shellTabs.ts": (
                "export const TABS = [{ label: '회의록', to: 'meetings' }, "
                "{ label: '태스크', to: 'tasks' }]"
            ),
            "src/pages/Dash.tsx": "<button>전체 보기</button>",
        }
    )
    page = next(p for p in build_facts(snap).pages if p.path == "/w/:id/dashboard")
    assert [e.text for e in page.elements] == ["전체 보기", "회의록", "태스크"]


def test_title_tagline_is_split_into_name_and_summary():
    """채움 README 제목 '# 채움 — 공실에 맞는 업종 분석'."""
    from app.analyze.facts import _name_and_summary

    readme = "# 채움 — 공실에 맞는 업종 분석\n\n카카오테크 캠퍼스 4기 · 강원대 1팀\n"
    name, summary = _name_and_summary(readme, "x")
    assert name == "채움"
    assert summary == "공실에 맞는 업종 분석. 카카오테크 캠퍼스 4기 · 강원대 1팀"
    assert _name_and_summary("# Foo: fast bar\n", "x") == ("Foo", "fast bar")
    # 하이픈 이름은 그대로
    assert _name_and_summary("# my-app\n\nhello\n", "x") == ("my-app", "hello")


def test_nuxt_i18n_messages_feed_elements():
    from app.analyze.i18n import load_messages

    snap = make_snap(
        {
            "package.json": pkg({"nuxt": "4", "@nuxtjs/i18n": "9"}),
            "nuxt.config.ts": "export default defineNuxtConfig({ i18n: { defaultLocale: 'en' } })",
            "internationalization/en.json": (
                '{"Type to search...": "Type to search...", "nav": {"home": "Home"}}'
            ),
            "internationalization/de-DE.json": '{"Type to search...": "Suchen..."}',
            "app/pages/index.vue": "<template><div /></template>",
            "app/pages/search.vue": (
                "<template><input :placeholder=\"$t('Type to search...')\"></template>"
            ),
        }
    )
    msgs = load_messages(snap)
    assert msgs["Type to search..."] == "Type to search..." and msgs["nav.home"] == "Home"
    facts = build_facts(snap)
    search = next(p for p in facts.pages if p.path == "/search")
    assert [e.selector for e in search.elements] == ['input[placeholder="Type to search..."]']


def test_locale_pick_prefers_default_then_en_then_ko():
    from app.analyze.i18n import load_messages

    ko_only = make_snap(
        {"src/locales/ko.json": '{"a": "가"}', "src/locales/ja.json": '{"a": "あ"}'}
    )
    assert load_messages(ko_only) == {"a": "가"}
    no_locale = make_snap({"package.json": pkg({"next": "15"})})
    assert load_messages(no_locale) == {}
