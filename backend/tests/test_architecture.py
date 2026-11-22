from app.analyze.facts import RepoFacts
from app.architecture import infer_architecture


def facts(stack, framework="next-app") -> RepoFacts:
    return RepoFacts("x", "", sorted(stack), "", framework, [])


def test_next_supabase():
    arch = infer_architecture(facts(["next", "react", "@supabase/supabase-js"]))
    assert arch == {"nodes": ["Next.js", "Supabase"], "edges": [[0, 1]]}


def test_next_without_backend_uses_api_routes_and_db():
    arch = infer_architecture(facts(["next", "react", "@prisma/client", "@anthropic-ai/sdk"]))
    assert arch["nodes"] == ["Next.js", "Next.js API", "PostgreSQL", "Claude API"]


def test_react_vite_express_mongo():
    arch = infer_architecture(facts(["react", "vite", "express", "mongoose"], "react"))
    assert arch["nodes"] == ["React + Vite", "Express", "MongoDB"]


def test_react_only_single_node():
    assert infer_architecture(facts(["react"], "react")) == {"nodes": ["React"], "edges": []}


def test_edges_chain():
    arch = infer_architecture(facts(["next", "firebase", "openai"]))
    assert arch["edges"] == [[i, i + 1] for i in range(len(arch["nodes"]) - 1)]


def test_no_app_still_one_node():
    assert infer_architecture(RepoFacts("x", "", [], None, None, []))["nodes"] == ["Web App"]


def test_frontend_names_for_other_frameworks():
    assert infer_architecture(facts(["nuxt", "vue"], "nuxt"))["nodes"][0] == "Nuxt"
    assert infer_architecture(facts(["vue", "vite"], "vue"))["nodes"][0] == "Vue"


def test_sveltekit_and_flutter_nodes():
    assert infer_architecture(facts(["@sveltejs/kit"], "sveltekit"))["nodes"][0] == "SvelteKit"
    arch = infer_architecture(facts(["go_router", "firebase_core"], "flutter"))
    assert arch["nodes"] == ["Flutter", "Firebase"]
    assert infer_architecture(facts(["supabase_flutter"], "flutter"))["nodes"] == [
        "Flutter",
        "Supabase",
    ]


def test_backend_services_join_the_chain():  # 프론트 package.json 밖의 백엔드 (모노레포)
    f = facts(["react", "vite"], "react")
    f.services = ["fastapi", "postgres", "redis", "openai"]
    assert infer_architecture(f)["nodes"] == ["React + Vite", "FastAPI", "PostgreSQL", "OpenAI API"]


def test_flutter_with_django_backend():
    f = facts(["go_router"], "flutter")
    f.services = ["django", "mysql2"]
    assert infer_architecture(f)["nodes"] == ["Flutter", "Django", "MySQL"]


def test_spring_boot_node():
    f = facts(["next", "react"])
    f.services = ["spring-boot", "postgres"]
    assert infer_architecture(f)["nodes"] == ["Next.js", "Spring Boot", "PostgreSQL"]
