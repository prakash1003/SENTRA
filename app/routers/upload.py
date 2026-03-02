"""
upload.py — Multipart PDF upload endpoint and job status endpoint.
"""

import asyncio
import logging
import uuid
from pathlib import Path

import aiofiles
from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.config import UPLOADS_DIR
from app.services.embedder import embed_pages
from app.services.extractor import extract_pages, save_extracted_json
from app.services.pdf_processor import convert_pdf_to_images
from app.services.weaviate_store import store_pages

router = APIRouter()
logger = logging.getLogger(__name__)

# In-memory job registry (sufficient for a single-process service)
_jobs: dict[str, dict] = {}


# ── Helper ────────────────────────────────────────────────────────────────────

async def _save_upload(upload_file: UploadFile, dest: Path) -> None:
    """Persist an UploadFile to *dest* using async I/O."""
    content = await upload_file.read()
    async with aiofiles.open(str(dest), "wb") as fh:
        await fh.write(content)


# ── Pipeline ──────────────────────────────────────────────────────────────────

async def _process_single_pdf(
    pdf_path: Path,
    pdf_type: str,
    job_id: str,
    upload_batch_id: str,
) -> dict:
    """
    Run the full pipeline for a single PDF:
        1. Convert pages to images
        2. Extract structured data with Claude 3.7 Vision
        3. Create embeddings with text-embedding-3-small via LiteLLM
        4. Store in Weaviate

    Returns a summary dict for the PDF.
    """
    pdf_name = pdf_path.stem
    summary: dict = {"pdf_name": pdf_name, "status": "ok", "error": None}

    try:
        # 1. PDF → images
        conversion = await convert_pdf_to_images(pdf_path)
        image_paths: list[str] = conversion["pages"]
        summary["pages"] = len(image_paths)
        summary["conversion_time"] = conversion["total_time"]

        # 2. Vision extraction (parallel)
        extraction_results = await extract_pages(image_paths, pdf_type)
        await save_extracted_json(pdf_name, extraction_results)
        summary["extracted_pages"] = len(extraction_results)

        # 3. Embedding creation — text-embedding-3-small via LiteLLM (parallel)
        embedded_results = await embed_pages(extraction_results)

        # 4. Weaviate storage (parallel batch)
        store_summary = await store_pages(
            embedded_results,
            pdf_name=pdf_name,
            pdf_type=pdf_type,
            upload_batch_id=upload_batch_id,
        )
        summary["weaviate"] = store_summary

    except Exception as exc:  # noqa: BLE001
        logger.exception("Pipeline error for '%s': %s", pdf_name, exc)
        summary["status"] = "error"
        summary["error"] = str(exc)

    return summary


async def _run_job(
    job_id: str,
    pdf_paths: list[Path],
    pdf_type: str,
    upload_batch_id: str,
) -> None:
    """Background task: process all PDFs in parallel and update the job registry."""
    _jobs[job_id]["status"] = "processing"

    tasks = [
        _process_single_pdf(path, pdf_type, job_id, upload_batch_id)
        for path in pdf_paths
    ]
    results = await asyncio.gather(*tasks)

    _jobs[job_id]["status"] = "completed"
    _jobs[job_id]["results"] = results
    logger.info("Job %s completed — %d PDF(s) processed", job_id, len(results))


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/upload", summary="Upload one or multiple documents for processing")
async def upload_pdfs(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(
        ...,
        description="One or more documents to process (PDF, DOC, DOCX, XLS, XLSX)",
    ),
    pdf_type: str = Form(
        "selection_sheet",
        description="Document type: 'selection_sheet' (default) or 'take_off'",
    ),
) -> JSONResponse:
    """
    Accept one or more documents and kick off the async processing pipeline.

    - **files**: one or more files (PDF, DOC, DOCX, XLS, XLSX) via multipart/form-data
    - **pdf_type**: `selection_sheet` (default) or `take_off`
    """
    if pdf_type not in ("selection_sheet", "take_off"):
        raise HTTPException(
            status_code=422,
            detail="pdf_type must be 'selection_sheet' or 'take_off'",
        )
    if not files:
        raise HTTPException(status_code=422, detail="No files uploaded.")

    job_id = str(uuid.uuid4())
    upload_batch_id = job_id
    saved_paths: list[Path] = []

    for upload_file in files:
        filename = Path(upload_file.filename or "upload.bin").name
        dest = UPLOADS_DIR / f"{job_id}_{filename}"
        await _save_upload(upload_file, dest)
        saved_paths.append(dest)
        logger.info("Saved upload: %s", dest)

    _jobs[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "files": [p.name for p in saved_paths],
        "pdf_type": pdf_type,
        "results": [],
    }

    background_tasks.add_task(
        _run_job,
        job_id=job_id,
        pdf_paths=saved_paths,
        pdf_type=pdf_type,
        upload_batch_id=upload_batch_id,
    )

    return JSONResponse(
        status_code=202,
        content={
            "job_id": job_id,
            "status": "queued",
            "files": [f.filename for f in files],
            "message": "Processing started — use GET /status/{job_id} to poll progress.",
        },
    )


@router.get("/status/{job_id}", summary="Check job processing status")
async def get_status(job_id: str) -> JSONResponse:
    """Return the current status and results (if complete) for *job_id*."""
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return JSONResponse(content=job)
