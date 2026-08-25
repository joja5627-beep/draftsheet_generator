"""Shared source ingestion and normalization for publisher consensus builders."""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from fantasy_football_2026.constants import PLAYER_NAME_ALIASES
from fantasy_football_2026.domain.normalization import normalize_name
from fantasy_football_2026.errors import FantasyFootballError, InjuryContextError, StorageError
from fantasy_football_2026.infrastructure.storage import load_json_object
from fantasy_football_2026.infrastructure.web import CachedWebClient, CachePolicy


@dataclass(frozen=True, slots=True)
class ConsensusSource:
    source_id: str
    family: str
    url: str
    mode: str
    players: tuple[str, ...]
    required: bool


@dataclass(frozen=True, slots=True)
class SourceObservation:
    source_id: str
    family: str
    url: str
    retrieved_at: str | None
    from_cache: bool
    players: tuple[str, ...]
    status: str
    error: str | None


class _ArticleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._heading_depth = 0
        self._heading_parts: list[str] = []
        self.headings: list[str] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag in {"h2", "h3", "h4"}:
            self._heading_depth += 1
            if self._heading_depth == 1:
                self._heading_parts = []

    def handle_data(self, data: str) -> None:
        cleaned = " ".join(data.split())
        if not cleaned:
            return
        self.text_parts.append(cleaned)
        if self._heading_depth:
            self._heading_parts.append(cleaned)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"h2", "h3", "h4"} and self._heading_depth:
            self._heading_depth -= 1
            if self._heading_depth == 0 and self._heading_parts:
                self.headings.append(" ".join(self._heading_parts))


class CachedArticleClient:
    """Article-specific adapter over the shared cached web client."""

    def __init__(
        self,
        *,
        cache_dir: Path,
        refresh: bool,
        offline: bool,
        timeout: float,
    ) -> None:
        self.cache_dir = cache_dir
        self._client = CachedWebClient(
            CachePolicy(
                refresh=refresh,
                offline=offline,
                timeout=timeout,
                stale_if_error=True,
            )
        )

    def fetch(self, source: ConsensusSource) -> tuple[str, str, bool]:
        try:
            result = self._client.fetch_text(
                name=source.source_id,
                url=source.url,
                cache_path=self.cache_dir / f"{source.source_id}.html",
            )
        except FantasyFootballError as error:
            raise InjuryContextError(str(error)) from error
        return result.payload, result.retrieved_at, result.from_cache


class ArticleCandidateExtractor:
    """Extract player-name endorsements from headings or verified explicit lists."""

    def __init__(self, player_names: tuple[str, ...]) -> None:
        self.player_names = player_names

    def extract(self, source: ConsensusSource, html: str) -> tuple[str, ...]:
        parser = _ArticleParser()
        parser.feed(html)
        haystacks = parser.headings if source.mode == "headings" else parser.text_parts
        normalized = " | ".join(normalize_name(value) for value in haystacks)
        candidates = source.players if source.players else self.player_names
        found = [
            name
            for name in candidates
            if any(variant in normalized for variant in self._variants(name))
        ]
        return tuple(dict.fromkeys(found))

    @staticmethod
    def _variants(name: str) -> tuple[str, ...]:
        normalized = normalize_name(name)
        alias = PLAYER_NAME_ALIASES.get(normalized)
        reverse = next(
            (short for short, full in PLAYER_NAME_ALIASES.items() if full == normalized),
            None,
        )
        return tuple(value for value in (normalized, alias, reverse) if value)


class ConsensusBuilderSupport:
    """Reusable parsing and normalization behavior shared by consensus builders."""

    @staticmethod
    def _load(path: Path) -> dict[str, Any]:
        try:
            return load_json_object(path)
        except StorageError as error:
            raise InjuryContextError(str(error)) from error

    @staticmethod
    def _sources(
        catalog: dict[str, Any],
        *,
        default_mode: str,
        include_players: bool,
        catalog_name: str,
    ) -> tuple[ConsensusSource, ...]:
        try:
            return tuple(
                ConsensusSource(
                    source_id=str(item["id"]),
                    family=str(item["family"]),
                    url=str(item["url"]),
                    mode=str(item.get("mode", default_mode)),
                    players=(
                        tuple(str(name) for name in item.get("players", []))
                        if include_players
                        else ()
                    ),
                    required=bool(item.get("required", False)),
                )
                for item in catalog["sources"]
            )
        except (KeyError, TypeError) as error:
            raise InjuryContextError(f"Invalid {catalog_name} source catalog: {error}") from error

    @staticmethod
    def _name_index(players: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return {normalize_name(player.get("name")): player for player in players}

    @staticmethod
    def _resolve_name(value: Any, canonical: dict[str, str]) -> str | None:
        normalized = normalize_name(value)
        if normalized in canonical:
            return normalized
        alias = PLAYER_NAME_ALIASES.get(normalized)
        if alias in canonical:
            return str(alias)
        reverse = next(
            (short for short, full in PLAYER_NAME_ALIASES.items() if full == normalized),
            None,
        )
        return reverse if reverse in canonical else None

    @staticmethod
    def _injury_max(label: str) -> int:
        values = [int(value) for value in re.findall(r"\d+", label)]
        return max(values, default=0)

    @staticmethod
    def _optional_float(value: Any) -> float | None:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None
