"""Click CLI entry point for PHI Masker."""

from __future__ import annotations

import json
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import click

from src.config import PipelineConfig
from src.pipeline import PHIMaskingPipeline

logger = logging.getLogger(__name__)

_watch_executor = ThreadPoolExecutor(max_workers=2)


def _run_pipeline(path: str, **kwargs) -> None:
    try:
        config = PipelineConfig(input_path=path, **kwargs)
    except ValueError as exc:
        logger.error("Config error for %s: %s", path, exc)
        return
    result = PHIMaskingPipeline(config).run()
    status = result.get("status")
    if status == "success":
        logger.info("Done: %s -> %s", path, result.get("output_file"))
    elif status == "skipped":
        logger.info("Skipped (already processed): %s", path)
    else:
        logger.error("Failed: %s — %s", path, result.get("error"))


@click.group()
def cli() -> None:
    """PHI Masker — detect and mask PHI/PII entities in parquet files."""


@cli.command("mask")
@click.option(
    "--input", "-i",
    "input_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to the input parquet file.",
)
@click.option(
    "--output-dir", "-o",
    default="output",
    show_default=True,
    type=click.Path(),
    help="Directory for the masked output file.",
)
@click.option(
    "--labels", "-l",
    "labels_file",
    default="labels/default_labels.md",
    show_default=True,
    type=click.Path(),
    help="Path to the Markdown labels file.",
)
@click.option(
    "--batch-size", "-b",
    default=32,
    show_default=True,
    type=int,
    help="Number of rows per model inference batch.",
)
@click.option(
    "--min-accuracy", "-a",
    default=0.7,
    show_default=True,
    type=float,
    help="Minimum confidence threshold for entity detection (0.0–1.0).",
)
@click.option(
    "--entities", "-e",
    multiple=True,
    default=None,
    help="Restrict detection to these entity types (repeatable).",
)
@click.option(
    "--output-format", "-f",
    "output_format",
    default="parquet",
    show_default=True,
    type=click.Choice(["parquet", "csv", "json"], case_sensitive=False),
    help="Output file format.",
)
@click.option(
    "--log-level",
    default="INFO",
    show_default=True,
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    help="Logging verbosity.",
)
@click.option(
    "--force", "-F",
    is_flag=True,
    default=False,
    help="Reprocess even if this file was already successfully processed.",
)
def mask(
    input_path: str,
    output_dir: str,
    labels_file: str,
    batch_size: int,
    min_accuracy: float,
    entities: tuple,
    output_format: str,
    log_level: str,
    force: bool,
) -> None:
    """Run the PHI masking pipeline and print a JSON summary to stdout."""
    try:
        config = PipelineConfig(
            input_path=input_path,
            output_dir=output_dir,
            labels_file=labels_file,
            batch_size=batch_size,
            min_accuracy=min_accuracy,
            entities=list(entities) if entities else None,
            output_format=output_format.lower(),
            log_level=log_level.upper(),
            force=force,
        )
    except ValueError as exc:
        click.echo(f"Configuration error: {exc}", err=True)
        sys.exit(1)

    pipeline = PHIMaskingPipeline(config)
    result = pipeline.run()

    click.echo(json.dumps(result, indent=2, default=str))

    if result.get("status") == "error":
        sys.exit(1)


@cli.command("serve")
@click.option(
    "--host",
    default="0.0.0.0",
    show_default=True,
    help="Host address to bind the server to.",
)
@click.option(
    "--port",
    default=8000,
    show_default=True,
    type=int,
    help="Port to listen on.",
)
@click.option(
    "--reload",
    is_flag=True,
    default=False,
    help="Enable uvicorn auto-reload (development only).",
)
def serve(host: str, port: int, reload: bool) -> None:
    """Start the PHI Masker FastAPI server."""
    try:
        import uvicorn
    except ImportError:
        click.echo("uvicorn is required. Install it with: pip install uvicorn", err=True)
        sys.exit(1)

    click.echo(f"Starting PHI Masker API on http://{host}:{port}")
    uvicorn.run(
        "api.app:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


@cli.command("watch")
@click.option(
    "--input-dir", "-i",
    default="input",
    show_default=True,
    type=click.Path(file_okay=False),
    help="Directory to watch for parquet files.",
)
@click.option("--output-dir", "-o", default="output", show_default=True, type=click.Path())
@click.option(
    "--labels", "-l",
    "labels_file",
    default="labels/default_labels.md",
    show_default=True,
    type=click.Path(),
)
@click.option("--batch-size", "-b", default=32, show_default=True, type=int)
@click.option("--min-accuracy", "-a", default=0.7, show_default=True, type=float)
@click.option(
    "--output-format", "-f",
    "output_format",
    default="parquet",
    show_default=True,
    type=click.Choice(["parquet", "csv", "json"], case_sensitive=False),
)
@click.option(
    "--log-level",
    default="INFO",
    show_default=True,
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
)
def watch(
    input_dir: str,
    output_dir: str,
    labels_file: str,
    batch_size: int,
    min_accuracy: float,
    output_format: str,
    log_level: str,
) -> None:
    """Watch a directory and auto-run the pipeline on new parquet files."""
    import time

    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        click.echo("watchdog is required. Install it with: pip install watchdog", err=True)
        sys.exit(1)

    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    os.makedirs(input_dir, exist_ok=True)
    pipeline_kwargs = dict(
        output_dir=output_dir,
        labels_file=labels_file,
        batch_size=batch_size,
        min_accuracy=min_accuracy,
        output_format=output_format.lower(),
        log_level=log_level.upper(),
    )

    class ParquetHandler(FileSystemEventHandler):
        def _handle(self, path: str) -> None:
            if path.endswith(".parquet"):
                logger.info("Detected: %s", path)
                _watch_executor.submit(_run_pipeline, path, **pipeline_kwargs)

        def on_created(self, event) -> None:
            if not event.is_directory:
                self._handle(event.src_path)

        def on_moved(self, event) -> None:
            if not event.is_directory:
                self._handle(event.dest_path)

    observer = Observer()
    observer.schedule(ParquetHandler(), input_dir, recursive=False)
    observer.start()
    click.echo(f"Watching '{input_dir}' for parquet files. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    cli()
