from app.analyze.elements import Element
from app.analyze.facts import PageFacts, RepoFacts
from app.contracts import schema_errors
from app.login import login_steps


def _facts(*pages: PageFacts) -> RepoFacts:
    return RepoFacts("n", "s", [], "", "next-app", list(pages))


def test_login_steps_from_form():
    page = PageFacts(
        "/login",
        False,
        "f",
        [
            Element("input", "이메일", 'input[placeholder="이메일"]'),
            Element("input", "비밀번호", 'input[placeholder="비밀번호"]'),
            Element("button", "로그인", "text=로그인"),
        ],
    )
    auth = login_steps(_facts(PageFacts("/", False, "h", []), page), "u", "p")
    assert auth == {
        "steps": [
            {"id": 1, "action": "goto", "path": "/login", "caption": "로그인"},
            {
                "id": 2,
                "action": "type",
                "selector": 'input[placeholder="이메일"]',
                "value": "u",
                "caption": "아이디",
            },
            {
                "id": 3,
                "action": "type",
                "selector": 'input[placeholder="비밀번호"]',
                "value": "p",
                "caption": "비밀번호",
            },
            {"id": 4, "action": "click", "selector": "text=로그인", "caption": "로그인"},
        ]
    }
    probe = {"baseUrl": "https://x.dev", "auth": auth, "steps": [auth["steps"][0]]}
    assert schema_errors("scenario", probe) == []


def test_login_steps_flutter_hash_route():
    page = PageFacts(
        "/#/signin",
        False,
        "f",
        [
            Element("input", "Password", 'role=textbox[name="Password"]'),
            Element("input", "아이디", 'role=textbox[name="아이디"]'),
            Element("button", "Sign in", 'role=button[name="Sign in"]'),
        ],
    )
    steps = login_steps(_facts(page), "u", "p")["steps"]
    assert steps[0]["path"] == "/#/signin"
    assert (steps[1]["selector"], steps[1]["value"]) == ('role=textbox[name="아이디"]', "u")
    assert (steps[2]["selector"], steps[2]["value"]) == ('role=textbox[name="Password"]', "p")


def test_login_steps_none_for_social_only():
    page = PageFacts(
        "/#/login",
        False,
        "f",
        [
            Element("button", "카카오로 계속하기", 'role=button[name="카카오로 계속하기"]'),
            Element("button", "구글로 계속하기", 'role=button[name="구글로 계속하기"]'),
        ],
    )
    assert login_steps(_facts(page), "u", "p") is None
