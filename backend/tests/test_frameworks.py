"""React·Next 외 프레임워크 라우트 추출 (Vue Router · Nuxt · SvelteKit · Flutter) + React lazy."""

from app.analyze.elements import extract_elements
from app.analyze.facts import build_facts
from app.analyze.routes import find_app_root, routes_for
from tests.conftest import make_snap, pkg


def paths_files(snap):
    return [(r.path, r.dynamic, r.file) for r in routes_for(snap, find_app_root(snap))]


# ── 1. Vue Router · Nuxt ─────────────────────────────────────────────

VUE_ROUTER = """
import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: HomeView },
    { path: '/about', component: () => import('@/views/AboutView.vue') },
    {
      path: '/settings',
      component: () => import('../views/SettingsLayout.vue'),
      children: [
        { path: 'profile', component: () => import('../views/ProfileView.vue') },
        { path: ':tab', component: () => import('../views/TabView.vue') },
      ],
    },
    { path: '/old', redirect: '/' },
    { path: '/:pathMatch(.*)*', component: () => import('../views/NotFound.vue') },
  ],
})
export default router
"""


def test_vue_app_root():
    snap = make_snap({"package.json": pkg({"vue": "3", "vue-router": "4"})})
    assert find_app_root(snap).framework == "vue"


def test_vue_router_nested_objects_and_lazy_components():
    snap = make_snap(
        {"package.json": pkg({"vue": "3"}), "src/router/index.ts": VUE_ROUTER},
        extra_paths=[
            "src/views/HomeView.vue",
            "src/views/AboutView.vue",
            "src/views/SettingsLayout.vue",
            "src/views/ProfileView.vue",
            "src/views/TabView.vue",
            "src/views/NotFound.vue",
        ],
    )
    assert paths_files(snap) == [
        ("/", False, "src/views/HomeView.vue"),
        ("/:pathMatch(.*)*", True, "src/views/NotFound.vue"),
        ("/about", False, "src/views/AboutView.vue"),
        ("/settings", False, "src/views/SettingsLayout.vue"),
        ("/settings/:tab", True, "src/views/TabView.vue"),
        ("/settings/profile", False, "src/views/ProfileView.vue"),
    ]


def test_react_object_routes_join_children():
    src = """
    const router = createBrowserRouter([
      { path: "/", element: <Root />, children: [
        { index: true, element: <Home /> },
        { path: "team", element: <Team /> },
      ]},
    ]);
    """
    snap = make_snap({"package.json": pkg({"react": "18"}), "src/main.tsx": src})
    assert [p for p, _, _ in paths_files(snap)] == ["/", "/team"]


def test_nuxt_pages_routes():
    snap = make_snap(
        {"package.json": pkg({"nuxt": "3", "vue": "3"})},
        extra_paths=[
            "pages/index.vue",
            "pages/about.vue",
            "pages/posts/[id].vue",
            "pages/users/_id.vue",
            "pages/(marketing)/pricing.vue",
            "components/Header.vue",
        ],
    )
    assert find_app_root(snap).framework == "nuxt"
    assert paths_files(snap) == [
        ("/", False, "pages/index.vue"),
        ("/about", False, "pages/about.vue"),
        ("/pricing", False, "pages/(marketing)/pricing.vue"),
        ("/posts/[id]", True, "pages/posts/[id].vue"),
        ("/users/_id", True, "pages/users/_id.vue"),
    ]


def test_nuxt4_app_pages_dir():
    snap = make_snap(
        {"package.json": pkg({"nuxt": "4"})}, extra_paths=["app/pages/index.vue", "app/app.vue"]
    )
    assert [p for p, _, _ in paths_files(snap)] == ["/"]


def test_vue_template_elements():
    src = """
    <template>
      <button @click="open()">열기</button>
      <button @click="n > 0 && go()">이동</button>
      <router-link to="/about">소개</router-link>
      <NuxtLink to="/pricing">가격</NuxtLink>
      <input v-model="q" placeholder="검색" />
      <button :aria-label="t('x')">{{ t('y') }}</button>
    </template>
    """
    assert [e.selector for e in extract_elements(src)] == [
        "text=열기",
        "text=이동",
        "text=소개",
        "text=가격",
        'input[placeholder="검색"]',
    ]


def test_vue_facts_reads_view_elements_on_demand():
    loaded = {"src/views/HomeView.vue": "<template><button>시작</button></template>"}
    snap = make_snap(
        {"package.json": pkg({"vue": "3"}), "src/router/index.ts": VUE_ROUTER},
        extra_paths=["src/views/HomeView.vue"],
        loader=loaded.get,
    )
    home = build_facts(snap).pages[0]
    assert (home.path, [e.selector for e in home.elements]) == ("/", ["text=시작"])


# ── 2. React lazy import ─────────────────────────────────────────────


def test_react_lazy_import_resolves_component():
    src = """
    import { lazy } from 'react'
    const Dash = lazy(() => import('./pages/Dash'))
    const Team = React.lazy(async () => import('./pages/Team'))
    export default () => (<Routes>
      <Route path="/dash" element={<Dash />} />
      <Route path="/team" element={<Suspense><Team /></Suspense>} />
      <Route path="/lazy" lazy={() => import('./pages/Lazy')} />
    </Routes>)
    """
    snap = make_snap(
        {"package.json": pkg({"react": "18"}), "src/App.tsx": src},
        extra_paths=["src/pages/Dash.tsx", "src/pages/Team.tsx", "src/pages/Lazy.tsx"],
    )
    assert [(p, f) for p, _, f in paths_files(snap)] == [
        ("/dash", "src/pages/Dash.tsx"),
        ("/lazy", "src/pages/Lazy.tsx"),
        ("/team", "src/pages/Team.tsx"),
    ]


# kyungpook-3 처럼: 감싼 lazy + element={screen(page)} + FSD 재export(index.ts) → 위젯
FSD = {
    "package.json": pkg({"react": "19"}),
    "src/app/router/routes.tsx": """
      const dashboardPage = lazyPage(() => import('@/pages/dashboard').then((m) => m.DashboardPage))
      export const appRoutes = (<Route path="/" element={<RootLayout />}>
        <Route path="dashboard" element={screen(dashboardPage)} />
      </Route>)
    """,
    "src/pages/dashboard/index.ts": "export { DashboardPage } from './ui/DashboardPage'",
    "src/pages/dashboard/ui/DashboardPage.tsx": """
      import { useWorkspace } from '@/entities/workspace/api/useWorkspace'
      import { Dashboard } from '@/widgets/dashboard'
      export function DashboardPage() { return <Dashboard /> }
    """,
    "src/widgets/dashboard/index.ts": "export * from './ui/Dashboard'",
    "src/widgets/dashboard/ui/Dashboard.tsx": (
        "<section><button onClick={() => add()}>새 태스크</button>"
        '<input placeholder="검색" onChange={(e) => s(e)} /></section>'
    ),
    "src/entities/workspace/api/useWorkspace.ts": "<button>여기는 따라가면 안 됨</button>",
}


def test_wrapped_lazy_and_reexports_reach_widget_elements():
    snap = make_snap(
        {
            "src/app/router/routes.tsx": FSD["src/app/router/routes.tsx"],
            "package.json": FSD["package.json"],
        },
        extra_paths=list(FSD),
        loader=FSD.get,
    )
    dash = next(p for p in build_facts(snap).pages if p.path == "/dashboard")
    assert dash.file == "src/pages/dashboard/index.ts"
    assert [e.selector for e in dash.elements] == ["text=새 태스크", 'input[placeholder="검색"]']


def test_index_route_wins_over_layout_on_same_path():
    src = """
    import Root from './layouts/Root'
    import Landing from './pages/Landing'
    export const r = (<Route path="/" element={<Root />}>
      <Route element={<Guard />}><Route index element={<Landing />} /></Route>
    </Route>)
    """
    snap = make_snap(
        {"package.json": pkg({"react": "19"}), "src/routes.tsx": src},
        extra_paths=["src/layouts/Root.tsx", "src/pages/Landing.tsx"],
    )
    assert paths_files(snap) == [("/", False, "src/pages/Landing.tsx")]


def test_barrel_follows_only_imported_names():
    files = {
        "package.json": pkg({"react": "19"}),
        "src/routes.tsx": """
          import { SignupPage } from './pages/signup/SignupPage'
          export const r = <Route path="/signup" element={<SignupPage />} />
        """,
        "src/pages/signup/SignupPage.tsx": (
            "import { SignupForm, type X } from '@/features/auth'\n"
            "export const SignupPage = () => <SignupForm />"
        ),
        "src/features/auth/index.ts": (
            "export { LoginForm } from './ui/LoginForm'\n"
            "export { SignupForm as SignupForm } from './ui/SignupForm'\n"
            "export * from './ui/shared'\n"
            "export type { X } from './model/types'"
        ),
        "src/features/auth/ui/LoginForm.tsx": "<Button>로그인</Button>",
        "src/features/auth/ui/SignupForm.tsx": "<Button>가입하기</Button>",
        "src/features/auth/ui/shared.tsx": "<Link to='/'>처음으로</Link>",
    }
    snap = make_snap(files, loader=files.get)
    page = next(p for p in build_facts(snap).pages if p.path == "/signup")
    assert [e.selector for e in page.elements] == ["text=가입하기", "text=처음으로"]


# ── 3. SvelteKit · Flutter ──────────────────────────────────────────


def test_sveltekit_routes():
    snap = make_snap(
        {"package.json": pkg(dev={"@sveltejs/kit": "2", "svelte": "5"})},
        extra_paths=[
            "src/routes/+page.svelte",
            "src/routes/+layout.svelte",
            "src/routes/about/+page.svelte",
            "src/routes/(app)/dashboard/+page.svelte",
            "src/routes/blog/[slug]/+page.svelte",
            "src/routes/api/items/+server.ts",
        ],
    )
    assert find_app_root(snap).framework == "sveltekit"
    assert paths_files(snap) == [
        ("/", False, "src/routes/+page.svelte"),
        ("/about", False, "src/routes/about/+page.svelte"),
        ("/dashboard", False, "src/routes/(app)/dashboard/+page.svelte"),
        ("/blog/[slug]", True, "src/routes/blog/[slug]/+page.svelte"),
    ]


def test_svelte_elements():
    src = """
    <button on:click={() => count++}>더하기</button>
    <a href="/about">소개</a>
    <input bind:value={q} placeholder="검색" />
    """
    assert [e.selector for e in extract_elements(src)] == [
        "text=더하기",
        "text=소개",
        'input[placeholder="검색"]',
    ]


PUBSPEC = """
name: safe_app
dependencies:
  flutter:
    sdk: flutter
  go_router: ^14.0.0
  firebase_core: ^3.0.0
dev_dependencies:
  flutter_test:
    sdk: flutter
"""

GO_ROUTER = """
import 'package:go_router/go_router.dart';
class AppRoutes {
  static const home = '/';
  static const login = '/login';
  static const result = '/result';
}
final appRouter = GoRouter(
  routes: [
    GoRoute(path: AppRoutes.home, builder: (c, s) => const HomeScreen(), routes: [
      GoRoute(path: 'detail/:id', builder: (c, s) => const DetailScreen()),
      GoRoute(path: 'settings', builder: (c, s) => const SettingsScreen()),
    ]),
    ShellRoute(builder: (c, s, child) => Shell(child: child), routes: [
      GoRoute(path: '/profile', builder: (c, s) => const ProfileScreen()),
    ]),
    GoRoute(path: AppRoutes.result, builder: (c, s) => const ResultScreen()),
  ],
);
"""


def flutter_snap(main_dart: str):
    files = {
        "frontend/pubspec.yaml": PUBSPEC,
        "frontend/lib/router/app_router.dart": GO_ROUTER,
        "frontend/lib/main.dart": main_dart,
    }
    return make_snap(files, extra_paths=["frontend/lib/screens/home.dart"])


def test_flutter_go_router_hash_urls_by_default():
    snap = flutter_snap("void main() { runApp(const App()); }")
    root = find_app_root(snap)
    assert (root.dir, root.framework) == ("frontend", "flutter")
    assert [(p, d) for p, d, _ in paths_files(snap)] == [
        ("/", False),
        ("/#/profile", False),
        ("/#/result", False),
        ("/#/settings", False),
        ("/#/detail/:id", True),
    ]
    facts = build_facts(snap)
    assert "go_router" in facts.stack and "flutter" not in facts.stack
    assert all(p.elements == [] for p in facts.pages)  # 화면 파일이 없으면 요소도 없다


def test_flutter_path_url_strategy():
    snap = flutter_snap("void main() { usePathUrlStrategy(); runApp(const App()); }")
    assert [p for p, _, _ in paths_files(snap)][:3] == ["/", "/profile", "/result"]


def test_flutter_material_routes_map():
    files = {
        "pubspec.yaml": PUBSPEC,
        "lib/main.dart": """
          void main() { setUrlStrategy(PathUrlStrategy()); runApp(MaterialApp(
            routes: {
              '/': (context) => const Home(),
              '/about': (context) => const About(),
            },
          )); }
        """,
    }
    assert [p for p, _, _ in paths_files(make_snap(files))] == ["/", "/about"]


def test_nuxt_auto_imported_components():
    files = {
        "package.json": pkg({"nuxt": "4"}),
        "app/pages/index.vue": (
            "<template><MediaHero /><lazy-carousel-base /><IconNuxt /></template>"
        ),
        "app/components/media/Hero.vue": "<template><button>재생</button></template>",
        "app/components/carousel/Base.vue": (
            '<template><NuxtLink to="/x">더 보기</NuxtLink></template>'
        ),
        "app/components/icon/IconNuxt.vue": "<template><a href='/'>로고</a></template>",
    }
    snap = make_snap(files, loader=files.get)
    home = build_facts(snap).pages[0]
    assert [e.selector for e in home.elements] == ["text=재생", "text=더 보기", "text=로고"]


# ── 3-b. Flutter 요소 (semantics 모드에서 role 로 클릭) ─────────────────


def test_dart_elements():
    from app.analyze.flutter import dart_elements

    src = """
    Column(children: [
      ElevatedButton(onPressed: () => go(), child: const Text('다음')),
      TextButton.icon(onPressed: skip, icon: Icon(Icons.skip), label: const Text("건너뛰기")),
      IconButton(tooltip: '뒤로', icon: const Icon(Icons.arrow_back), onPressed: back),
      PrimaryButton(label: '시작하기', onTap: start),
      _SocialButton(label: '카카오로 계속하기', icon: Image.asset(a), onPressed: k),
      ElevatedButton(onPressed: ok, child: Text(l10n.ok)),
      TextField(decoration: InputDecoration(labelText: '이메일', hintText: 'a@b.c')),
      TextFormField(decoration: const InputDecoration(hintText: '비밀번호')),
      const Text('그냥 텍스트'),
    ])
    """
    assert [(e.kind, e.selector) for e in dart_elements(src)] == [
        ("button", 'role=button[name="다음"]'),
        ("button", 'role=button[name="건너뛰기"]'),
        ("button", 'role=button[name="뒤로"]'),
        ("button", 'role=button[name="시작하기"]'),
        ("button", 'role=button[name="카카오로 계속하기"]'),
        ("input", 'role=textbox[name="이메일"]'),
        ("input", 'role=textbox[name="비밀번호"]'),
    ]


def test_flutter_routes_link_screen_files_and_elements():
    pubspec = PUBSPEC.replace("name: safe_app", "name: safe_app")
    files = {
        "frontend/pubspec.yaml": pubspec,
        "frontend/lib/main.dart": "void main() { usePathUrlStrategy(); runApp(App()); }",
        "frontend/lib/router/app_router.dart": """
          import 'package:go_router/go_router.dart';
          import 'package:safe_app/screens/home/home_screen.dart';
          import '../screens/login/login_screen.dart';
          final r = GoRouter(routes: [
            GoRoute(path: '/', builder: (context, state) => const HomeScreen()),
            GoRoute(path: '/login', pageBuilder: (c, s) {
              return NoTransitionPage(child: LoginScreen());
            }),
          ]);
        """,
        "frontend/lib/screens/home/home_screen.dart": """
          import 'package:flutter/material.dart';
          import '../../widgets/menu_card.dart';
          import '../../providers/user_provider.dart';
          class HomeScreen extends StatelessWidget {
            Widget build(BuildContext context) => ElevatedButton(onPressed: f, child: Text('시작'));
          }
        """,
        "frontend/lib/widgets/menu_card.dart": "FilledButton(onPressed: f, child: Text('메뉴'))",
        "frontend/lib/providers/user_provider.dart": "TextButton(child: Text('따라가면 안 됨'))",
        "frontend/lib/screens/login/login_screen.dart": "class LoginScreen {}",
    }
    snap = make_snap(
        {k: files[k] for k in ("frontend/pubspec.yaml", "frontend/lib/router/app_router.dart")},
        extra_paths=list(files),
        loader=files.get,
    )
    home = build_facts(snap).pages[0]
    assert (home.path, home.file) == ("/", "frontend/lib/screens/home/home_screen.dart")
    assert [e.selector for e in home.elements] == [
        'role=button[name="시작"]',
        'role=button[name="메뉴"]',
    ]
    login = routes_for(snap, find_app_root(snap))[1]
    assert (login.path, login.file) == ("/login", "frontend/lib/screens/login/login_screen.dart")


def test_flutter_does_not_follow_other_screens_and_skips_numeric_names():
    files = {
        "pubspec.yaml": PUBSPEC,
        "lib/main.dart": "void main() { usePathUrlStrategy(); }",
        "lib/router.dart": """
          import 'screens/a_screen.dart';
          import 'screens/b_screen.dart';
          final r = GoRouter(routes: [
            GoRoute(path: '/', builder: (c, s) => const AScreen()),
            GoRoute(path: '/b', builder: (c, s) => const BScreen()),
          ]);
        """,
        "lib/screens/a_screen.dart": """
          import 'b_screen.dart';
          class AScreen { build() => Column(children: [
            ElevatedButton(onPressed: () => push(BScreen()), child: Text('B로 가기')),
            TextField(decoration: InputDecoration(hintText: '0')),
          ]); }
        """,
        "lib/screens/b_screen.dart": "class BScreen { x() => TextButton(child: Text('B 버튼')); }",
    }
    snap = make_snap(
        {k: files[k] for k in ("pubspec.yaml", "lib/router.dart")},
        extra_paths=list(files),
        loader=files.get,
    )
    a = build_facts(snap).pages[0]
    assert [e.selector for e in a.elements] == ['role=button[name="B로 가기"]']


def test_react_page_does_not_follow_other_route_pages():
    files = {
        "package.json": pkg({"react": "19"}),
        "src/App.tsx": """
          import Home from './pages/Home'
          import About from './pages/About'
          export default () => (<Routes>
            <Route path="/" element={<Home />} /><Route path="/about" element={<About />} />
          </Routes>)
        """,
        "src/pages/Home.tsx": "import About from './About'\n<button>홈 버튼</button>",
        "src/pages/About.tsx": "<button>소개 버튼</button>",
    }
    snap = make_snap(files, loader=files.get)
    home = build_facts(snap).pages[0]
    assert [e.selector for e in home.elements] == ["text=홈 버튼"]
