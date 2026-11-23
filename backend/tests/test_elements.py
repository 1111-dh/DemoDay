from app.analyze.elements import Element, extract_elements


def test_extract_elements_literal_only():
    src = """
    <div>
      <button className="x">검색</button>
      <button>{t("save")}</button>
      <Link href="/about">소개</Link>
      <a href="https://x.dev">  외부   링크 </a>
      <input name="q" type="text" />
      <input placeholder="이메일" />
      <input value={v} />
    </div>
    """
    assert extract_elements(src) == [
        Element("button", "검색", "text=검색"),
        Element("link", "소개", "text=소개"),
        Element("input", "q", "input[name=q]"),
        Element("input", "이메일", 'input[placeholder="이메일"]'),
    ]


def test_aria_label_selector():
    src = '<button aria-label="메뉴 열기"><Icon /></button>'
    assert extract_elements(src) == [Element("button", "메뉴 열기", '[aria-label="메뉴 열기"]')]


def test_extract_elements_limit_and_dedupe():
    src = "".join(f"<button>버튼{i}</button><button>버튼{i}</button>" for i in range(30))
    out = extract_elements(src, limit=15)
    assert len(out) == 15
    assert len({e.selector for e in out}) == 15


def test_skips_too_long_text():
    assert extract_elements(f"<button>{'가' * 31}</button>") == []


def test_arrow_function_handlers_keep_elements():  # 리뷰 #1
    src = """
    <button onClick={() => setOpen(true)}>열기</button>
    <button onClick={() => go()} aria-label="닫기">X</button>
    <input onChange={(e) => setQ(e.target.value)} name="q" />
    <Link href="/about" onClick={() => track()}>소개</Link>
    """
    assert [e.selector for e in extract_elements(src)] == [
        "text=열기",
        '[aria-label="닫기"]',
        "input[name=q]",
        "text=소개",
    ]


def test_data_attribute_is_not_name():  # 리뷰 #9
    src = '<input data-name="field" placeholder="검색어" />'
    assert [e.selector for e in extract_elements(src)] == ['input[placeholder="검색어"]']


def test_html_entities_decoded():
    assert [e.selector for e in extract_elements("<button>&nbsp;Edit&amp;Save</button>")] == [
        "text=Edit&Save"
    ]


def test_design_system_components():
    src = """
    <form>
      <TextField label="이메일" {...register('email')} />
      <PasswordField label="비밀번호" {...register("password")} />
      <SearchInput placeholder="찾기" />
      <Button type="submit" disabled={isSubmitting}>로그인</Button>
      <GuardedLink to={paths.signup()}>회원가입</GuardedLink>
      <FormErrorPanel message={m} />
      <ButtonGroup><span>무시</span></ButtonGroup>
    </form>
    """
    assert [(e.kind, e.selector) for e in extract_elements(src)] == [
        ("input", "input[name=email]"),
        ("input", "input[name=password]"),
        ("input", 'input[placeholder="찾기"]'),
        ("button", "text=로그인"),
        ("link", "text=회원가입"),
    ]


def test_external_links_are_skipped():  # 데모에서 다른 사이트로 나가는 링크는 누르지 않는다
    src = (
        '<a href="https://vercel.com" aria-label="go to vercel">V</a>'
        '<a href="//twitter.com/x" aria-label="Link to X account">X</a>'
        '<a href="/about" target="_blank">새 탭</a>'
        '<NuxtLink to="https://github.com/nuxt">GitHub</NuxtLink>'
        '<NuxtLink to="/search">검색</NuxtLink>'
        '<a href="/movies">영화</a>'
        '<a :href="links.homepage" aria-label="Link to Homepage" rel="noopener">H</a>'
        '<a href="mailto:a@b.c">메일</a>'
    )
    assert [e.text for e in extract_elements(src)] == ["검색", "영화"]


def test_nav_config_objects_become_links():  # managers-manager shellTabs.ts
    src = """
    export const TABS = [
      { key: 'dashboard', label: '대시보드', icon: 'home', to: paths.dashboard },
      { to: paths.meetings, label: "회의록" },
      { label: '설정', value: 3 },
      { title: '도움말', href: '/help' },
    ]
    """
    assert [(e.kind, e.text, e.selector) for e in extract_elements(src)] == [
        ("link", "대시보드", "text=대시보드"),
        ("link", "회의록", "text=회의록"),
        ("link", "도움말", "text=도움말"),
    ]


def test_translated_text_resolved_with_messages():  # nuxt/movies: 모든 문구가 $t('…')
    msgs = {"Type to search...": "Type to search...", "nav.home": "홈", "Search": "검색"}
    vue = """<template>
      <input v-model="q" :placeholder="$t('Type to search...')">
      <NuxtLink to="/" :title="$t('nav.home')"><div i-ph-house /></NuxtLink>
      <button>{{ $t('Search') }}</button>
      <button>{{ $t('missing.key') }}</button>
    </template>"""
    out = [(e.kind, e.text, e.selector) for e in extract_elements(vue, messages=msgs)]
    assert out == [
        ("input", "Type to search...", 'input[placeholder="Type to search..."]'),
        ("link", "홈", '[title="홈"]'),
        ("button", "검색", "text=검색"),
    ]  # 번역에 없는 키는 지금처럼 버린다


def test_jsx_t_calls_resolved():
    jsx = '<input placeholder={t("search.ph")} /><button>{t("go")}</button>'
    out = [
        e.selector for e in extract_elements(jsx, messages={"search.ph": "검색어", "go": "찾기"})
    ]
    assert out == ['input[placeholder="검색어"]', "text=찾기"]
    assert extract_elements(jsx) == []  # 번역 없으면 예전처럼 아무것도 안 뽑는다
