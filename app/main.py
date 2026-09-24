"""FastAPI entry point for 觅旅."""

from fastapi import FastAPI

app = FastAPI(
    title="觅旅 MiliTravel API",
    version="0.1.0",
    description="觅旅旅行规划平台后端 API",
)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    """Return a lightweight liveness response."""
    return {"status": "ok"}
