"""
pdf_processor.py — Convert PDF pages to PNG images using pdf2image / poppler.

All public functions are async.  The CPU-bound pdf2image conversion runs in a
thread-pool executor so it does not block the event loop.
"""

import asyncio
import logging
import time
from pathlib import Path

import aiofiles
import aiofiles.os
from pdf2image import convert_from_path
from PIL import Image

from app.config import IMAGES_DIR, PDF_CONVERSION_DPI

logger = logging.getLogger(__name__)


async def convert_pdf_to_images(pdf_path: Path) -> dict:
    """
    Convert every page of *pdf_path* to a 300-DPI PNG image.

    Images are saved to:
        sentra-demo/output_images/{pdf_stem}/page_{n:04d}.png

    Returns a dict with:
        - pdf_name   : stem of the PDF file
        - pages      : list of absolute image paths (as strings)
        - page_times : time in seconds taken per page
        - total_time : total wall-clock conversion time
    """
    pdf_stem = pdf_path.stem
    output_dir: Path = IMAGES_DIR / pdf_stem
    await aiofiles.os.makedirs(str(output_dir), exist_ok=True)

    logger.info("Converting '%s' to images at %d DPI …", pdf_path.name, PDF_CONVERSION_DPI)
    total_start = time.perf_counter()

    # Run the blocking conversion in a thread pool so the event loop stays free
    loop = asyncio.get_event_loop()
    pages: list[Image.Image] = await loop.run_in_executor(
        None,
        lambda: convert_from_path(
            str(pdf_path),
            dpi=PDF_CONVERSION_DPI,
            fmt="png",
        ),
    )

    image_paths: list[str] = []
    page_times: list[float] = []

    for idx, page_image in enumerate(pages, start=1):
        page_start = time.perf_counter()
        image_path = output_dir / f"page_{idx:04d}.png"

        # Save the image in the executor as well (PIL save is blocking)
        await loop.run_in_executor(
            None,
            lambda img=page_image, path=image_path: img.save(str(path), "PNG"),
        )

        elapsed = time.perf_counter() - page_start
        page_times.append(round(elapsed, 3))
        image_paths.append(str(image_path))
        logger.debug("  Page %d saved in %.3fs → %s", idx, elapsed, image_path)

    total_time = round(time.perf_counter() - total_start, 3)
    logger.info(
        "Converted %d page(s) in %.3fs for '%s'",
        len(image_paths),
        total_time,
        pdf_path.name,
    )

    return {
        "pdf_name": pdf_stem,
        "pages": image_paths,
        "page_times": page_times,
        "total_time": total_time,
    }
