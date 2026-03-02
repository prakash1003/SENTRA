"""
config.py — Load environment variables and application settings.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
load_dotenv()

# ── AWS / Bedrock ──────────────────────────────────────────────────────────────
AWS_ACCESS_KEY_ID: str = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY: str = os.getenv("AWS_SECRET_ACCESS_KEY", "")
AWS_REGION_NAME: str = os.getenv("AWS_REGION_NAME", "us-east-1")

# ── Model IDs ─────────────────────────────────────────────────────────────────
BEDROCK_MODEL: str = os.getenv(
    "BEDROCK_MODEL",
    "bedrock/us.anthropic.claude-3-7-sonnet-20250219-v1:0",
)
EMBED_MODEL: str = os.getenv(
    "EMBED_MODEL",
    "bedrock/amazon.titan-embed-text-v2:0",
)
EMBED_DIMENSIONS: int = int(os.getenv("EMBED_DIMENSIONS", "1024"))

# ── Concurrency ───────────────────────────────────────────────────────────────
MAX_CONCURRENT_EXTRACTIONS: int = int(os.getenv("MAX_CONCURRENT_EXTRACTIONS", "5"))
MAX_CONCURRENT_EMBEDDINGS: int = int(os.getenv("MAX_CONCURRENT_EMBEDDINGS", "10"))

# ── Server ────────────────────────────────────────────────────────────────────
SERVER_PORT: int = int(os.getenv("SERVER_PORT", "7861"))

# ── Storage paths ─────────────────────────────────────────────────────────────
BASE_DIR: Path = Path("sentra-demo")
UPLOADS_DIR: Path = BASE_DIR / "uploads"
IMAGES_DIR: Path = BASE_DIR / "output_images"
EXTRACTED_DIR: Path = BASE_DIR / "extracted_data"

# Create directories at import time so they are always available
for _dir in (UPLOADS_DIR, IMAGES_DIR, EXTRACTED_DIR):
    _dir.mkdir(parents=True, exist_ok=True)

# ── LLM extraction settings ───────────────────────────────────────────────────
LLM_TEMPERATURE: float = 0.0
LLM_MAX_TOKENS: int = 4096
PDF_CONVERSION_DPI: int = 300
