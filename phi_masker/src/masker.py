"""GLiNER model loading, entity detection, and text masking."""

from __future__ import annotations

import logging
import os
import warnings
from typing import Any, Dict, List, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

# Suppress HuggingFace/tqdm noise — progress bars and deprecation warnings
# from huggingface_hub and tokenizers are informational only and clutter the CLI.
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

warnings.filterwarnings("ignore", category=Warning, module="urllib3")
warnings.filterwarnings("ignore", message=".*NotOpenSSLWarning.*")
warnings.filterwarnings("ignore", message=".*resume_download.*")


def _load_model() -> Any:
    """Load the nvidia/gliner-PII model from HuggingFace via gliner.

    Returns:
        A loaded GLiNER model instance.

    Raises:
        ImportError: If the gliner package is not installed.
        RuntimeError: If the model fails to load.
    """
    try:
        from gliner import GLiNER  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "The 'gliner' package is required. Install it with: pip install gliner"
        ) from exc

    logger.info("Loading model 'nvidia/gliner-PII' — this may take a moment…")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = GLiNER.from_pretrained("nvidia/gliner-PII")
    except Exception as exc:
        raise RuntimeError(f"Failed to load nvidia/gliner-PII: {exc}") from exc

    logger.info("Model loaded successfully")
    return model


def _mask_text(text: str, entities: List[Dict[str, Any]]) -> str:
    """Replace detected entity spans with [ENTITY_TYPE] tags.

    Entities are applied in reverse start-position order so that earlier
    character offsets are not shifted by replacements that follow them.

    Args:
        text: Original text string.
        entities: List of entity dicts with keys: text, label, score, start, end.

    Returns:
        The masked text with all entity spans replaced.
    """
    sorted_entities = sorted(entities, key=lambda e: e["start"], reverse=True)
    for entity in sorted_entities:
        tag = "[" + entity["label"].upper().replace(" ", "_") + "]"
        text = text[: entity["start"]] + tag + text[entity["end"] :]
    return text


def run_masking(
    df: pd.DataFrame,
    labels: List[str],
    batch_size: int,
    min_accuracy: float,
) -> Tuple[pd.DataFrame, List[List[Dict[str, Any]]]]:
    """Detect PHI entities and mask the Content column.

    Processes rows in batches for efficiency. For each row the original
    Content is replaced with the masked version. Per-row entity lists
    are returned alongside the modified DataFrame for reporting.

    Args:
        df: Preprocessed DataFrame with a 'Content' column.
        labels: List of entity type strings to detect.
        batch_size: Number of rows per model inference batch.
        min_accuracy: Confidence threshold; entities below this score are ignored.

    Returns:
        A tuple of:
            - DataFrame with the Content column replaced by masked text.
            - List (one entry per row) of entity dicts detected in that row.
    """
    model = _load_model()

    texts = df["Content"].tolist()
    total = len(texts)
    all_entities: List[List[Dict[str, Any]]] = []
    masked_texts: List[str] = []

    logger.info(
        "Starting entity detection — %d rows, batch_size=%d, threshold=%.2f",
        total,
        batch_size,
        min_accuracy,
    )

    for batch_start in range(0, total, batch_size):
        batch_texts = texts[batch_start : batch_start + batch_size]
        batch_num = batch_start // batch_size + 1
        logger.debug(
            "Processing batch %d (%d–%d of %d)",
            batch_num,
            batch_start + 1,
            min(batch_start + batch_size, total),
            total,
        )

        for text in batch_texts:
            try:
                raw_entities: List[Dict[str, Any]] = model.predict_entities(
                    text, labels, threshold=min_accuracy
                )
            except Exception as exc:
                logger.warning("Entity detection failed for a row: %s", exc)
                raw_entities = []

            all_entities.append(raw_entities)
            masked_texts.append(_mask_text(text, raw_entities))

    df_out = df.copy()
    df_out["Content"] = masked_texts

    entities_found = sum(len(e) for e in all_entities)
    logger.info(
        "Masking complete — %d entities detected across %d rows",
        entities_found,
        total,
    )
    return df_out, all_entities
