from fastapi import FastAPI

from app.api.chat_routes import router as guardrail_router


def create_app() -> FastAPI:
    app = FastAPI(title="PikuAI Gaurdrails", version="0.1.0")
    app.include_router(guardrail_router, prefix="/api/v1")

    @app.get("/health")
    def health() -> dict[str, object]:
        return {"ok": True, "service": "pikuai-gaurdrails"}

    return app


app = create_app()
