"""FastAPI 진입점 (A 담당). 실행: make dev-api"""

from fastapi import FastAPI

app = FastAPI(title="DemoDay API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
