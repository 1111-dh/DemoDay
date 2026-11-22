"""run 디렉터리와 상태 파일(status.json). 위치는 paths.RUNS (테스트에서 교체 가능)."""

from __future__ import annotations

import json
import os
import re
import secrets
from datetime import datetime
from pathlib import Path

from app import paths

BUSY = ("queued", "capturing", "scening", "rendering")
_ID = re.compile(r"^\d{4}-\d{6}-[a-z0-9]{4}$")


def new_run() -> str:
    rid = f"{datetime.now():%m%d-%H%M%S}-{secrets.token_hex(2)}"
    (paths.RUNS / rid).mkdir(parents=True)
    write_status(rid, stage="created")
    return rid


def run_dir(rid: str) -> Path:
    d = paths.RUNS / rid
    if not _ID.match(rid) or not d.is_dir():
        raise KeyError(rid)
    return d


def read_status(rid: str) -> dict:
    f = run_dir(rid) / "status.json"
    return json.loads(f.read_text()) if f.exists() else {}


def write_status(rid: str, **fields: object) -> dict:
    status = {
        **read_status(rid),
        **fields,
        "updatedAt": datetime.now().isoformat(timespec="seconds"),
    }
    if status.get("stage") != "error":
        status.pop("error", None)
    if status.get("warning") is None:  # warning=None 으로 지운다
        status.pop("warning", None)
    write_json(run_dir(rid) / "status.json", status)
    return status


def write_json(path: Path, data: object) -> None:
    """임시 파일에 쓰고 교체 — 폴링 중인 읽기가 반쯤 쓴 파일을 보지 않게."""
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    os.replace(tmp, path)


def is_busy(rid: str) -> bool:
    return read_status(rid).get("stage") in BUSY
