"""
helpers.py — Utility functions: JSON flattening, lot code detection, community detection.
"""

import json
import re
from typing import Any


def flatten_json(data: Any, prefix: str = "") -> str:
    """
    Recursively flatten a JSON-serialisable object into a single searchable string.

    Each key-value pair is rendered as "key: value" on its own line so that the
    resulting text can be embedded or used as retrieval context.
    """
    lines: list[str] = []

    if isinstance(data, dict):
        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, (dict, list)):
                lines.append(flatten_json(value, prefix=full_key))
            else:
                lines.append(f"{full_key}: {value}")
    elif isinstance(data, list):
        for idx, item in enumerate(data):
            full_key = f"{prefix}[{idx}]"
            if isinstance(item, (dict, list)):
                lines.append(flatten_json(item, prefix=full_key))
            else:
                lines.append(f"{full_key}: {item}")
    else:
        lines.append(f"{prefix}: {data}")

    return "\n".join(lines)


def detect_lot_code(extracted: dict) -> str:
    """
    Attempt to extract a lot code from an already-extracted JSON dict.
    Returns an empty string when not found.
    """
    # Common key names where lot codes appear
    candidates = [
        "lot_code", "lot", "lot_number", "lot_no", "lot_id",
        "Lot Code", "Lot", "Lot Number",
    ]
    for key in candidates:
        value = extracted.get(key)
        if value:
            return str(value).strip()

    # Deep search — flatten and look for patterns like "Lot 42" or "L-042"
    flat = flatten_json(extracted)
    match = re.search(r"\blot[_ -]?(\w+)\b", flat, re.IGNORECASE)
    if match:
        return match.group(0).strip()

    return ""


def detect_community(extracted: dict) -> str:
    """
    Attempt to extract a community / subdivision name from an extracted JSON dict.
    Returns an empty string when not found.
    """
    candidates = [
        "community", "subdivision", "project", "development",
        "Community", "Subdivision", "Project",
    ]
    for key in candidates:
        value = extracted.get(key)
        if value:
            return str(value).strip()

    return ""


def safe_json_loads(text: str) -> dict:
    """
    Safely parse a JSON string.  If parsing fails, return a dict with the raw
    text stored under the "raw_text" key so callers always get a dict back.
    """
    # Strip markdown code fences that LLMs sometimes add
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {"raw_text": text}
