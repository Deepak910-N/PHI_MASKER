"""Pydantic request/response models for the PHI Masker API."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class OutputFormat(str, Enum):
    """Supported output file formats."""

    parquet = "parquet"
    csv = "csv"
    json = "json"


class JobStatus(str, Enum):
    """Lifecycle states for an async processing job."""

    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class ProcessRequest(BaseModel):
    """Request body for the /process endpoint.

    Attributes:
        input_path: Path to the input parquet file (server-side path after upload).
        output_dir: Directory for the output file.
        labels_file: Path to the Markdown labels file.
        batch_size: Model inference batch size.
        min_accuracy: Confidence threshold for entity detection.
        entities: Optional list of entity types to restrict detection.
        output_format: Desired output format.
        log_level: Logging verbosity.
        async_mode: If True, returns immediately with a job_id.
    """

    input_path: str
    output_dir: str = "output"
    labels_file: str = "labels/default_labels.md"
    batch_size: int = Field(default=32, ge=1)
    min_accuracy: float = Field(default=0.7, ge=0.0, le=1.0)
    entities: Optional[List[str]] = None
    output_format: OutputFormat = OutputFormat.parquet
    log_level: str = "INFO"
    async_mode: bool = False


class JobResponse(BaseModel):
    """Response returned when an async job is created.

    Attributes:
        job_id: UUID identifying the job.
        status: Initial job status.
        message: Human-readable status message.
    """

    job_id: str
    status: JobStatus
    message: str


class JobStatusResponse(BaseModel):
    """Detailed status response for a specific job.

    Attributes:
        job_id: UUID of the job.
        status: Current lifecycle state.
        progress: Optional progress note.
        result: Full result dict if completed.
        error: Error message if failed.
    """

    job_id: str
    status: JobStatus
    progress: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class HealthResponse(BaseModel):
    """Health-check response.

    Attributes:
        status: Always "ok" when the service is running.
        version: API version string.
    """

    status: str
    version: str
