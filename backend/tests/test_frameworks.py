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
