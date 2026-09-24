"""TraceGuard FastAPI application."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from backend.api import cases_router, investigate_router
from backend.config import settings

FRONTEND = Path(__file__).resolve().parents[1] / "frontend" / "index.html"

app = FastAPI(
    title="TraceGuard",
    description="Agentic, graph-native fraud investigation platform powered by TigerGraph.",
    version="0.1.0",
    debug=settings.app_debug,
)

app.include_router(cases_router)
app.include_router(investigate_router)


@app.get("/")
def analyst_page() -> FileResponse:
    return FileResponse(FRONTEND)


@app.get("/health")
def health_check() -> dict[str, str]:
    """Return the service health status."""
    return {"status": "ok"}
