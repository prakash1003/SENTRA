"""
embedder.py — Create text embeddings via text-embedding-3-small (LiteLLM → OpenAI).

Pages are embedded in parallel, controlled by MAX_CONCURRENT_EMBEDDINGS semaphore.
All public functions are async.
"""

import asyncio
import logging
import time

import litellm

from app.config import (
    EMBED_DIMENSIONS,
    EMBED_MODEL,
    MAX_CONCURRENT_EMBEDDINGS,
)
from app.utils.helpers import flatten_json

logger = logging.getLogger(__name__)


async def _embed_single(
    text: str,
    semaphore: asyncio.Semaphore,
) -> list[float]:
    """
    Embed a single text string.  Returns the embedding vector (list of floats).
    On error returns an empty list.
    """
    async with semaphore:
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: litellm.embedding(
                    model=EMBED_MODEL,
                    input=text,
                    dimensions=EMBED_DIMENSIONS,
                ),
            )
            return response.data[0]["embedding"]
        except Exception as exc:  # noqa: BLE001
            logger.error("Embedding failed: %s", exc)
            return []


async def embed_pages(extraction_results: list[dict]) -> list[dict]:
    """
    Create embeddings for each extracted page in parallel.

    Each *extraction_result* is a dict produced by extractor.extract_pages().
    Returns the same list with an extra ``embedding`` key added to each item.
    """
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_EMBEDDINGS)
    start = time.perf_counter()

    async def _process(result: dict) -> dict:
        extracted = result.get("extracted") or {}
        flat_text = flatten_json(extracted)
        embedding = await _embed_single(flat_text, semaphore)
        return {**result, "embedding": embedding, "flat_text": flat_text}

    enriched = await asyncio.gather(*[_process(r) for r in extraction_results])
    elapsed = round(time.perf_counter() - start, 3)
    logger.info("Embedded %d page(s) in %.3fs", len(enriched), elapsed)
    return list(enriched)
