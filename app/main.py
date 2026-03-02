"""
main.py — FastAPI application entry point.  Runs on port 7861.
"""

import logging

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.config import SERVER_PORT
from app.routers.upload import router as upload_router
from app.services.weaviate_store import get_collection_stats

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="SENTRA — Document Processing Service",
    description=(
        "Async PDF upload → Image conversion → Vision LLM extraction → "
        "Embedding creation → Weaviate storage pipeline."
    ),
    version="1.0.0",
)

app.include_router(upload_router)


# ── Health & stats ────────────────────────────────────────────────────────────

@app.get("/health", summary="Health check")
async def health() -> JSONResponse:
    return JSONResponse(content={"status": "ok"})


@app.get("/collections/stats", summary="Weaviate collection object counts")
async def collection_stats() -> JSONResponse:
    stats = await get_collection_stats()
    return JSONResponse(content=stats)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=SERVER_PORT,
        reload=False,
    )
