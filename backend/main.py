"""TraceGuard FastAPI application."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from backend.api import cases_router, graph_router, investigate_router, monitoring_router
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
app.include_router(graph_router)
app.include_router(monitoring_router)


@app.get("/")
def analyst_page() -> FileResponse:
    return FileResponse(FRONTEND)


@app.get("/health")
def health_check() -> dict[str, str]:
    """Return service health and which backends are active. Never include secrets."""
    return {
        "status": "ok",
        "graph": "tigergraph" if settings.tg_host.strip() else "local",
        "llm": "on" if settings.openai_api_key.strip() else "off",
    }
