"""의존성 이름으로 아키텍처 다이어그램 노드를 추정한다 (C의 추출 모듈이 오기 전까지 임시).

계층 순서: 프론트 → API/BaaS → DB → 외부 API. 존재하는 계층만, 순서대로 한 줄로 잇는다.
"""

from __future__ import annotations

from app.analyze.facts import RepoFacts

# (의존성 이름 접두어, 노드 이름) — 위에서부터 먼저 맞는 것 사용
_API = [
    ("@supabase/", "Supabase"),
    ("supabase_flutter", "Supabase"),
    ("firebase", "Firebase"),
    ("firebase_core", "Firebase"),
    ("express", "Express"),
    ("fastify", "Fastify"),
    ("hono", "Hono"),
    ("@nestjs/", "NestJS"),
    ("fastapi", "FastAPI"),
    ("django", "Django"),
    ("flask", "Flask"),
    ("spring-boot", "Spring Boot"),
]
_DB = [
    ("@prisma/client", "PostgreSQL"),
    ("prisma", "PostgreSQL"),
    ("drizzle-orm", "PostgreSQL"),
    ("pg", "PostgreSQL"),
    ("postgres", "PostgreSQL"),
    ("mysql2", "MySQL"),
    ("mongoose", "MongoDB"),
    ("mongodb", "MongoDB"),
    ("better-sqlite3", "SQLite"),
    ("redis", "Redis"),
]
_EXTERNAL = [
    ("@anthropic-ai/sdk", "Claude API"),
    ("openai", "OpenAI API"),
    ("@google/genai", "Gemini API"),
    ("stripe", "Stripe"),
]
_BAAS = {"Supabase", "Firebase"}  # DB를 겸하므로 DB 계층 생략


def _first(stack: list[str], table: list[tuple[str, str]]) -> str | None:
    for prefix, name in table:
        if any(dep == prefix or (prefix.endswith("/") and dep.startswith(prefix)) for dep in stack):
            return name
    return None


def _frontend(facts: RepoFacts) -> str:
    stack = facts.stack
    if facts.framework == "flutter":
        return "Flutter"
    if "@sveltejs/kit" in stack:
        return "SvelteKit"
    if "next" in stack:
        return "Next.js"
    if "nuxt" in stack:
        return "Nuxt"
    if "react" in stack:
        return "React + Vite" if "vite" in stack else "React"
    if "vue" in stack:
        return "Vue"
    return "Web App"


def infer_architecture(facts: RepoFacts) -> dict:
    stack = [*facts.stack, *facts.services]  # 프론트 의존성 + 레포 안 백엔드 매니페스트
    nodes = [_frontend(facts)]
    api = _first(stack, _API)
    if api is None and nodes[0] == "Next.js" and (_first(stack, _DB) or _first(stack, _EXTERNAL)):
        api = "Next.js API"
    if api:
        nodes.append(api)
    if api not in _BAAS and (db := _first(stack, _DB)):
        nodes.append(db)
    if ext := _first(stack, _EXTERNAL):
        nodes.append(ext)
    return {"nodes": nodes, "edges": [[i, i + 1] for i in range(len(nodes) - 1)]}
