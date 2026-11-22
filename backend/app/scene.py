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

FPS = 30
TITLE_SEC = 3
SCREEN_SEC = 4
FALLBACK_SEC = 2
ARCH_SEC = 6
ZOOM = 1.6
W_MIN, W_MAX = 0.5, 2.0
MAX_CAPTION = 30
SYSTEM = (Path(__file__).parent / "prompts" / "scene.md").read_text()


class SceneCopy(BaseModel):
    title: str
    subtitle: str
    captions: list[str]
    weights: list[float]


def _clamp(w: float) -> float:
    return min(W_MAX, max(W_MIN, w))


def assemble(
    scenario: dict,
    capture: dict,
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

    for i, shot in enumerate(capture["shots"]):
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

    if include_architecture:
        scenes.append(
            {"type": "architecture", "durationSec": ARCH_SEC, **infer_architecture(facts)}
        )
    return {"fps": FPS, "totalSec": total_sec, "scenes": scenes}


def _user_message(scenario: dict, capture: dict, facts: RepoFacts) -> str:
    steps = {s["id"]: s for s in scenario["steps"]}
    screens = [
        {"index": i, "status": shot.get("status", "ok"), "step": steps.get(shot["stepId"], {})}
        for i, shot in enumerate(capture["shots"])
    ]
    data = {"name": facts.name, "summary": facts.summary, "screens": screens}
    return json.dumps(data, ensure_ascii=False, indent=2)


def build_scene(
    run_dir: Path, total_sec: float, include_architecture: bool, llm: LLM | None
) -> dict:
    scenario = json.loads((run_dir / "scenario.json").read_text())
    capture = json.loads((run_dir / "capture.json").read_text())
    facts = RepoFacts.from_json((run_dir / "facts.json").read_text())
    n = len(capture["shots"])

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
        return errors

    copy = None
    if llm is not None:
        user = _user_message(scenario, capture, facts)
        copy = generate(llm, system=SYSTEM, user=user, output=SceneCopy, check=check)
    doc = assemble(scenario, capture, facts, total_sec, include_architecture, copy)
    if copy is not None and schema_errors("scene", doc):
        doc = assemble(scenario, capture, facts, total_sec, include_architecture, None)
    if errors := schema_errors("scene", doc):
        raise ValueError("scene 계약 위반: " + "; ".join(errors))
    (run_dir / "scene.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2))
    return doc
