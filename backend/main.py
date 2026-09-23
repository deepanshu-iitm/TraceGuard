"""TraceGuard FastAPI application."""

from fastapi import FastAPI

from backend.config import settings

app = FastAPI(
    title="TraceGuard",
    description="Agentic, graph-native fraud investigation platform powered by TigerGraph.",
    version="0.1.0",
    debug=settings.app_debug,
)


@app.get("/health")
def health_check() -> dict[str, str]:
    """Return the service health status."""
    return {"status": "ok"}