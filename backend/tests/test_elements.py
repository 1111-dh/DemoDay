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
