"""All API endpoints for the PHI Masker service."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ..src.config import PipelineConfig
from ..src.pipeline import PHIMaskingPipeline
from . import tasks
from .schemas import (
    HealthResponse,
    JobResponse,
    JobStatus,
    JobStatusResponse,
    ProcessRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter()

API_VERSION = "1.0.0"
INPUT_DIR = "input"


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@router.get("/health", response_model=HealthResponse, tags=["system"])
async def health() -> HealthResponse:
    """Return service health status and version.

    Returns:
        HealthResponse with status "ok" and the current API version.
    """
    return HealthResponse(status="ok", version=API_VERSION)


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


@router.post("/upload", tags=["files"])
async def upload_file(file: UploadFile = File(...)) -> Dict[str, str]:
    """Accept a .parquet file upload and save it to the input directory.

    Args:
        file: The uploaded file; must have a .parquet extension.

    Returns:
        A dict with the saved server-side path.

    Raises:
        HTTPException 400: If the file does not have a .parquet extension.
    """
    if not (file.filename or "").endswith(".parquet"):
        raise HTTPException(
            status_code=400,
            detail="Only .parquet files are accepted",
        )

    os.makedirs(INPUT_DIR, exist_ok=True)
    dest = os.path.join(INPUT_DIR, file.filename)

    content = await file.read()
    with open(dest, "wb") as fh:
        fh.write(content)

    logger.info("Uploaded file saved to: %s", dest)
    return {"saved_path": dest, "filename": file.filename}


# ---------------------------------------------------------------------------
# Process
# ---------------------------------------------------------------------------


@router.post("/process", tags=["processing"])
async def process(request: ProcessRequest) -> Any:
    """Run the PHI masking pipeline.

    If async_mode is True, the job is submitted to the background thread pool
    and the endpoint returns immediately with a job_id. Otherwise the pipeline
    runs synchronously and the full result is returned.

    Args:
        request: ProcessRequest body with pipeline configuration.

    Returns:
        JobResponse (async) or the full result dict (sync).

    Raises:
        HTTPException 422: If the configuration is invalid.
        HTTPException 500: If the synchronous pipeline raises an exception.
    """
    try:
        config = PipelineConfig(
            input_path=request.input_path,
            output_dir=request.output_dir,
            labels_file=request.labels_file,
            batch_size=request.batch_size,
            min_accuracy=request.min_accuracy,
            entities=request.entities,
            output_format=request.output_format.value,
            log_level=request.log_level,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    config_dict = request.model_dump()

    def _run_pipeline() -> Dict[str, Any]:
        return PHIMaskingPipeline(config).run()

    if request.async_mode:
        job_id = await tasks.run_async(_run_pipeline, config_dict)
        return JobResponse(
            job_id=job_id,
            status=JobStatus.queued,
            message=f"Job {job_id} queued for processing",
        )

    try:
        result = tasks.run_sync(_run_pipeline, config_dict)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return result


# ---------------------------------------------------------------------------
# Job status / results
# ---------------------------------------------------------------------------


@router.get("/status/{job_id}", response_model=JobStatusResponse, tags=["jobs"])
async def job_status(job_id: str) -> JobStatusResponse:
    """Return current status for a job.

    Args:
        job_id: UUID of the job.

    Returns:
        JobStatusResponse with current status, result (if complete), or error.

    Raises:
        HTTPException 404: If the job ID is not found.
    """
    job = tasks.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    return JobStatusResponse(
        job_id=job["job_id"],
        status=job["status"],
        progress=None,
        result=job.get("result"),
        error=job.get("error"),
    )


@router.get("/results/{job_id}", tags=["jobs"])
async def job_results(job_id: str) -> FileResponse:
    """Download the masked output file for a completed job.

    Args:
        job_id: UUID of the completed job.

    Returns:
        FileResponse streaming the masked output file.

    Raises:
        HTTPException 404: If the job is not found or not yet complete.
        HTTPException 400: If the job failed or has no output file.
    """
    job = tasks.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    if job["status"] != JobStatus.completed:
        raise HTTPException(
            status_code=400,
            detail=f"Job '{job_id}' is not complete (status: {job['status']})",
        )

    result = job.get("result") or {}
    output_file = result.get("output_file")
    if not output_file or not Path(output_file).exists():
        raise HTTPException(
            status_code=404,
            detail=f"Output file for job '{job_id}' not found on disk",
        )

    return FileResponse(
        path=output_file,
        filename=Path(output_file).name,
        media_type="application/octet-stream",
    )


@router.get("/report/{job_id}", tags=["jobs"])
async def job_report(job_id: str) -> Dict[str, Any]:
    """Return the full statistics and quality report for a completed job.

    Args:
        job_id: UUID of the completed job.

    Returns:
        The statistics and quality_check sections from the pipeline result.

    Raises:
        HTTPException 404: If the job is not found or not yet complete.
    """
    job = tasks.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    if job["status"] != JobStatus.completed:
        raise HTTPException(
            status_code=400,
            detail=f"Job '{job_id}' is not complete (status: {job['status']})",
        )

    result = job.get("result") or {}
    return {
        "job_id": job_id,
        "statistics": result.get("statistics", {}),
        "quality_check": result.get("quality_check", {}),
        "labels_used": result.get("labels_used", []),
        "processing_time_seconds": result.get("processing_time_seconds"),
    }


@router.get("/jobs", tags=["jobs"])
async def list_jobs() -> List[Dict[str, Any]]:
    """List all jobs with their current status and metadata.

    Returns:
        List of job summary dicts, ordered by creation time.
    """
    return [
        {
            "job_id": j["job_id"],
            "status": j["status"],
            "created_at": j["created_at"],
            "has_result": j.get("result") is not None,
            "error": j.get("error"),
        }
        for j in tasks.list_jobs()
    ]
