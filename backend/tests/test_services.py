from app.analyze.facts import RepoFacts, build_facts
from app.analyze.routes import find_app_root
from app.analyze.services import service_stack
from tests.conftest import make_snap, pkg

FILES = {
    "README.md": "# M\n소개\n",
    "frontend/package.json": pkg({"react": "19", "vite": "6"}),
    "frontend/src/App.tsx": "<Routes></Routes>",
    "frontend/android/build.gradle.kts": 'id("org.springframework.boot")',  # 프론트 폴더 → 무시
    "backend/requirements.txt": "fastapi==0.110\nasyncpg>=0.29\nopenai\nredis\n",
    "backend/docker-compose.yml": "services:\n  db:\n    image: postgres:16\n",
    "ai/pyproject.toml": '[project]\ndependencies = ["anthropic>=0.40", "google-genai"]\n',
}


def test_service_stack_reads_manifests_outside_app_root():
    snap = make_snap(FILES)
    services = service_stack(snap, find_app_root(snap))
    assert {"fastapi", "postgres", "openai", "redis", "@anthropic-ai/sdk", "@google/genai"} <= set(
        services
    )
    assert "spring-boot" not in services


def test_build_facts_keeps_services():
    assert "fastapi" in build_facts(make_snap(FILES)).services


def test_services_default_and_old_json():
    import json
    from dataclasses import asdict

    d = asdict(RepoFacts("n", "s", [], None, None, []))
    assert d["services"] == []
    d.pop("services")
    assert RepoFacts.from_json(json.dumps(d)).services == []


def test_spring_boot_gradle_and_mongo_compose():
    snap = make_snap(
        {
            "web/package.json": pkg({"next": "16", "react": "19"}),
            "web/app/page.tsx": "<main/>",
            "server/build.gradle": "implementation 'org.springframework.boot:spring-boot-starter'",
            "compose.yaml": "services:\n  mongo:\n    image: mongo:7\n",
        }
    )
    assert {"spring-boot", "mongodb"} <= set(service_stack(snap, find_app_root(snap)))
