"""Shared bucket rules and coordinated colors for draft-sheet context values."""

from __future__ import annotations

import re
from typing import Final, Literal

Bucket = Literal["green", "yellow", "red"]

BUCKET_COLORS: Final[dict[Bucket, str]] = {
    "green": "#34785B",
    "yellow": "#956B1D",
    "red": "#A84F52",
}


def rank_bucket(value: object) -> Bucket:
    """Bucket a 1-32 rank, where lower is more favorable."""

    try:
        rank = int(str(value).strip())
    except (TypeError, ValueError):
        return "red"
    if 1 <= rank <= 10:
        return "green"
    if 11 <= rank <= 22:
        return "yellow"
    return "red"


def depth_chart_bucket(value: object) -> Bucket:
    """Bucket a depth-chart label by its trailing order number."""

    label = str(value).strip().upper()
    if label == "DST":
        return "green"
    match = re.search(r"(\d+)$", label)
    if match is None:
        return "red"
    order = int(match.group(1))
    if order == 1:
        return "green"
    if order == 2:
        return "yellow"
    return "red"


def injury_bucket(value: object) -> Bucket:
    """Bucket a projected regular-season weeks-missed label."""

    label = str(value).strip().upper()
    if label in {"--", "N/A"}:
        return "green"
    numbers = [int(number) for number in re.findall(r"\d+", label)]
    if not numbers:
        return "red"
    maximum = max(numbers)
    if maximum == 0:
        return "green"
    if maximum <= 2:
        return "yellow"
    return "red"


def context_bucket(column: str, value: object) -> Bucket:
    """Return the display bucket for a named PDF context column."""

    normalized_column = column.upper()
    if normalized_column == "DC":
        return depth_chart_bucket(value)
    if normalized_column == "INJ":
        return injury_bucket(value)
    return rank_bucket(value)
