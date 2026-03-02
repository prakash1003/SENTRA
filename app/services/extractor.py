"""
extractor.py — Vision LLM extraction via Claude 3.7 Sonnet (LiteLLM → AWS Bedrock).

Pages are processed in parallel batches to balance throughput against rate limits.
All public functions are async.
"""

import asyncio
import base64
import json
import logging
import time
from pathlib import Path

import aiofiles
import litellm

from app.config import (
    BEDROCK_MODEL,
    EXTRACTED_DIR,
    LLM_MAX_TOKENS,
    LLM_TEMPERATURE,
    MAX_CONCURRENT_EXTRACTIONS,
)
from app.utils.helpers import safe_json_loads

logger = logging.getLogger(__name__)

# ── Extraction prompts ────────────────────────────────────────────────────────

SELECTION_SHEET_PROMPT = """You are an expert document parser.
Extract ALL information from this Selection Sheet image into a structured JSON object.
Include:
- lot_info: lot number, address, phase, community
- purchaser: buyer name(s), contact information
- sale_info: sale date, contract number, base price, total price
- selected_options: list of all selected items, each with category, item name, description, price
- categories: list of unique category names present

Return ONLY valid JSON. No markdown fences, no explanation."""

TAKE_OFF_PROMPT = """You are an expert construction document parser.
Extract ALL information from this Take Off Sheet image into a structured JSON object.
Include:
- keys_and_legends: any colour codes, abbreviations, or legend entries
- column_headers: list of column names in the table(s)
- rows: list of all data rows, each containing all cell values keyed by column header
- replaces_logic: any "REPLACES" or substitution rules found (list of objects with from/to/condition)
- color_coding: any colour-coded rules or highlights explained
- section: section or trade name if identifiable

Return ONLY valid JSON. No markdown fences, no explanation."""


def _get_prompt(pdf_type: str) -> str:
    if pdf_type == "take_off":
        return TAKE_OFF_PROMPT
    return SELECTION_SHEET_PROMPT


# ── Core per-page extraction ──────────────────────────────────────────────────

async def _extract_single_page(
    image_path: str,
    pdf_type: str,
    semaphore: asyncio.Semaphore,
) -> dict:
    """
    Extract structured data from a single page image.

    Returns a dict with keys: page_path, extracted, tokens, cost, elapsed, error.
    """
    async with semaphore:
        start = time.perf_counter()
        # Read image bytes asynchronously
        async with aiofiles.open(image_path, "rb") as fh:
            image_bytes = await fh.read()

        b64_image = base64.standard_b64encode(image_bytes).decode("utf-8")
        prompt = _get_prompt(pdf_type)

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{b64_image}",
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ]

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: litellm.completion(
                    model=BEDROCK_MODEL,
                    messages=messages,
                    temperature=LLM_TEMPERATURE,
                    max_tokens=LLM_MAX_TOKENS,
                ),
            )
            raw_text: str = response.choices[0].message.content or ""
            extracted = safe_json_loads(raw_text)
            usage = response.usage or {}
            tokens = {
                "input": getattr(usage, "prompt_tokens", 0),
                "output": getattr(usage, "completion_tokens", 0),
            }
            cost = getattr(response, "_hidden_params", {}).get("response_cost", 0.0)
            error = None
        except Exception as exc:  # noqa: BLE001
            logger.error("Extraction failed for %s: %s", image_path, exc)
            extracted = {}
            tokens = {"input": 0, "output": 0}
            cost = 0.0
            error = str(exc)

        elapsed = round(time.perf_counter() - start, 3)
        logger.debug("Extracted page %s in %.3fs", image_path, elapsed)

        return {
            "page_path": image_path,
            "extracted": extracted,
            "tokens": tokens,
            "cost": cost,
            "elapsed": elapsed,
            "error": error,
        }


# ── Batch extraction ──────────────────────────────────────────────────────────

async def extract_pages(image_paths: list[str], pdf_type: str) -> list[dict]:
    """
    Extract all pages concurrently, respecting MAX_CONCURRENT_EXTRACTIONS.
    Returns a list of per-page result dicts (same order as input).
    """
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_EXTRACTIONS)
    tasks = [
        _extract_single_page(path, pdf_type, semaphore)
        for path in image_paths
    ]
    results = await asyncio.gather(*tasks)
    return list(results)


# ── Save extracted data ───────────────────────────────────────────────────────

async def save_extracted_json(pdf_name: str, results: list[dict]) -> str:
    """
    Persist extraction results to sentra-demo/extracted_data/{pdf_name}_extracted.json.
    Returns the file path as a string.
    """
    output_path = EXTRACTED_DIR / f"{pdf_name}_extracted.json"
    payload = json.dumps(results, indent=2, ensure_ascii=False)
    async with aiofiles.open(str(output_path), "w", encoding="utf-8") as fh:
        await fh.write(payload)
    logger.info("Saved extraction results → %s", output_path)
    return str(output_path)
