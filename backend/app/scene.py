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
from app.llm import LLM, generate
from app.scenario import with_reference

FPS = 30
TITLE_SEC = 3
SCREEN_SEC = 4
FALLBACK_SEC = 2
ARCH_SEC = 6
ZOOM = 1.6
W_MIN, W_MAX = 0.5, 2.0
MAX_CAPTION = 30
CARD_SEC = 3  # 문제·정리 카드
MAX_CLIP_SEC = 8  # 녹화 구간이 길어도 장면은 이 이상 늘리지 않는다
LOGIN_SEC = 2
LOGIN_CAPTION = "테스트 계정으로 로그인"
MAX_HIGHLIGHTS = 2
MAX_CARD = 28  # 문제·정리 카드는 큰 글씨 장 구분 카드로 그려진다 — 두 줄 이내
SYSTEM = (Path(__file__).parent / "prompts" / "scene.md").read_text()


class SceneCopy(BaseModel):
    title: str
    subtitle: str
    captions: list[str]
    weights: list[float]
    highlights: list[list[str]] = []  # 화면별 caption 에서 그대로 따온 강조어 (비우면 없음)
    problem: str = ""  # README에 나온 문제 한 문장 (없으면 빈 문자열 → 카드 없음)
    closing: str = ""  # 서비스 가치 한 문장 (없으면 카드 없음)


def _clamp(w: float) -> float:
    return min(W_MAX, max(W_MIN, w))


def keep_shots(shots: list[dict]) -> list[dict]:
    """실패(fallback)한 단계는 뺀다 — 일어나지 않은 동작을 자막으로 말하게 된다.

    전부 실패했으면 첫 화면 하나만 남긴다(영상은 나와야 한다).
    """
    ok = [shot for shot in shots if shot.get("status", "ok") != "fallback"]
    return ok or shots[:1]


def _card(text: str, kicker: str) -> dict:
    return {"type": "title", "durationSec": CARD_SEC, "text": text, "kicker": kicker}


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
        scenes.append(_card(copy.problem.strip(), "문제"))
    for j, image in enumerate(login_images or []):  # 문제 → (로그인) → 해결 화면
        login: dict = {"type": "screen", "durationSec": LOGIN_SEC, "image": image}
        if j == len(login_images) - 1:
            login["caption"] = LOGIN_CAPTION
        scenes.append(login)

    # 강조 개수가 shot 수와 다르면 강조만 버린다 (자막·카드는 살린다)
    highlights = copy.highlights if copy and len(copy.highlights) == len(shots) else None
    for i, shot in enumerate(shots):
        caption = copy.captions[i] if copy else step_caption.get(shot["stepId"], "")
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
            screen["durationSec"] = SCREEN_SEC * (_clamp(copy.weights[i]) if copy else 1)
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
    if include_architecture:
        scenes.append(
            {"type": "architecture", "durationSec": ARCH_SEC, **infer_architecture(facts)}
        )
    return {"fps": FPS, "totalSec": total_sec, "scenes": scenes}


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
    user = json.dumps(data, ensure_ascii=False, indent=2)
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
    n = len(shots)

    def check(c: SceneCopy) -> list[str]:
        errors = []
        if len(c.captions) != n or len(c.weights) != n:
            errors.append(f"captions·weights는 정확히 {n}개여야 함")
        if not c.title.strip():
            errors.append("title이 비어 있음")
        if any(not t.strip() or len(t) > MAX_CAPTION for t in c.captions):
            errors.append(f"caption은 1~{MAX_CAPTION}자")
        if any(not W_MIN <= w <= W_MAX for w in c.weights):
            errors.append(f"weights는 {W_MIN}~{W_MAX}")
        if len(c.problem) > MAX_CARD or len(c.closing) > MAX_CARD:
            errors.append(f"problem·closing은 {MAX_CARD}자 이하")
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
