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
MAX_CARD = 28  # B의 kicker 장 구분 카드 전까지 제목 스타일(84px)로 그려진다 — 두 줄 이내
SYSTEM = (Path(__file__).parent / "prompts" / "scene.md").read_text()


class SceneCopy(BaseModel):
    title: str
    subtitle: str
    captions: list[str]
    weights: list[float]
    problem: str = ""  # README에 나온 문제 한 문장 (없으면 빈 문자열 → 카드 없음)
    closing: str = ""  # 서비스 가치 한 문장 (없으면 카드 없음)


def _clamp(w: float) -> float:
    return min(W_MAX, max(W_MIN, w))


def keep_shots(shots: list[dict]) -> list[dict]:
    """fallback이 연속되면 첫 번째만 남긴다 — 실패 뒤 이어지는 단계는 보통 같은 화면이다."""
    kept: list[dict] = []
    for shot in shots:
        fallback = shot.get("status", "ok") == "fallback"
        if fallback and kept and kept[-1].get("status", "ok") == "fallback":
            continue
        kept.append(shot)
    return kept


def _card(text: str) -> dict:
    return {"type": "title", "durationSec": CARD_SEC, "text": text}


def assemble(
    scenario: dict,
    shots: list[dict],
    facts: RepoFacts,
    total_sec: float,
    include_architecture: bool,
    copy: SceneCopy | None,
) -> dict:
    step_caption = {s["id"]: s.get("caption", "") for s in scenario["steps"]}
    title = {"type": "title", "durationSec": TITLE_SEC, "text": (copy and copy.title) or facts.name}
    subtitle = copy.subtitle if copy else facts.summary
    if subtitle:
        title["subtitle"] = subtitle
    scenes: list[dict] = [title]
    if copy and copy.problem.strip():
        scenes.append(_card(copy.problem.strip()))

    for i, shot in enumerate(shots):
        caption = copy.captions[i] if copy else step_caption.get(shot["stepId"], "")
        screen: dict = {"type": "screen", "image": shot["image"]}
        if shot.get("status", "ok") == "fallback":
            screen["durationSec"] = FALLBACK_SEC
        else:
            screen["durationSec"] = SCREEN_SEC * (_clamp(copy.weights[i]) if copy else 1)
            if click := shot.get("click"):
                screen["zoom"] = {"x": click["x"], "y": click["y"], "scale": ZOOM}
                screen["cursor"] = {"x": click["x"], "y": click["y"]}
        if caption:
            screen["caption"] = caption
        scenes.append(screen)

    if copy and copy.closing.strip():
        scenes.append(_card(copy.closing.strip()))
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
    shots = keep_shots(capture["shots"])  # LLM 호출 전에 — 자막·가중치 개수 = 남은 shot 수
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
    doc = assemble(scenario, shots, facts, total_sec, include_architecture, copy)
    if copy is not None and schema_errors("scene", doc):
        doc = assemble(scenario, shots, facts, total_sec, include_architecture, None)
    if errors := schema_errors("scene", doc):
        raise ValueError("scene 계약 위반: " + "; ".join(errors))
    (run_dir / "scene.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2))
    return doc
