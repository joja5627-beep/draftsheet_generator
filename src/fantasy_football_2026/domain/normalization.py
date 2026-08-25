"""Shared normalization rules for player names and NFL team codes."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from fantasy_football_2026.constants import PLAYER_SUFFIXES, TEAM_CODE_ALIASES


def normalize_name(value: str) -> str:
    """Return the canonical ASCII comparison key for a player name."""

    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    tokens = re.findall(r"[a-z0-9]+", ascii_value.lower())
    while tokens and tokens[-1] in PLAYER_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def normalize_team(value: Any) -> str | None:
    """Return a current canonical NFL team abbreviation."""

    if value is None:
        return None
    team = str(value).strip().upper()
    if not team:
        return None
    return TEAM_CODE_ALIASES.get(team, team)
