from fastapi import FastAPI

from app.api.routes import router as validator_router


def create_app() -> FastAPI:
    app = FastAPI(title="PikuAI Guardrails Validator", version="0.1.0")
    app.include_router(validator_router, prefix="/api/v1")

    @app.get("/health")
    def health() -> dict[str, object]:
        return {"ok": True, "service": "pikuai-gaurdrails-validator"}

    return app


app = create_app()
