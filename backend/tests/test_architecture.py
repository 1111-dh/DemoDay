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
