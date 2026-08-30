"""Validation, statistics, and quality grading of masked output."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

import pandas as pd

logger = logging.getLogger(__name__)

# Residual PHI patterns to check after masking
_RESIDUAL_PATTERNS: List[tuple[str, re.Pattern[str]]] = [
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("phone", re.compile(r"\b(\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    ("ip_address", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    (
        "credit_card",
        re.compile(r"\b(?:\d{4}[\s\-]?){3}\d{4}\b"),
    ),
    (
        "date_of_birth",
        re.compile(
            r"\b(?:0?[1-9]|1[0-2])[/\-](?:0?[1-9]|[12]\d|3[01])[/\-](?:19|20)\d{2}\b"
        ),
    ),
]

# Matches any existing mask tag like [PERSON] or [PHONE_NUMBER]
_MASK_TAG_RE = re.compile(r"\[[A-Z_]+\]")


def _text_is_inside_tag(text: str, match: re.Match[str]) -> bool:
    """Return True if a regex match falls entirely within a [TAG] span."""
    for tag_match in _MASK_TAG_RE.finditer(text):
        if tag_match.start() <= match.start() and match.end() <= tag_match.end():
            return True
    return False


def validate_residual_phi(
    df: pd.DataFrame,
) -> List[Dict[str, Any]]:
    """Scan masked Content for residual PHI patterns that were not caught by GLiNER.

    Matches that fall inside existing [TAG] spans are skipped.

    Args:
        df: DataFrame whose Content column has already been masked.

    Returns:
        A list of warning dicts, each containing:
            - row_index (int)
            - pattern_type (str)
            - matched_text (str)
    """
    warnings: List[Dict[str, Any]] = []

    for idx, text in enumerate(df["Content"]):
        if not isinstance(text, str):
            continue
        for pattern_type, pattern in _RESIDUAL_PATTERNS:
            for match in pattern.finditer(text):
                if _text_is_inside_tag(text, match):
                    continue
                warnings.append(
                    {
                        "row_index": idx,
                        "pattern_type": pattern_type,
                        "matched_text": match.group(),
                    }
                )

    logger.info("Residual PHI validation found %d potential issues", len(warnings))
    return warnings


def compute_statistics(
    df: pd.DataFrame,
    all_entities: List[List[Dict[str, Any]]],
    preprocessing_stats: Dict[str, int],
) -> Dict[str, Any]:
    """Compute processing statistics from the detected entities.

    Args:
        df: Masked DataFrame (used only for row count).
        all_entities: Per-row list of entity dicts from the masker.
        preprocessing_stats: Stats dict produced by the preprocessor.

    Returns:
        A dict with keys:
            total_rows_processed, rows_with_entities, rows_without_entities,
            total_entities_detected, entities_by_type,
            avg_confidence, min_confidence, max_confidence,
            preprocessing_stats.
    """
    total_rows = len(all_entities)
    rows_with = sum(1 for row in all_entities if row)
    rows_without = total_rows - rows_with

    entities_by_type: Dict[str, int] = {}
    all_scores: List[float] = []

    for row_entities in all_entities:
        for ent in row_entities:
            label = ent.get("label", "unknown")
            entities_by_type[label] = entities_by_type.get(label, 0) + 1
            score = ent.get("score")
            if score is not None:
                all_scores.append(float(score))

    total_entities = sum(entities_by_type.values())
    if not all_scores:
        # No entities detected — file is clean, award top grade
        avg_conf = 1.0
        min_conf = 1.0
        max_conf = 1.0
    else:
        avg_conf = sum(all_scores) / len(all_scores)
        min_conf = min(all_scores)
        max_conf = max(all_scores)

    return {
        "total_rows_processed": total_rows,
        "rows_with_entities": rows_with,
        "rows_without_entities": rows_without,
        "total_entities_detected": total_entities,
        "entities_by_type": entities_by_type,
        "avg_confidence": round(avg_conf, 4),
        "min_confidence": round(min_conf, 4),
        "max_confidence": round(max_conf, 4),
        "preprocessing_stats": preprocessing_stats,
    }


def compute_quality_grade(
    avg_confidence: float,
    validation_warnings: List[Dict[str, Any]],
    min_accuracy: float,
) -> Dict[str, Any]:
    """Assign a quality grade based on confidence and residual PHI warnings.

    Grading rubric:
        A — avg_confidence >= 0.85 and 0 warnings
        B — avg_confidence >= 0.70 and <= 2 warnings
        C — avg_confidence >= 0.55 and <= 5 warnings
        D — everything else

    Args:
        avg_confidence: Mean confidence score across all detected entities.
        validation_warnings: List of residual PHI warnings from validate_residual_phi.
        min_accuracy: The threshold that was configured for the run.

    Returns:
        A dict with keys: grade (str), threshold_used (float), passes (bool).
    """
    warning_count = len(validation_warnings)

    if avg_confidence >= 0.85 and warning_count == 0:
        grade = "A"
    elif avg_confidence >= 0.70 and warning_count <= 2:
        grade = "B"
    elif avg_confidence >= 0.55 and warning_count <= 5:
        grade = "C"
    else:
        grade = "D"

    passes = grade in {"A", "B"}
    logger.info(
        "Quality grade: %s (avg_confidence=%.4f, warnings=%d, passes=%s)",
        grade,
        avg_confidence,
        warning_count,
        passes,
    )
    return {
        "grade": grade,
        "threshold_used": min_accuracy,
        "passes": passes,
    }
