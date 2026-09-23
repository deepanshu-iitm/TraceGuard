"""TraceGuard FastAPI application."""

from fastapi import FastAPI

app = FastAPI(
    title="TraceGuard",
    description="Agentic, graph-native fraud investigation platform powered by TigerGraph.",
    version="0.1.0",
)


@app.get("/health")
def health_check() -> dict[str, str]:
    """Return the service health status."""
    return {"status": "ok"}