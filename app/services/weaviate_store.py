"""
weaviate_store.py — Embedded Weaviate client, collection management, and async inserts.

Uses Embedded Weaviate (runs inside the process — no external service required).
All public functions are async.
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

import weaviate
import weaviate.classes as wvc
from weaviate.embedded import EmbeddedOptions

from app.utils.helpers import detect_community, detect_lot_code

logger = logging.getLogger(__name__)

# ── Singleton client ──────────────────────────────────────────────────────────
_client: weaviate.WeaviateClient | None = None


def get_client() -> weaviate.WeaviateClient:
    """Return (and lazily create) the singleton Weaviate embedded client."""
    global _client  # noqa: PLW0603
    if _client is None:
        logger.info("Starting embedded Weaviate …")
        _client = weaviate.connect_to_embedded(
            version="1.24.4",
            options=EmbeddedOptions(),
        )
        _ensure_collections(_client)
        logger.info("Embedded Weaviate is ready.")
    return _client


# ── Collection definitions ────────────────────────────────────────────────────

def _ensure_collections(client: weaviate.WeaviateClient) -> None:
    """Create collections if they don't already exist."""
    _create_selection_sheets(client)
    _create_take_offs(client)


def _create_selection_sheets(client: weaviate.WeaviateClient) -> None:
    if client.collections.exists("SelectionSheets"):
        return
    client.collections.create(
        name="SelectionSheets",
        vectorizer_config=wvc.config.Configure.Vectorizer.none(),
        vector_index_config=wvc.config.Configure.VectorIndex.hnsw(
            distance_metric=wvc.config.VectorDistances.COSINE,
        ),
        properties=[
            wvc.config.Property(name="text", data_type=wvc.config.DataType.TEXT),
            wvc.config.Property(name="pdf_name", data_type=wvc.config.DataType.TEXT),
            wvc.config.Property(name="pdf_type", data_type=wvc.config.DataType.TEXT),
            wvc.config.Property(name="lot_code", data_type=wvc.config.DataType.TEXT),
            wvc.config.Property(name="community", data_type=wvc.config.DataType.TEXT),
            wvc.config.Property(name="page_number", data_type=wvc.config.DataType.INT),
            wvc.config.Property(name="section_name", data_type=wvc.config.DataType.TEXT),
            wvc.config.Property(name="upload_batch_id", data_type=wvc.config.DataType.TEXT),
            wvc.config.Property(name="extracted_at", data_type=wvc.config.DataType.TEXT),
            wvc.config.Property(name="raw_json", data_type=wvc.config.DataType.TEXT),
        ],
    )
    logger.info("Created Weaviate collection: SelectionSheets")


def _create_take_offs(client: weaviate.WeaviateClient) -> None:
    if client.collections.exists("TakeOffs"):
        return
    client.collections.create(
        name="TakeOffs",
        vectorizer_config=wvc.config.Configure.Vectorizer.none(),
        vector_index_config=wvc.config.Configure.VectorIndex.hnsw(
            distance_metric=wvc.config.VectorDistances.COSINE,
        ),
        properties=[
            wvc.config.Property(name="text", data_type=wvc.config.DataType.TEXT),
            wvc.config.Property(name="pdf_name", data_type=wvc.config.DataType.TEXT),
            wvc.config.Property(name="pdf_type", data_type=wvc.config.DataType.TEXT),
            wvc.config.Property(name="lot_code", data_type=wvc.config.DataType.TEXT),
            wvc.config.Property(name="section", data_type=wvc.config.DataType.TEXT),
            wvc.config.Property(name="page_number", data_type=wvc.config.DataType.INT),
            wvc.config.Property(name="upload_batch_id", data_type=wvc.config.DataType.TEXT),
            wvc.config.Property(name="replaces", data_type=wvc.config.DataType.TEXT),
            wvc.config.Property(name="extracted_at", data_type=wvc.config.DataType.TEXT),
            wvc.config.Property(name="raw_json", data_type=wvc.config.DataType.TEXT),
        ],
    )
    logger.info("Created Weaviate collection: TakeOffs")


# ── Insert helpers ────────────────────────────────────────────────────────────

def _build_selection_sheet_object(
    page_result: dict,
    pdf_name: str,
    upload_batch_id: str,
    page_number: int,
) -> tuple[dict, list[float]]:
    extracted = page_result.get("extracted") or {}
    flat_text = page_result.get("flat_text", "")
    now = datetime.now(timezone.utc).isoformat()

    properties: dict[str, Any] = {
        "text": flat_text,
        "pdf_name": pdf_name,
        "pdf_type": "selection_sheet",
        "lot_code": detect_lot_code(extracted),
        "community": detect_community(extracted),
        "page_number": page_number,
        "section_name": str(extracted.get("section_name", "")),
        "upload_batch_id": upload_batch_id,
        "extracted_at": now,
        "raw_json": json.dumps(extracted, ensure_ascii=False),
    }
    return properties, page_result.get("embedding", [])


def _build_take_off_object(
    page_result: dict,
    pdf_name: str,
    upload_batch_id: str,
    page_number: int,
) -> tuple[dict, list[float]]:
    extracted = page_result.get("extracted") or {}
    flat_text = page_result.get("flat_text", "")
    now = datetime.now(timezone.utc).isoformat()

    replaces = extracted.get("replaces_logic", [])
    replaces_str = json.dumps(replaces, ensure_ascii=False) if replaces else ""

    properties: dict[str, Any] = {
        "text": flat_text,
        "pdf_name": pdf_name,
        "pdf_type": "take_off",
        "lot_code": detect_lot_code(extracted),
        "section": str(extracted.get("section", "")),
        "page_number": page_number,
        "upload_batch_id": upload_batch_id,
        "replaces": replaces_str,
        "extracted_at": now,
        "raw_json": json.dumps(extracted, ensure_ascii=False),
    }
    return properties, page_result.get("embedding", [])


# ── Public async API ──────────────────────────────────────────────────────────

async def store_pages(
    page_results: list[dict],
    pdf_name: str,
    pdf_type: str,
    upload_batch_id: str,
) -> dict:
    """
    Insert all pages into the appropriate Weaviate collection in parallel batches.

    Returns a summary dict with ``inserted`` and ``failed`` counts.
    """
    loop = asyncio.get_event_loop()

    def _sync_insert() -> dict:
        client = get_client()
        collection_name = "SelectionSheets" if pdf_type == "selection_sheet" else "TakeOffs"
        collection = client.collections.get(collection_name)

        inserted = 0
        failed = 0
        start = time.perf_counter()

        with collection.batch.dynamic() as batch:
            for idx, page_result in enumerate(page_results, start=1):
                try:
                    if pdf_type == "selection_sheet":
                        props, vector = _build_selection_sheet_object(
                            page_result, pdf_name, upload_batch_id, idx
                        )
                    else:
                        props, vector = _build_take_off_object(
                            page_result, pdf_name, upload_batch_id, idx
                        )

                    batch.add_object(properties=props, vector=vector if vector else None)
                    inserted += 1
                except Exception as exc:  # noqa: BLE001
                    logger.error("Failed to insert page %d: %s", idx, exc)
                    failed += 1

        elapsed = round(time.perf_counter() - start, 3)
        logger.info(
            "Stored %d/%d page(s) in Weaviate collection '%s' (%.3fs)",
            inserted,
            inserted + failed,
            collection_name,
            elapsed,
        )
        return {"inserted": inserted, "failed": failed, "elapsed": elapsed}

    return await loop.run_in_executor(None, _sync_insert)


async def get_collection_stats() -> dict:
    """Return total object counts for each collection."""
    loop = asyncio.get_event_loop()

    def _sync_stats() -> dict:
        client = get_client()
        stats: dict[str, int] = {}
        for name in ("SelectionSheets", "TakeOffs"):
            try:
                col = client.collections.get(name)
                agg = col.aggregate.over_all(total_count=True)
                stats[name] = agg.total_count or 0
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not fetch stats for %s: %s", name, exc)
                stats[name] = -1
        return stats

    return await loop.run_in_executor(None, _sync_stats)
