"""scenario + capture + facts → scene.json.

장면 구성은 결정적으로 조립하고, LLM(SceneCopy)은 제목·자막·장면 비중만 맡는다.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from app.analyze.facts import RepoFacts
from app.architecture import infer_architecture
from app.contracts import schema_errors
from app.contracts.scene import Icon
from app.llm import LLM, generate
from app.scenario import with_reference

FPS = 30
TITLE_SEC = 3
SCREEN_SEC = 4
FALLBACK_SEC = 2
ARCH_SEC = 4
ZOOM = 1.6
W_MIN, W_MAX = 0.5, 2.0
MAX_CAPTION = 30
CARD_MIN, CARD_MAX = 2.0, 4.0  # 문제·정리 카드 — 글자 수만큼 읽을 시간
MAX_CLIP_SEC = 8  # 녹화 구간이 길어도 장면은 이 이상 늘리지 않는다
LOGIN_SEC = 2
LOGIN_CAPTION = "테스트 계정으로 로그인"
MAX_HIGHLIGHTS = 2
MAX_CARD = 28  # 문제·정리 카드는 큰 글씨 장 구분 카드로 그려진다 — 두 줄 이내
SYSTEM = (Path(__file__).parent / "prompts" / "scene.md").read_text()


MAX_POINT = 24  # points 항목 한 줄
POINTS_BASE, POINT_SEC = 1.5, 1.0  # points 장면 길이: 1.5초 + 항목당 1초


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


def _clamp(w: float) -> float:
    return min(W_MAX, max(W_MIN, w))


def keep_shots(shots: list[dict]) -> list[dict]:
    """실패(fallback)한 단계는 뺀다 — 일어나지 않은 동작을 자막으로 말하게 된다.

    전부 실패했으면 첫 화면 하나만 남긴다(영상은 나와야 한다).
    """
    ok = [shot for shot in shots if shot.get("status", "ok") != "fallback"]
    return ok or shots[:1]


def _points(heading: str, points: list[PointDraft], kicker: str) -> dict | None:
    """문제·해결 아이콘 카드 장면. 항목이 2개 미만이면 None (호출부가 카드로 대신)."""
    items = [{"icon": str(p.icon), "text": p.text.strip()} for p in points if p.text.strip()][:4]
    if len(items) < 2:
        return None
    sec = POINTS_BASE + POINT_SEC * len(items)
    return {
        "type": "points",
        "durationSec": sec,
        "kicker": kicker,
        "heading": heading.strip(),
        "items": items,
    }


def _read_sec(text: str) -> float:
    """한 줄 문장을 읽을 시간: 1.2초 + 글자당 0.09초 (2~4초)."""
    return round(min(CARD_MAX, max(CARD_MIN, 1.2 + 0.09 * len(text))), 2)


def _card(text: str, kicker: str) -> dict:
    return {"type": "title", "durationSec": _read_sec(text), "text": text, "kicker": kicker}


def _highlight(caption: str, words: list[str]) -> list[str]:
    """caption 에 실제로 있는 단어만. 중복·더 긴 단어에 포함된 단어는 뺀다(긴 쪽 우선)."""
    found = sorted({w.strip() for w in words if w.strip() and w.strip() in caption}, key=len)
    kept = [w for i, w in enumerate(found) if not any(w in longer for longer in found[i + 1 :])]
    return sorted(kept, key=caption.index)[:MAX_HIGHLIGHTS]


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
) -> dict:
    """video = capture.video (녹화 파일), login_images = capture.login.images (입력칸 가림)."""
    step_caption = {s["id"]: s.get("caption", "") for s in scenario["steps"]}
    title = {"type": "title", "durationSec": TITLE_SEC, "text": (copy and copy.title) or facts.name}
    subtitle = copy.subtitle if copy else facts.summary
    if subtitle:
        title["subtitle"] = subtitle
    scenes: list[dict] = [title]
    if copy and copy.problem.strip():
        problem = _points(copy.problem, copy.problem_points, "문제")
        scenes.append(problem or _card(copy.problem.strip(), "문제"))
    if (
        copy
        and copy.solution.strip()
        and (solution := _points(copy.solution, copy.solution_points, "해결"))
    ):
        scenes.append(solution)
    for j, image in enumerate(login_images or []):  # 문제 → (로그인) → 해결 화면
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
            screen["durationSec"] = min(MAX_CLIP_SEC, max(FALLBACK_SEC, sec))
            screen["video"] = {"src": video, "startMs": clip["startMs"], "endMs": clip["endMs"]}
        else:
            weight = copy.weights[i] if copy and i < len(copy.weights) else 1
            screen["durationSec"] = SCREEN_SEC * _clamp(weight)
        if shot.get("status", "ok") != "fallback":
            if click := shot.get("click"):
                screen["zoom"] = {"x": click["x"], "y": click["y"], "scale": ZOOM}
                screen["cursor"] = {"x": click["x"], "y": click["y"]}
        if caption:
            screen["caption"] = caption
            if highlights and (words := _highlight(caption, highlights[i])):
                screen["highlight"] = words
        scenes.append(screen)

    if copy and copy.closing.strip():
        scenes.append(_card(copy.closing.strip(), "정리"))
    arch = infer_architecture(facts) if include_architecture else None
    # 노드가 하나뿐이면(예: 'Nuxt') 보여줄 구조가 없다 — 한 단어 화면이 4초 이어지지 않게 뺀다
    if arch and len(arch["nodes"]) >= 2:
        scenes.append({"type": "architecture", "durationSec": ARCH_SEC, **arch})
    # 영상 길이는 내용만큼 — 요청 길이(total_sec)는 상한. 더 길면 렌더가 비율대로 줄인다.
    # 짧은 내용을 요청 길이까지 늘리면 카드가 늘어지고 화면이 느리게 재생돼 루즈해진다.
    content = round(sum(sc["durationSec"] for sc in scenes), 2)
    return {"fps": FPS, "totalSec": min(total_sec, content), "scenes": scenes}


def _user_message(
    scenario: dict, shots: list[dict], facts: RepoFacts, prompt: str | None = None
) -> str:
    steps = {s["id"]: s for s in scenario["steps"]}
    screens = [
        {"index": i, "status": shot.get("status", "ok"), "step": steps.get(shot["stepId"], {})}
        for i, shot in enumerate(shots)
    ]
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


def build_scene(
    run_dir: Path, total_sec: float, include_architecture: bool, llm: LLM | None
) -> dict:
    scenario = json.loads((run_dir / "scenario.json").read_text())
    capture = json.loads((run_dir / "capture.json").read_text())
    facts = RepoFacts.from_json((run_dir / "facts.json").read_text())
    prompt_file = run_dir / "prompt.txt"
    prompt = prompt_file.read_text() if prompt_file.exists() else None
    shots = keep_shots(capture["shots"])
    login = capture.get("login") or {}
    media = {"video": capture.get("video"), "login_images": login.get("images")}

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
        for name, pts in (
            ("problem_points", c.problem_points),
            ("solution_points", c.solution_points),
        ):
            if len(pts) > 4 or any(len(p.text) > MAX_POINT for p in pts):
                errors.append(f"{name}는 4개 이하, 항목당 {MAX_POINT}자 이하")
        return errors

    copy = None
    if llm is not None:
        user = _user_message(scenario, shots, facts, prompt)
        copy = generate(llm, system=SYSTEM, user=user, output=SceneCopy, check=check)
    doc = assemble(scenario, shots, facts, total_sec, include_architecture, copy, **media)
    if copy is not None and schema_errors("scene", doc):
        doc = assemble(scenario, shots, facts, total_sec, include_architecture, None, **media)
    if errors := schema_errors("scene", doc):
        raise ValueError("scene 계약 위반: " + "; ".join(errors))
    (run_dir / "scene.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2))
    return doc
