"""Parse entity labels from a Markdown file."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

_LIST_ITEM_RE = re.compile(r"^\s*[-*+]\s+(.+)$")
_NUMBERED_ITEM_RE = re.compile(r"^\s*\d+[.)]\s+(.+)$")
_MD_FORMAT_RE = re.compile(r"[*_`]")


def parse_labels(labels_file: str) -> List[str]:
    """Extract entity labels from a Markdown file.

    Only Markdown list items (lines starting with -, *, or +) are parsed.
    Headings and plain text are ignored. Labels are deduplicated while
    preserving their first-occurrence order and returned as lowercase strings.

    Args:
        labels_file: Path to the Markdown file containing entity labels.

    Returns:
        A deduplicated, order-preserving list of label strings.

    Raises:
        FileNotFoundError: If the labels file does not exist.
        ValueError: If no labels are found in the file.
    """
    path = Path(labels_file)
    if not path.exists():
        raise FileNotFoundError(f"Labels file not found: {labels_file}")

    seen: set[str] = set()
    labels: List[str] = []

    for line in path.read_text(encoding="utf-8").splitlines():
        match = _LIST_ITEM_RE.match(line) or _NUMBERED_ITEM_RE.match(line)
        if not match:
            continue
        label = _MD_FORMAT_RE.sub("", match.group(1)).strip().lower()
        if label and label not in seen:
            seen.add(label)
            labels.append(label)

    if not labels:
        raise ValueError(f"No entity labels found in '{labels_file}'")

    logger.debug("Parsed %d labels from '%s'", len(labels), labels_file)
    return labels
