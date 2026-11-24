"""scenario + capture + facts → scene.json.

장면 구성은 결정적으로 조립하고, LLM(SceneCopy)은 제목·자막·장면 비중만 맡는다.
"""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path

from pydantic import BaseModel

from app.analyze.facts import RepoFacts
from app.architecture import infer_architecture
from app.contracts import schema_errors
from app.contracts.scene import Icon
from app.llm import LLM, generate
from app.scenario import with_reference
from app.vision import Describer

FPS = 30
TITLE_SEC = 4.5  # 오프닝 — 글자가 하나씩 올라오는 모션이 끝나고 읽을 시간
SCREEN_SEC = 4
FALLBACK_SEC = 2
ARCH_SEC = 4
ZOOM = 1.6
W_MIN, W_MAX = 0.5, 2.0
MAX_CAPTION = 30
CARD_MIN, CARD_MAX = 3.0, 5.0  # 문제·정리 카드 — 글자 수만큼 읽을 시간 (11/24 너무 빠르다는 피드백)
MAX_CLIP_SEC = 9  # 녹화 구간이 길어도 장면은 이 이상 늘리지 않는다
SCREEN_MIN = 4.5  # 화면 장면 최소 길이 — 짧은 녹화는 느리게 재생하고 카메라가 움직인다
FILL_MAX = 7.0  # 요청 길이를 채울 때 화면 장면 하나의 상한 (더 길면 정지 화면이 늘어진다)
LOGIN_SEC = 2
LOGIN_CAPTION = "테스트 계정으로 로그인"
MAX_HIGHLIGHTS = 2
MAX_CARD = 28  # 문제·정리 카드는 큰 글씨 장 구분 카드로 그려진다 — 두 줄 이내
SYSTEM = (Path(__file__).parent / "prompts" / "scene.md").read_text()


MAX_POINT = 16  # points 항목 — 모션 그래픽용 짧은 키워드(프롬프트는 12자, 여유 4자)
MAX_SITUATION = 22  # 문제 항목 — 사람이 겪는 상황 한 문장(프롬프트는 18자, 여유 4자)
# 해결 장면 기본: 3초 + 항목당 1초 / 문제 장면 기본: 제목 1.4초 + 상황당 3초 (render ProblemStory)
POINTS_BASE, POINT_SEC = 3.0, 1.0
STORY_BASE, STORY_SEC = 1.4, 3.0
# LLM이 problem_sec·solution_sec로 정하는 길이의 항목당 범위(초)
STORY_RANGE, POINTS_RANGE = (2.4, 4.5), (0.8, 2.0)


class PointDraft(BaseModel):
    icon: Icon
    text: str


class SceneCopy(BaseModel):
    title: str
    subtitle: str
    captions: list[str]
    weights: list[float]
    highlights: list[list[str]] = []  # 화면별 caption 에서 그대로 따온 강조어 (비우면 없음)
    problem: str = ""  # README에 나온 문제 한 문장 (없으면 빈 문자열 → 카드 없음)
    problem_points: list[PointDraft] = []  # 불편 2~3개 → points 장면 (1개 이하면 문제 카드)
    solution: str = ""  # 해결 한 줄 제목
    solution_points: list[PointDraft] = []  # 핵심 기능 2~4개 → points 장면 (없으면 생략)
    closing: str = ""  # 서비스 가치 한 문장 (없으면 카드 없음)
    problem_sec: float = 0  # 문제 장면 길이(초) — LLM이 상황 무게를 보고 정한다(0이면 기본값)
    solution_sec: float = 0  # 해결 장면 길이(초)


def _clamp(w: float) -> float:
    return min(W_MAX, max(W_MIN, w))


def keep_shots(shots: list[dict]) -> list[dict]:
    """실패(fallback)한 단계는 뺀다 — 일어나지 않은 동작을 자막으로 말하게 된다.

    전부 실패했으면 첫 화면 하나만 남긴다(영상은 나와야 한다).
    """
    ok = [shot for shot in shots if shot.get("status", "ok") != "fallback"]
    return ok or shots[:1]


def _points(heading: str, points: list[PointDraft], kicker: str, want: float = 0) -> dict | None:
    """문제·해결 장면. 항목이 2개 미만이면 None (호출부가 카드로 대신).

    want(초)는 LLM이 내용을 보고 정한 길이 — 항목 수에 맞는 범위로 자르고, 0이면 기본값.
    """
    items = [{"icon": str(p.icon), "text": p.text.strip()} for p in points if p.text.strip()][:4]
    if len(items) < 2:
        return None
    problem = kicker == "문제"
    base, each = (STORY_BASE, STORY_SEC) if problem else (POINTS_BASE, POINT_SEC)
    lo, hi = STORY_RANGE if problem else POINTS_RANGE
    n = len(items)
    least, most = base + lo * n, base + hi * n
    sec = round(min(most, max(least, want)) if want > 0 else base + each * n, 2)
    return {
        "type": "points",
        "durationSec": sec,
        "kicker": kicker,
        "heading": heading.strip(),
        "items": items,
    }


ENDING_MIN = 3.5  # 엔딩 — 로고·이름이 뜬 뒤 문장을 읽을 시간
BRIDGE_SEC = 3.2  # "하지만 …을 사용한다면?" — 문제에서 시연으로 넘어가는 한 박자
BRIDGE_KICKER = "하지만"


def _object_particle(name: str) -> str:
    """이름 뒤 목적격 조사: 받침 있는 한글로 끝나면 '을', 아니면 '를'(영문 이름 포함)."""
    last = name.strip()[-1:] or "x"
    if "가" <= last <= "힣":
        return "을" if (ord(last) - 0xAC00) % 28 else "를"
    return "를"


def bridge(name: str) -> dict:
    name = name.strip()
    text = f"{name}{_object_particle(name)} 사용한다면?"
    return {"type": "title", "durationSec": BRIDGE_SEC, "kicker": BRIDGE_KICKER, "text": text}


def _read_sec(text: str) -> float:
    """한 줄 문장을 읽을 시간: 1.8초 + 글자당 0.1초 (3~5초)."""
    return round(min(CARD_MAX, max(CARD_MIN, 1.8 + 0.1 * len(text))), 2)


def _card(text: str, kicker: str) -> dict:
    return {"type": "title", "durationSec": _read_sec(text), "text": text, "kicker": kicker}


def _highlight(caption: str, words: list[str]) -> list[str]:
    """caption 에 실제로 있는 단어만. 중복·더 긴 단어에 포함된 단어는 뺀다(긴 쪽 우선)."""
    found = sorted({w.strip() for w in words if w.strip() and w.strip() in caption}, key=len)
    kept = [w for i, w in enumerate(found) if not any(w in longer for longer in found[i + 1 :])]
    return sorted(kept, key=caption.index)[:MAX_HIGHLIGHTS]


def fill(doc: dict, total_sec: float) -> dict:
    """내용이 요청 길이보다 짧으면 녹화가 있는 화면 장면만 늘린다(장면당 FILL_MAX초까지).

    카드·모션 그래픽은 늘리면 늘어지므로 그대로 두고, 실제 화면은 카메라가 천천히 움직여 버틴다.
    """
    scenes = doc["scenes"]
    screens = [sc for sc in scenes if sc["type"] == "screen" and sc.get("video")]
    gap = total_sec - sum(sc["durationSec"] for sc in scenes)
    while gap > 0.05 and (room := [sc for sc in screens if sc["durationSec"] < FILL_MAX]):
        add = min(gap / len(room), min(FILL_MAX - sc["durationSec"] for sc in room))
        for sc in room:
            sc["durationSec"] = round(sc["durationSec"] + add, 2)
        gap -= add * len(room)
    total = round(sum(sc["durationSec"] for sc in scenes), 2)
    return {**doc, "totalSec": min(total_sec, total)}


def assemble(
    scenario: dict,
    shots: list[dict],
    facts: RepoFacts,
    total_sec: float,
    include_architecture: bool,
    copy: SceneCopy | None,
    *,
    video: str | None = None,
    login_images: list[str] | None = None,
    service_name: str | None = None,
) -> dict:
    """video = capture.video (녹화 파일), login_images = capture.login.images (입력칸 가림)."""
    step_caption = {s["id"]: s.get("caption", "") for s in scenario["steps"]}
    title = {"type": "title", "durationSec": TITLE_SEC, "text": (copy and copy.title) or facts.name}
    subtitle = copy.subtitle if copy else facts.summary
    if subtitle:
        title["subtitle"] = subtitle
    # 영상 흐름(11/24): 문제 상황 → "하지만 {서비스}를 사용한다면?" → 시연
    # → {서비스}가 문제를 해결한다는 마무리.
    # 제목 슬라이드는 문제를 못 찾았을 때만 연다. 해결은 카드 대신 시연으로 바로 보여 준다.
    scenes: list[dict] = []
    if copy and copy.problem.strip():
        problem = _points(copy.problem, copy.problem_points, "문제", copy.problem_sec)
        scenes.append(problem or _card(copy.problem.strip(), "문제"))
        scenes.append(bridge(service_name or title["text"]))
    else:
        scenes.append(title)
    for j, image in enumerate(login_images or []):  # 문제 → 연결 → (로그인) → 시연
        login: dict = {"type": "screen", "durationSec": LOGIN_SEC, "image": image}
        if j == len(login_images) - 1:
            login["caption"] = LOGIN_CAPTION
        scenes.append(login)

    # 강조 개수가 shot 수와 다르면 강조만 버린다 (자막·카드는 살린다)
    highlights = copy.highlights if copy and len(copy.highlights) == len(shots) else None
    for i, shot in enumerate(shots):
        draft = step_caption.get(shot["stepId"], "")
        caption = copy.captions[i] if copy and i < len(copy.captions) else draft
        screen: dict = {"type": "screen", "image": shot["image"]}
        if shot.get("status", "ok") == "fallback":
            screen["durationSec"] = FALLBACK_SEC
        elif video and (clip := shot.get("clip")) and clip["endMs"] > clip["startMs"]:
            # weight 대신 녹화 구간 길이를 비중으로 쓴다. 전체 길이는 렌더가 totalSec 에 맞춰
            # 늘이고 줄이며, 구간과 다르면 재생 속도(0.5~2배)·마지막 프레임 정지로 맞춘다
            sec = (clip["endMs"] - clip["startMs"]) / 1000
            weight = copy.weights[i] if copy and i < len(copy.weights) else 1
            least = SCREEN_MIN * min(1.4, max(0.9, weight))  # 핵심 화면은 조금 더 오래
            screen["durationSec"] = round(min(MAX_CLIP_SEC, max(least, sec)), 2)
            screen["video"] = {"src": video, "startMs": clip["startMs"], "endMs": clip["endMs"]}
        else:
            weight = copy.weights[i] if copy and i < len(copy.weights) else 1
            screen["durationSec"] = max(SCREEN_MIN, SCREEN_SEC * _clamp(weight))
        if shot.get("status", "ok") != "fallback":
            if click := shot.get("click"):
                screen["zoom"] = {"x": click["x"], "y": click["y"], "scale": ZOOM}
                screen["cursor"] = {"x": click["x"], "y": click["y"]}
            elif focus := shot.get("focus"):  # 클릭이 없는 화면도 설명하는 곳으로 천천히 다가간다
                screen["zoom"] = {**focus, "scale": FOCUS_ZOOM}
        if caption:
            screen["caption"] = caption
            if highlights and (words := _highlight(caption, highlights[i])):
                screen["highlight"] = words
        scenes.append(screen)

    if copy and copy.closing.strip():
        # 엔딩: [로고][서비스 이름] + 아래 "이제, ~하세요" 한 문장(11/24 피드백).
        # 이름은 subtitle 로 — 렌더가 엔딩 배치로 그린다. 웹 편집기는 text(문장)를 고친다
        ending = _card(copy.closing.strip(), "정리")
        ending["durationSec"] = max(ENDING_MIN, ending["durationSec"])
        ending["subtitle"] = (service_name or title["text"]).strip()
        scenes.append(ending)
    arch = infer_architecture(facts) if include_architecture else None
    # 노드가 하나뿐이면(예: 'Nuxt') 보여줄 구조가 없다 — 한 단어 화면이 4초 이어지지 않게 뺀다
    if arch and len(arch["nodes"]) >= 2:
        scenes.append({"type": "architecture", "durationSec": ARCH_SEC, **arch})
    # 영상 길이는 내용만큼 — 요청 길이(total_sec)는 상한. 더 길면 렌더가 비율대로 줄인다.
    content = round(sum(sc["durationSec"] for sc in scenes), 2)
    return {"fps": FPS, "totalSec": min(total_sec, content), "scenes": scenes}


def _user_message(
    scenario: dict,
    shots: list[dict],
    facts: RepoFacts,
    prompt: str | None = None,
    seen: list[str | None] | None = None,
) -> str:
    steps = {s["id"]: s for s in scenario["steps"]}
    screens = []
    for i, shot in enumerate(shots):
        screen = {
            "index": i,
            "status": shot.get("status", "ok"),
            "step": steps.get(shot["stepId"], {}),
        }
        if seen and i < len(seen) and seen[i]:
            screen["seen"] = seen[i]  # 스크린샷에 실제로 보이는 내용(이미지 모델)
            # 시나리오 초안 자막은 화면을 보지 않고 쓴 추측 — 있으면 LLM이 그대로 베낀다(11/23)
            screen["step"] = {k: v for k, v in screen["step"].items() if k != "caption"}
        screens.append(screen)
    data = {
        "name": facts.name,
        "summary": facts.summary,
        "readme": facts.readme,
        "screens": screens,
    }
    n = len(screens)
    user = json.dumps(data, ensure_ascii=False, indent=2)
    user += f"\n\n화면 {n}개 — captions·weights·highlights는 정확히 {n}개씩, screens 순서대로."
    return with_reference(user, prompt, "자막 말투와 강조할 부분에만 반영한다")


def describe_shots(run_dir: Path, shots: list[dict], describer: Describer) -> list[str | None]:
    """각 화면 스크린샷을 이미지 모델로 한 번에 읽는다. 파일이 없거나 못 읽으면 None."""
    files = [run_dir / shot.get("image", "") for shot in shots]
    present = [i for i, f in enumerate(files) if f.is_file()]
    out: list[str | None] = [None] * len(shots)
    if present:
        answers = describer.describe_many([files[i].read_bytes() for i in present])
        for i, text in zip(present, answers, strict=False):
            out[i] = text
    return out


EMPTY_SEEN = "로딩 중인 빈 화면"  # prompts/vision.md 가 빈 화면에 쓰라고 정한 문구

# 이미지 모델이 설명 앞에 붙이는 핵심 영역 [위치](prompts/vision.md) → 1280x720 칸 중심
FOCUS_ZOOM = 1.35  # 클릭 줌보다 약하게 — 맥락은 남기고 설명하는 곳으로 시선만 모은다
_CELLS = ["왼쪽위", "위", "오른쪽위", "왼쪽", "가운데", "오른쪽", "왼쪽아래", "아래", "오른쪽아래"]
_FOCUS = re.compile(r"^\[\s*([^\]]+?)\s*\]\s*")


def split_focus(seen: list[str | None]) -> tuple[list[str | None], list[dict | None]]:
    """'[위] 설명' → ('설명', 위 칸 중심). 위치가 없거나 모르는 말이면 None(줌 없음)."""
    texts: list[str | None] = []
    points: list[dict | None] = []
    for s in seen:
        m = _FOCUS.match(s or "")
        cell = m.group(1).replace(" ", "") if m else ""
        texts.append(s[m.end() :] if s and m else s)
        if cell in _CELLS:
            row, col = divmod(_CELLS.index(cell), 3)
            points.append({"x": round((col + 0.5) * 1280 / 3), "y": round((row + 0.5) * 720 / 3)})
        else:
            points.append(None)
    return texts, points


def drop_empty(shots: list[dict], seen: list[str | None]) -> tuple[list[dict], list[str | None]]:
    """이미지 모델이 빈 화면이라 한 화면은 뺀다 — 보이는 게 없는데 자막만 기능을 말하게 된다.

    캡처의 로딩 뼈대 감지가 못 잡은 것(스피너 등)용. 전부 비었으면 그대로 둔다(영상은 나와야 한다).
    """
    kept = [
        (s, t) for s, t in zip(shots, seen, strict=False) if not (t and t.startswith(EMPTY_SEEN))
    ]
    if not kept:
        return shots, seen
    return [s for s, _ in kept], [t for _, t in kept]


def build_scene(
    run_dir: Path,
    total_sec: float,
    include_architecture: bool,
    llm: LLM | None,
    *,
    describer: Describer | None = None,
) -> dict:
    scenario = json.loads((run_dir / "scenario.json").read_text())
    capture = json.loads((run_dir / "capture.json").read_text())
    facts = RepoFacts.from_json((run_dir / "facts.json").read_text())
    prompt_file = run_dir / "prompt.txt"
    prompt = prompt_file.read_text() if prompt_file.exists() else None
    shots = keep_shots(capture["shots"])
    login = capture.get("login") or {}
    # 배포 사이트가 밝힌 서비스 이름(app/logo.py) — README 첫 제목은 슬로건인 경우가 많다
    name_file = run_dir / "site_name.txt"
    site = name_file.read_text().strip() if name_file.exists() else ""
    if site:
        facts = dataclasses.replace(facts, name=site)
    media = {
        "video": capture.get("video"),
        "login_images": login.get("images"),
        "service_name": site or None,
    }

    def check(c: SceneCopy) -> list[str]:
        errors = []
        # captions·weights 개수가 화면 수와 달라도 버리지 않는다 — 모자란 건 시나리오 초안·1.0 으로
        if not c.title.strip():
            errors.append("title이 비어 있음")
        if any(not t.strip() or len(t) > MAX_CAPTION for t in c.captions):
            errors.append(f"caption은 1~{MAX_CAPTION}자")
        if any(not W_MIN <= w <= W_MAX for w in c.weights):
            errors.append(f"weights는 {W_MIN}~{W_MAX}")
        if max(len(c.problem), len(c.closing), len(c.solution)) > MAX_CARD:
            errors.append(f"problem·solution·closing은 {MAX_CARD}자 이하")
        for name, pts, most in (
            ("problem_points", c.problem_points, MAX_SITUATION),
            ("solution_points", c.solution_points, MAX_POINT),
        ):
            if len(pts) > 4 or any(len(p.text) > most for p in pts):
                errors.append(f"{name}는 4개 이하, 항목당 {most}자 이하")
        return errors

    copy = None
    if llm is not None:
        seen = describe_shots(run_dir, shots, describer) if describer else None
        if seen is not None:  # 자막 점검용 — 화면마다 이미지 모델이 읽은 내용
            (run_dir / "seen.json").write_text(json.dumps(seen, ensure_ascii=False, indent=2))
            seen, focus = split_focus(seen)
            # 핵심 영역은 shot 에 붙인다(빈 화면을 뺄 때 같이 빠지게). capture.json 에는 안 쓴다
            shots = [{**s, "focus": f} if f else s for s, f in zip(shots, focus, strict=False)]
            shots, seen = drop_empty(shots, seen)
        user = _user_message(scenario, shots, facts, prompt, seen)
        copy = generate(llm, system=SYSTEM, user=user, output=SceneCopy, check=check)
    doc = assemble(scenario, shots, facts, total_sec, include_architecture, copy, **media)
    if copy is not None and schema_errors("scene", doc):
        doc = assemble(scenario, shots, facts, total_sec, include_architecture, None, **media)
    doc = fill(doc, total_sec)
    if errors := schema_errors("scene", doc):
        raise ValueError("scene 계약 위반: " + "; ".join(errors))
    (run_dir / "scene.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2))
    return doc
