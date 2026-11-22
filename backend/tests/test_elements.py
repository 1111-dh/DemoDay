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
        Element("link", "외부 링크", "text=외부 링크"),
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
