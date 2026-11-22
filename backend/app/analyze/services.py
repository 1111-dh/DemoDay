"""앱(프론트) 폴더 밖 백엔드 매니페스트에서 아키텍처용 서비스 이름을 뽑는다.

모노레포(frontend/ + backend/ + ai/)는 프론트 package.json 만으로는 백엔드·DB 가 안 보인다.
결과는 architecture.py 표가 알아보는 의존성 이름(예: "fastapi", "postgres", "openai").
"""

from __future__ import annotations

import re

from app.analyze.routes import AppRoot
from app.github import SERVICE_MANIFESTS, RepoSnapshot

MAX_MANIFESTS = 10
_SKIP = re.compile(
    r"(?:^|/)(?:node_modules|vendor|\.venv|venv|dist|build|test|tests|e2e|examples?)/"
)
# (패턴, 이름) — 이름은 architecture.py 표의 접두어와 맞춘다
_KNOWN = [
    (r"\bfastapi\b", "fastapi"),
    (r"\bdjango\b", "django"),
    (r"\bflask\b", "flask"),
    (r"spring-boot|org\.springframework\.boot", "spring-boot"),
    (r"\bexpress\b", "express"),
    (r"@nestjs/", "@nestjs/core"),
    (r"psycopg|asyncpg|postgresql|image:\s*[\"']?postgres", "postgres"),
    (r"pymysql|mysqlclient|mysql-connector|image:\s*[\"']?mysql", "mysql2"),
    (r"pymongo|\bmotor\b|mongoose|image:\s*[\"']?mongo", "mongodb"),
    (r"\bredis\b", "redis"),
    (r"\bopenai\b", "openai"),
    (r"\banthropic\b", "@anthropic-ai/sdk"),
    (r"google-genai|google-generativeai|@google/genai", "@google/genai"),
]
_PATTERNS = [(re.compile(p, re.IGNORECASE), name) for p, name in _KNOWN]


def _manifests(snap: RepoSnapshot, root: AppRoot | None) -> list[str]:
    app = f"{root.dir}/" if root and root.dir else None
    found = []
    for path in snap.paths:
        if path.rsplit("/", 1)[-1] not in SERVICE_MANIFESTS or _SKIP.search(path):
            continue
        if app and path.startswith(
            app
        ):  # 프론트 자신(안드로이드 gradle 등 포함)은 package.json 이 이미 맡는다
            continue
        if root and not root.dir and path == "package.json":
            continue
        found.append(path)
    return sorted(found, key=lambda p: p.count("/"))[:MAX_MANIFESTS]


def service_stack(snap: RepoSnapshot, root: AppRoot | None) -> list[str]:
    names: list[str] = []
    for path in _manifests(snap, root):
        text = snap.read(path) or ""
        for pattern, name in _PATTERNS:
            if name not in names and pattern.search(text):
                names.append(name)
    return names
