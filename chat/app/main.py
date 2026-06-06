from fastapi import FastAPI

from app.api.routes import router as chat_router
from app.model_service import warm_chat_model


def create_app() -> FastAPI:
    app = FastAPI(title="PikuAI Guardrails Chat", version="0.1.0")
    app.include_router(chat_router, prefix="/api/v1")

    @app.on_event("startup")
    async def startup_load_model() -> None:
        warm_chat_model()

    @app.get("/health")
    def health() -> dict[str, object]:
        return {"ok": True, "service": "pikuai-gaurdrails-chat"}

    return app


app = create_app()
