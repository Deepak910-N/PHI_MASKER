"""FastAPI application factory for the PHI Masker service."""

from __future__ import annotations

from fastapi import FastAPI

from .routes import router

APP_VERSION = "1.0.0"


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        A fully configured FastAPI instance with all routes registered.
    """
    app = FastAPI(
        title="PHI Masker API",
        description=(
            "Production-grade API for detecting and masking PHI/PII entities "
            "in parquet files using the nvidia/gliner-PII model."
        ),
        version=APP_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.include_router(router, prefix="/api/v1")

    @app.get("/", tags=["system"])
    async def root():
        """Root endpoint returning application metadata."""
        return {
            "app": "PHI Masker API",
            "version": APP_VERSION,
            "docs": "/docs",
        }

    return app


app = create_app()
