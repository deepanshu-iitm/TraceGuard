"""TraceGuard FastAPI application."""

from fastapi import FastAPI

from backend.api import investigate_router
from backend.config import settings

app = FastAPI(
    title="TraceGuard",
    description="Agentic, graph-native fraud investigation platform powered by TigerGraph.",
    version="0.1.0",
    debug=settings.app_debug,
)


app.include_router(investigate_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    """Return the service health status."""
    return {"status": "ok"}