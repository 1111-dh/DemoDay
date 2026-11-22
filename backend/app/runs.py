"""run 디렉터리와 상태 파일(status.json). 위치는 paths.RUNS (테스트에서 교체 가능)."""

from __future__ import annotations

import json
import re
import secrets
from datetime import datetime
from pathlib import Path

from app import paths

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
    (run_dir(rid) / "status.json").write_text(json.dumps(status, ensure_ascii=False))
    return status
