"""In-memory async job manager for the PHI Masker API."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from .schemas import JobStatus

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=4)

# In-memory store: job_id -> job record dict (capped at 200 entries)
_jobs: OrderedDict[str, Dict[str, Any]] = OrderedDict()
_MAX_JOBS = 200


def _new_job(config: Dict[str, Any]) -> str:
    """Create a new job record and return its ID.

    Evicts the oldest completed/failed job when the store exceeds _MAX_JOBS.

    Args:
        config: Serialised pipeline configuration dict.

    Returns:
        The UUID string for the new job.
    """
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "job_id": job_id,
        "status": JobStatus.queued,
        "config": config,
        "result": None,
        "error": None,
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    logger.debug("Created job %s", job_id)

    # Evict oldest finished jobs when over the cap
    if len(_jobs) > _MAX_JOBS:
        for eid, ejob in list(_jobs.items()):
            if ejob["status"] in (JobStatus.completed, JobStatus.failed):
                del _jobs[eid]
                logger.debug("Evicted old job %s from store", eid)
                break

    return job_id


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a job record by ID.

    Args:
        job_id: UUID of the job to retrieve.

    Returns:
        The job dict, or None if not found.
    """
    return _jobs.get(job_id)


def list_jobs() -> List[Dict[str, Any]]:
    """Return all job records ordered by creation time (oldest first).

    Returns:
        List of job dicts.
    """
    return sorted(_jobs.values(), key=lambda j: j["created_at"])


def run_sync(pipeline_fn: Callable[[], Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """Run the pipeline synchronously and return the result.

    Args:
        pipeline_fn: Zero-argument callable that executes the pipeline and returns a
            result dict.
        config: Serialised config stored with the job (for record-keeping only).

    Returns:
        The result dict from the pipeline.
    """
    job_id = _new_job(config)
    _jobs[job_id]["status"] = JobStatus.processing
    try:
        result = pipeline_fn()
        _jobs[job_id]["status"] = JobStatus.completed
        _jobs[job_id]["result"] = result
        logger.info("Job %s completed synchronously", job_id)
        return result
    except Exception as exc:
        _jobs[job_id]["status"] = JobStatus.failed
        _jobs[job_id]["error"] = str(exc)
        logger.error("Job %s failed: %s", job_id, exc, exc_info=True)
        raise


async def run_async(
    pipeline_fn: Callable[[], Any], config: Dict[str, Any]
) -> str:
    """Submit the pipeline to the thread-pool executor and return the job ID.

    The pipeline runs in a background thread. Job status is updated on
    completion or failure.

    Args:
        pipeline_fn: Zero-argument callable that executes the pipeline.
        config: Serialised config stored with the job.

    Returns:
        The UUID string for the created job.
    """
    job_id = _new_job(config)
    loop = asyncio.get_running_loop()

    def _run() -> None:
        _jobs[job_id]["status"] = JobStatus.processing
        try:
            result = pipeline_fn()
            _jobs[job_id]["status"] = JobStatus.completed
            _jobs[job_id]["result"] = result
            logger.info("Async job %s completed", job_id)
        except Exception as exc:
            _jobs[job_id]["status"] = JobStatus.failed
            _jobs[job_id]["error"] = str(exc)
            logger.error("Async job %s failed: %s", job_id, exc, exc_info=True)

    loop.run_in_executor(_executor, _run)
    logger.debug("Async job %s queued", job_id)
    return job_id
