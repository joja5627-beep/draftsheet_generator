"""Build a multi-source market and baseline ranking context."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from fantasy_football_2026.constants import (
    DEFAULT_SOURCE_PDF,
    DEFAULT_TIMEOUT_SECONDS,
    PLAYER_NAME_ALIASES,
    TOTAL_RANKED_PLAYERS,
    ContextFile,
    DirectoryName,
    SourceUrl,
)
from fantasy_football_2026.domain.normalization import normalize_name, normalize_team
from fantasy_football_2026.errors import FantasyFootballError, InjuryContextError
from fantasy_football_2026.infrastructure.storage import write_json, write_text
from fantasy_football_2026.infrastructure.web import CachedWebClient, CachePolicy
from fantasy_football_2026.sources.injuries import RankedEntity, extract_ranked_entities

FFTODAY_URL = SourceUrl.FFTODAY_HALF_PPR
FANTASYPROS_URL = SourceUrl.FANTASYPROS_HALF_PPR
ESPN_SOURCE_URL = SourceUrl.ESPN_TOP_300

SOURCE_WEIGHTS = {"espn": 0.30, "fantasypros": 0.50, "fftoday": 0.20}

# The ESPN sheet occasionally uses common short forms while market feeds retain a
# player's full given name. Keep these narrow and explicit so a nickname cannot
# accidentally match a different player.
MARKET_NAME_ALIASES = PLAYER_NAME_ALIASES


@dataclass(frozen=True, slots=True)
class MarketPlayer:
    source_rank: int
    name: str
    team: str
    position: str
    position_rank: str
    bye_week: int | None
    espn_rank: int
    fantasypros_rank: int | None
    fantasypros_position_rank: str | None
    fantasypros_tier: int | None
    fantasypros_expert_count: int | None
    fftoday_rank: int | None
    fftoday_adp: float | None
    fftoday_position_rank: int | None
    consensus_rank: float
    source_count: int
    match_quality: str


class _FFTodayParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._table_depth = 0
        self._in_target = False
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self.rows: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "table":
            if self._in_target:
                self._table_depth += 1
            elif attributes.get("id") == "myTable":
                self._in_target = True
                self._table_depth = 1
        elif self._in_target and tag == "tr":
            self._row = []
        elif self._in_target and tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._in_target and tag in {"td", "th"} and self._cell is not None:
            assert self._row is not None
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif self._in_target and tag == "tr" and self._row is not None:
            if len(self._row) == 8 and self._row[0].isdigit():
                self.rows.append(self._row)
            self._row = None
        elif self._in_target and tag == "table":
            self._table_depth -= 1
            if self._table_depth == 0:
                self._in_target = False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build multi-source draft market context.")
    parser.add_argument("--pdf", type=Path, default=Path(DEFAULT_SOURCE_PDF))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(DirectoryName.CONTEXT, ContextFile.MARKET_MARKDOWN),
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=Path(DirectoryName.CONTEXT, ContextFile.MARKET_JSON),
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path(DirectoryName.CONTEXT, DirectoryName.CACHE),
    )
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = update_market_context(
        pdf_path=args.pdf,
        markdown_path=args.output,
        json_path=args.json_output,
        cache_dir=args.cache_dir,
        refresh=args.refresh,
        offline=args.offline,
        timeout=args.timeout,
    )
    print(f"Market rows: {result['player_count']}")
    print(f"Three-source rows: {result['three_source_count']}")
    print(f"Markdown: {Path(result['markdown_path']).resolve()}")
    print(f"JSON: {Path(result['json_path']).resolve()}")
    return 0


def update_market_context(
    *,
    pdf_path: Path,
    markdown_path: Path,
    json_path: Path,
    cache_dir: Path,
    refresh: bool,
    offline: bool,
    timeout: float,
) -> dict[str, Any]:
    entities = extract_ranked_entities(pdf_path)
    if len(entities) != TOTAL_RANKED_PLAYERS:
        raise InjuryContextError(
            f"Expected {TOTAL_RANKED_PLAYERS} ranked entities, extracted {len(entities)}."
        )

    fftoday_html, fftoday_meta = _fetch_html(
        name="fftoday_half_ppr_adp",
        url=FFTODAY_URL,
        cache_dir=cache_dir,
        refresh=refresh,
        offline=offline,
        timeout=timeout,
    )
    fantasypros_html, fantasypros_meta = _fetch_html(
        name="fantasypros_half_ppr",
        url=FANTASYPROS_URL,
        cache_dir=cache_dir,
        refresh=refresh,
        offline=offline,
        timeout=timeout,
    )
    fftoday = parse_fftoday(fftoday_html)
    fantasypros, fp_metadata = parse_fantasypros(fantasypros_html)
    players = build_market_players(entities, fftoday, fantasypros, fp_metadata)
    now = datetime.now(UTC)
    metadata = {
        "generated_at": now.isoformat(timespec="seconds"),
        "effective_date": now.date().isoformat(),
        "source_pdf": str(pdf_path),
        "source_weights": SOURCE_WEIGHTS,
        "method": (
            "Consensus rank is a weighted mean of ESPN PPR rank (30%), FantasyPros "
            "half-PPR expert consensus (50%), and FFToday half-PPR ADP (20%). Missing "
            "sources are omitted and remaining weights are renormalized."
        ),
        "sources": {
            "espn": {"url": ESPN_SOURCE_URL, "role": "projection baseline"},
            "fantasypros": {
                "url": FANTASYPROS_URL,
                "role": "multi-expert half-PPR consensus",
                "retrieved_at": fantasypros_meta["retrieved_at"],
                "from_cache": fantasypros_meta["from_cache"],
                "expert_count": fp_metadata.get("total_experts"),
                "source_updated": fp_metadata.get("last_updated"),
            },
            "fftoday": {
                "url": FFTODAY_URL,
                "role": "half-PPR market ADP from Underdog and Yahoo",
                "retrieved_at": fftoday_meta["retrieved_at"],
                "from_cache": fftoday_meta["from_cache"],
            },
        },
        "coverage": {
            "three_sources": sum(player.source_count == 3 for player in players),
            "two_sources": sum(player.source_count == 2 for player in players),
            "one_source": sum(player.source_count == 1 for player in players),
        },
        "caveat": (
            "ADP measures market price rather than projected production, and ESPN's source "
            "sheet is full PPR. The later league model applies VORP and automated context."
        ),
    }
    write_json(
        json_path,
        {"metadata": metadata, "players": [asdict(player) for player in players]},
    )
    write_text(markdown_path, render_markdown(metadata, players))
    return {
        "player_count": len(players),
        "three_source_count": sum(player.source_count == 3 for player in players),
        "markdown_path": str(markdown_path),
        "json_path": str(json_path),
    }


def parse_fftoday(html: str) -> list[dict[str, Any]]:
    parser = _FFTodayParser()
    parser.feed(html)
    if len(parser.rows) < 100:
        raise InjuryContextError(
            f"FFToday parser found only {len(parser.rows)} player rows; "
            "page layout may have changed."
        )
    return [
        {
            "rank": int(row[0]),
            "name": row[1],
            "position": row[2],
            "position_rank": int(row[3]),
            "team": normalize_team(row[4]),
            "underdog_rank": _optional_float(row[5]),
            "yahoo_rank": _optional_float(row[6]),
            "adp": float(row[7]),
        }
        for row in parser.rows
    ]


def parse_fantasypros(html: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    marker = "var ecrData = "
    start = html.find(marker)
    if start < 0:
        raise InjuryContextError("FantasyPros ecrData payload was not found.")
    start += len(marker)
    try:
        payload, _ = json.JSONDecoder().raw_decode(html[start:])
        players = payload["players"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise InjuryContextError(f"Could not parse FantasyPros ecrData: {error}") from error
    if len(players) < 300:
        raise InjuryContextError(f"FantasyPros payload contained only {len(players)} players.")
    return players, {
        "total_experts": payload.get("total_experts"),
        "last_updated": payload.get("last_updated"),
    }


def build_market_players(
    entities: tuple[RankedEntity, ...],
    fftoday_rows: list[dict[str, Any]],
    fantasypros_rows: list[dict[str, Any]],
    fantasypros_metadata: dict[str, Any],
) -> tuple[MarketPlayer, ...]:
    fftoday_index = _source_index(fftoday_rows, name_key="name", team_key="team")
    fantasypros_index = _source_index(
        fantasypros_rows, name_key="player_name", team_key="player_team_id"
    )
    players: list[MarketPlayer] = []
    for entity in entities:
        fftoday = _match_source(entity, fftoday_index, "position")
        fantasypros = _match_source(entity, fantasypros_index, "player_position_id")
        ranks: list[tuple[float, float]] = [(float(entity.rank), SOURCE_WEIGHTS["espn"])]
        if fantasypros is not None:
            ranks.append((float(fantasypros["rank_ecr"]), SOURCE_WEIGHTS["fantasypros"]))
        if fftoday is not None:
            ranks.append((float(fftoday["adp"]), SOURCE_WEIGHTS["fftoday"]))
        total_weight = sum(weight for _, weight in ranks)
        consensus_rank = sum(rank * weight for rank, weight in ranks) / total_weight
        source_count = len(ranks)
        players.append(
            MarketPlayer(
                source_rank=entity.rank,
                name=entity.name,
                team=entity.team,
                position=entity.position,
                position_rank=entity.position_rank,
                bye_week=entity.bye_week,
                espn_rank=entity.rank,
                fantasypros_rank=(
                    int(fantasypros["rank_ecr"]) if fantasypros is not None else None
                ),
                fantasypros_position_rank=(
                    str(fantasypros.get("pos_rank")) if fantasypros is not None else None
                ),
                fantasypros_tier=(
                    int(fantasypros["tier"])
                    if fantasypros is not None and fantasypros.get("tier") is not None
                    else None
                ),
                fantasypros_expert_count=(
                    int(fantasypros_metadata["total_experts"])
                    if fantasypros_metadata.get("total_experts") is not None
                    else None
                ),
                fftoday_rank=int(fftoday["rank"]) if fftoday is not None else None,
                fftoday_adp=float(fftoday["adp"]) if fftoday is not None else None,
                fftoday_position_rank=(
                    int(fftoday["position_rank"]) if fftoday is not None else None
                ),
                consensus_rank=round(consensus_rank, 2),
                source_count=source_count,
                match_quality=(
                    "three-source"
                    if source_count == 3
                    else "two-source"
                    if source_count == 2
                    else "espn-only"
                ),
            )
        )
    return tuple(players)


def render_markdown(metadata: dict[str, Any], players: tuple[MarketPlayer, ...]) -> str:
    coverage = metadata["coverage"]
    lines = [
        "# 2026 multi-source market context",
        "",
        f"**Generated:** `{metadata['generated_at']}`  ",
        f"**Three-source coverage:** {coverage['three_sources']}/300  ",
        "",
        metadata["method"],
        "",
        "| ESPN PPR | FantasyPros half-PPR ECR | FFToday half-PPR ADP |",
        "|---|---|---|",
        f"[Source]({ESPN_SOURCE_URL}) | [Source]({FANTASYPROS_URL}) | [Source]({FFTODAY_URL}) |",
        "",
        "| ESPN rank | Player | Pos-Team | FP rank | FFToday ADP | Consensus | Sources |",
        "|---:|---|---|---:|---:|---:|---:|",
    ]
    for player in players:
        lines.append(
            f"| {player.espn_rank} | {player.name} | {player.position}-{player.team} | "
            f"{player.fantasypros_rank or '--'} | "
            f"{player.fftoday_adp if player.fftoday_adp is not None else '--'} | "
            f"{player.consensus_rank:.2f} | {player.source_count} |"
        )
    lines.extend(["", "## Caveat", "", metadata["caveat"], ""])
    return "\n".join(lines)


def _source_index(
    rows: list[dict[str, Any]], *, name_key: str, team_key: str
) -> dict[tuple[str, str | None], list[dict[str, Any]]]:
    index: dict[tuple[str, str | None], list[dict[str, Any]]] = {}
    for row in rows:
        key = (normalize_name(row.get(name_key)), normalize_team(row.get(team_key)))
        index.setdefault(key, []).append(row)
    return index


def _match_source(
    entity: RankedEntity,
    index: dict[tuple[str, str | None], list[dict[str, Any]]],
    position_key: str,
) -> dict[str, Any] | None:
    if entity.position == "DST":
        team_candidates = [
            row for (_name, team), rows in index.items() if team == entity.team for row in rows
        ]
        defenses = [
            row for row in team_candidates if str(row.get(position_key)).upper() in {"DEF", "DST"}
        ]
        return defenses[0] if len(defenses) == 1 else None
    entity_name = normalize_name(entity.name)
    source_names = {entity_name, MARKET_NAME_ALIASES.get(entity_name, entity_name)}
    candidates = [
        row for source_name in source_names for row in index.get((source_name, entity.team), [])
    ]
    if not candidates:
        candidates = [
            row for (name, _team), rows in index.items() if name in source_names for row in rows
        ]
    position = "DST" if entity.position == "DST" else entity.position
    matches = [row for row in candidates if str(row.get(position_key)) == position]
    choices = matches or candidates
    return choices[0] if len(choices) == 1 else None


def _fetch_html(
    *,
    name: str,
    url: str,
    cache_dir: Path,
    refresh: bool,
    offline: bool,
    timeout: float,
) -> tuple[str, dict[str, Any]]:
    cache = cache_dir / f"{name}.html"
    try:
        result = CachedWebClient(
            CachePolicy(refresh=refresh, offline=offline, timeout=timeout)
        ).fetch_text(name=name, url=url, cache_path=cache)
    except FantasyFootballError as error:
        raise InjuryContextError(str(error)) from error
    return result.payload, {
        "retrieved_at": result.retrieved_at,
        "from_cache": result.from_cache,
    }


def _optional_float(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


if __name__ == "__main__":
    raise SystemExit(main())
