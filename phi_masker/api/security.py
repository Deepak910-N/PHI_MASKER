"""API key authentication dependency for PHI Masker."""

from __future__ import annotations

import os

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
_API_KEY = os.environ.get("PHI_MASKER_API_KEY", "")


def verify_api_key(api_key: str = Security(_API_KEY_HEADER)) -> None:
    """Raise HTTP 401 if the provided API key is missing or incorrect.

    Set the expected key via the PHI_MASKER_API_KEY environment variable.
    If the variable is not set, all requests are rejected.
    """
    if not _API_KEY:
        raise HTTPException(
            status_code=503,
            detail="API authentication is not configured. Set PHI_MASKER_API_KEY.",
        )
    if api_key != _API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key. Provide it as X-API-Key header.",
        )
