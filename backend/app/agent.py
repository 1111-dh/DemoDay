"""에이전트 녹화 모드의 판단 쪽(#53). 캡처(B)가 자식 프로세스로 띄운다.

stdin 으로 관찰 JSON 한 줄 → 이미지 LLM 이 다음 동작을 고름 → stdout 으로 동작 JSON 한 줄.
LLM 은 영상을 만들지 않는다 — 실제로 한 동작은 캡처가 scenario.json 단계로 남기고
scene·render 는 그대로 쓴다.

실행: DEMODAY_RUN_DIR=<run 디렉터리> uv run --project backend python -m app.agent
(관찰의 screenshot 은 run 디렉터리 기준 경로). 판단 모델은 BAZE(BAZE_AGENT_MODEL, 기본 Haiku 5.5).
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Literal

import httpx
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, ValidationError

from app.analyze.facts import RepoFacts
from app.llm import BAZE_BASE_URL, BAZE_CHAT_PATH, BAZE_MODEL, post_with_rate_retry, strict_schema
from app.scenario import _DANGER

log = logging.getLogger(__name__)
PROMPT = (Path(__file__).parent / "prompts" / "agent.md").read_text()
INPUT_ROLES = {"textbox", "searchbox", "combobox"}
MAX_TOKENS = 4096  # 생각하는 모델 — 작으면 빈 답(vision 과 같은 이유)
DONE = {"action": "done"}


class AgentAction(BaseModel):
    action: Literal["click", "type", "scroll", "done"]
    id: int
    value: str
    caption: str


def goal_for(facts: RepoFacts, prompt: str | None) -> str:
    """캡처에 넘길 목표 한 줄 — 서비스 소개 + 사용자 요청."""
    goal = f"{facts.name}: {facts.summary}".strip(": ")[:200]
    goal += " — 핵심 기능을 처음 쓰는 사람처럼 직접 써 보며 보여준다."
    return f"{goal} 요청: {prompt.strip()}" if prompt and prompt.strip() else goal


def _safe(elements: list[dict]) -> list[dict]:
    return [e for e in elements if not _DANGER.search(e.get("name") or "")]


def _marked(path: Path, elements: list[dict]) -> bytes:
    """Set-of-Mark: 요소 상자와 번호를 그린 스크린샷(녹화에는 남지 않는다)."""
    img = Image.open(path).convert("RGB")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=16)
    for e in elements:
        b = e["box"]
        x, y, w, h = b["x"], b["y"], b["w"], b["h"]
        draw.rectangle((x, y, x + w, y + h), outline=(230, 30, 30), width=2)
        draw.rectangle((x, y - 18, x + 8 + 9 * len(str(e["id"])), y), fill=(230, 30, 30))
        draw.text((x + 3, y - 18), str(e["id"]), fill=(255, 255, 255), font=font)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _problem(a: AgentAction, elements: dict[int, dict], clicked: set[str]) -> str | None:
    if a.action in ("click", "type") and a.id not in elements:
        return f"id {a.id}는 후보 목록에 없다"
    # 같은 요소를 다시 누르면 같은 장면이 반복된다. 번호는 화면마다 새로 매겨지니 이름으로 본다
    if a.action == "click" and (name := elements[a.id].get("name")) in clicked:
        return f"'{name}'은 이미 눌렀다 — 아직 보여주지 않은 기능을 골라라"
    if a.action == "type":
        if elements[a.id]["role"] not in INPUT_ROLES:
            return f"id {a.id}({elements[a.id]['role']})는 입력칸이 아니다"
        if not a.value.strip():
            return "type 에는 value 가 필요하다"
    return None


def _clean(a: AgentAction) -> dict:
    out: dict = {"action": a.action}
    if a.action in ("click", "type"):
        out["id"] = a.id
    if a.action == "type":
        out["value"] = a.value.strip()
    if a.action != "done" and a.caption.strip():
        out["caption"] = a.caption.strip()
    return out


class Decider:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        run_dir: Path,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.url = BAZE_BASE_URL + BAZE_CHAT_PATH
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self.model = model
        self.run_dir = run_dir
        self.client = client or httpx.Client(timeout=50)
        self.sleep = sleep
        self.clicked: set[str] = (
            set()
        )  # 이 영상에서 이미 누른 요소 이름(프로세스가 영상 하나 동안 산다)

    def _ask(self, text: str, image: bytes) -> AgentAction | None:
        url = "data:image/png;base64," + base64.b64encode(image).decode()
        body = {
            "model": self.model,
            "max_tokens": MAX_TOKENS,
            "messages": [
                {"role": "system", "content": PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": text},
                        {"type": "image_url", "image_url": {"url": url}},
                    ],
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "AgentAction",
                    "strict": True,
                    "schema": strict_schema(AgentAction.model_json_schema()),
                },
            },
        }
        res = post_with_rate_retry(self.client, self.url, self.headers, body, self.sleep)
        if res is None:
            return None
        try:
            return AgentAction.model_validate_json(res.json()["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError, ValueError, ValidationError):
            log.warning("에이전트 응답 형식 오류")
            return None

    def decide(self, obs: dict) -> dict:
        elements = _safe(obs.get("elements") or [])
        by_id = {e["id"]: e for e in elements}
        listing = "\n".join(f"[{e['id']}] {e['role']} {e['name']}" for e in elements) or "(없음)"
        history = json.dumps(obs.get("history") or [], ensure_ascii=False)
        text = (
            f"목표: {obs.get('goal', '')}\n지금 단계: {obs.get('step')} / 주소: {obs.get('url')}\n"
            f"지금까지 한 동작: {history}\n\n후보 요소(스크린샷의 빨간 번호):\n{listing}"
        )
        try:
            image = _marked(self.run_dir / obs["screenshot"], elements)
        except (OSError, KeyError, ValueError):
            log.warning("에이전트 스크린샷을 못 읽음")
            return DONE
        prompt = text
        for _ in range(2):
            a = self._ask(prompt, image)
            if a is None:
                return DONE
            if (err := _problem(a, by_id, self.clicked)) is None:
                if a.action == "click":
                    self.clicked.add(by_id[a.id].get("name") or "")
                return _clean(a)
            prompt = f"{text}\n\n이전 답 {a.model_dump_json()}은 틀렸다: {err}. 다시 골라라."
        return DONE


def serve(decider) -> None:
    """관찰 한 줄마다 동작 한 줄. 어떤 예외든 done 으로 답해 캡처가 멈추지 않게 한다."""
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            out = decider.decide(json.loads(line))
        except Exception:  # noqa: BLE001 — 판단 실패는 끝내기로(캡처는 기존 시나리오로 대체)
            log.exception("에이전트 판단 실패")
            out = DONE
        sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
        sys.stdout.flush()


def main() -> None:
    from dotenv import load_dotenv

    from app import paths

    load_dotenv(paths.ROOT / ".env")
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)  # stdout 은 동작 전용
    key = os.environ.get("BAZE_API_KEY")
    run_dir = Path(os.environ.get("DEMODAY_RUN_DIR", "."))
    if not key:
        log.warning("BAZE_API_KEY 가 없어 에이전트가 바로 끝낸다")
        for line in sys.stdin:
            if line.strip():
                print(json.dumps(DONE), flush=True)
        return
    serve(
        Decider(api_key=key, model=os.environ.get("BAZE_AGENT_MODEL", BAZE_MODEL), run_dir=run_dir)
    )


if __name__ == "__main__":
    main()
