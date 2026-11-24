import httpx

from app.logo import candidates, fetch_logo

HTML = """<html><head>
<link rel="icon" href="/favicon-32.png" sizes="32x32">
<link rel="apple-touch-icon" href="/apple.png" sizes="180x180">
<link rel="mask-icon" href="/mask.svg">
</head></html>"""


def test_candidates_prefer_apple_touch_icon_then_favicon():
    urls = candidates(HTML, "https://a.dev/")
    assert urls == [
        "https://a.dev/apple.png",
        "https://a.dev/favicon-32.png",
        "https://a.dev/favicon.ico",
    ]


def test_fetch_logo_saves_first_image_and_survives_failures(tmp_path):
    def handler(req):
        if req.url.path == "/":
            return httpx.Response(200, text=HTML)
        if req.url.path == "/apple.png":
            return httpx.Response(404)
        if req.url.path == "/favicon-32.png":
            return httpx.Response(200, content=b"png", headers={"content-type": "image/png"})
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    out = fetch_logo("https://a.dev/", tmp_path, client)
    assert out == tmp_path / "logo.png" and out.read_bytes() == b"png"

    dead = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    assert fetch_logo("https://b.dev/", tmp_path / "x", dead) is None


def test_site_name_prefers_meta_then_shortest_title_part():
    from app.logo import site_name

    assert site_name('<meta property="og:site_name" content="CodePes">') == "CodePes"
    assert site_name("<title>PM·CS 학습 길라잡이 · CS 길라잡이</title>") == "CS 길라잡이"
    assert site_name("<title>Nuxt Movies</title>") == "Nuxt Movies"
    assert site_name("<title>" + "가" * 40 + "</title>") is None
