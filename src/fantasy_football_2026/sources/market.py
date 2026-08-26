"""Build a multi-source market and baseline ranking context."""

from __future__ import annotations

import argparse
import json
import re
import statistics
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

SOURCE_WEIGHTS = {
    "espn": 1.0,
    "fantasypros": 1.0,
    "fftoday": 1.0,
    "rotoballer": 1.0,
    "fantasy_football_calculator": 1.0,
    "lineupbeat": 1.0,
    "pro_football_mania": 1.0,
}

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
    rotoballer_rank: int | None
    fantasy_football_calculator_rank: int | None
    lineupbeat_rank: int | None
    pro_football_mania_rank: int | None
    consensus_rank: float
    consensus_median: float
    consensus_range: float
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


class _TableRowsParser(HTMLParser):
    """Extract text cells from every HTML table row for source-specific filtering."""

    def __init__(self) -> None:
        super().__init__()
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self.rows: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._cell is not None:
            assert self._row is not None
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None


class _JsonLdParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._capture = False
        self._parts: list[str] = []
        self.documents: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script" and dict(attrs).get("type") == "application/ld+json":
            self._capture = True
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._capture:
            self.documents.append("".join(self._parts))
            self._capture = False


class _ProFootballManiaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._player: dict[str, Any] | None = None
        self.rows: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "tr" and attributes.get("data-pfm-player-name"):
            try:
                ranks = json.loads(attributes.get("data-pfm-ranks") or "{}")
                rank = int(ranks["overall"])
            except (ValueError, TypeError, KeyError, json.JSONDecodeError):
                self._player = None
                return
            self._player = {
                "rank": rank,
                "name": attributes["data-pfm-player-name"],
            }
        elif self._player is not None and attributes.get("data-position"):
            self._player.update(
                {
                    "position": _normalize_position(attributes["data-position"]),
                    "team": normalize_team(attributes.get("data-team-abbr")),
                }
            )

    def handle_endtag(self, tag: str) -> None:
        if tag == "tr" and self._player is not None:
            if self._player.get("position"):
                self.rows.append(self._player)
            self._player = None


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
    print(f"Five-plus-source rows: {result['five_plus_source_count']}")
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
    benchmark_documents: dict[str, tuple[str, dict[str, Any]]] = {}
    for source_name, source_url in _benchmark_source_urls().items():
        benchmark_documents[source_name] = _fetch_html(
            name=f"{source_name}_half_ppr",
            url=source_url,
            cache_dir=cache_dir,
            refresh=refresh,
            offline=offline,
            timeout=timeout,
        )
    fftoday = parse_fftoday(fftoday_html)
    fantasypros, fp_metadata = parse_fantasypros(fantasypros_html)
    benchmark_sources = {
        "rotoballer": parse_rotoballer(benchmark_documents["rotoballer"][0]),
        "fantasy_football_calculator": parse_fantasy_football_calculator(
            benchmark_documents["fantasy_football_calculator"][0]
        ),
        "lineupbeat": parse_lineupbeat(benchmark_documents["lineupbeat"][0]),
        "pro_football_mania": parse_pro_football_mania(
            benchmark_documents["pro_football_mania"][0]
        ),
    }
    players = build_market_players(
        entities,
        fftoday,
        fantasypros,
        fp_metadata,
        benchmark_sources=benchmark_sources,
    )
    now = datetime.now(UTC)
    metadata = {
        "generated_at": now.isoformat(timespec="seconds"),
        "effective_date": now.date().isoformat(),
        "source_pdf": str(pdf_path),
        "source_weights": SOURCE_WEIGHTS,
        "method": (
            "Consensus rank is the simple mean of every available rank from ESPN, "
            "FantasyPros, FFToday, RotoBaller, Fantasy Football Calculator, LineupBeat, "
            "and Pro Football Mania. Missing sources are omitted. The median and range "
            "are retained for automated anomaly detection."
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
            **{
                source_name: {
                    "url": _benchmark_source_urls()[source_name],
                    "role": _benchmark_source_roles()[source_name],
                    "retrieved_at": source_meta["retrieved_at"],
                    "from_cache": source_meta["from_cache"],
                    "row_count": len(benchmark_sources[source_name]),
                }
                for source_name, (_source_html, source_meta) in benchmark_documents.items()
            },
        },
        "coverage": {
            "seven_sources": sum(player.source_count == 7 for player in players),
            "five_plus_sources": sum(player.source_count >= 5 for player in players),
            "three_plus_sources": sum(player.source_count >= 3 for player in players),
            "minimum_sources": min(player.source_count for player in players),
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
        "five_plus_source_count": sum(player.source_count >= 5 for player in players),
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


def parse_rotoballer(html: str) -> list[dict[str, Any]]:
    parser = _TableRowsParser()
    parser.feed(html)
    rows = [
        {
            "rank": int(row[1]),
            "name": row[2],
            "team": None,
            "position": _normalize_position(row[3]),
        }
        for row in parser.rows
        if len(row) == 4 and row[1].isdigit() and _is_fantasy_position(row[3])
    ]
    return _validate_benchmark_rows("RotoBaller", rows, minimum=300)


def parse_fantasy_football_calculator(html: str) -> list[dict[str, Any]]:
    parser = _TableRowsParser()
    parser.feed(html)
    rows: list[dict[str, Any]] = []
    for row in parser.rows:
        if len(row) < 4 or not row[0].rstrip(".").isdigit() or not _is_fantasy_position(row[3]):
            continue
        rows.append(
            {
                "rank": int(row[0].rstrip(".")),
                "name": row[1],
                "team": normalize_team(row[2]),
                "position": _normalize_position(row[3]),
            }
        )
    return _validate_benchmark_rows("Fantasy Football Calculator", rows, minimum=100)


def parse_lineupbeat(html: str) -> list[dict[str, Any]]:
    parser = _JsonLdParser()
    parser.feed(html)
    candidates: list[dict[str, Any]] = []
    for document in parser.documents:
        try:
            payload = json.loads(document)
        except json.JSONDecodeError:
            continue
        candidates.extend(_find_item_lists(payload))
    item_list = max(candidates, key=lambda item: len(item.get("itemListElement") or []), default={})
    rows: list[dict[str, Any]] = []
    for item in item_list.get("itemListElement") or []:
        if not isinstance(item, dict):
            continue
        match = re.fullmatch(
            r"(?P<name>.+) \((?P<team>[^,]+), (?P<position>[^)]+)\)", str(item.get("name") or "")
        )
        if match is None or not _is_fantasy_position(match.group("position")):
            continue
        rows.append(
            {
                "rank": int(item["position"]),
                "name": match.group("name"),
                "team": normalize_team(match.group("team")),
                "position": _normalize_position(match.group("position")),
            }
        )
    return _validate_benchmark_rows("LineupBeat", rows, minimum=190)


def parse_pro_football_mania(html: str) -> list[dict[str, Any]]:
    parser = _ProFootballManiaParser()
    parser.feed(html)
    return _validate_benchmark_rows("Pro Football Mania", parser.rows, minimum=250)


def _find_item_lists(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if value.get("@type") == "ItemList" and isinstance(value.get("itemListElement"), list):
            found.append(value)
        for child in value.values():
            found.extend(_find_item_lists(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_find_item_lists(child))
    return found


def _validate_benchmark_rows(
    source_name: str,
    rows: list[dict[str, Any]],
    *,
    minimum: int,
) -> list[dict[str, Any]]:
    unique_ranks = {int(row["rank"]) for row in rows}
    if len(rows) < minimum or len(unique_ranks) != len(rows):
        raise InjuryContextError(
            f"{source_name} parser found {len(rows)} valid unique rows; "
            f"expected at least {minimum}."
        )
    return rows


def _normalize_position(value: str) -> str:
    position = value.strip().upper()
    return {"D": "DST", "DEF": "DST", "PK": "K"}.get(position, position)


def _is_fantasy_position(value: str) -> bool:
    return _normalize_position(value) in {"QB", "RB", "WR", "TE", "K", "DST"}


def build_market_players(
    entities: tuple[RankedEntity, ...],
    fftoday_rows: list[dict[str, Any]],
    fantasypros_rows: list[dict[str, Any]],
    fantasypros_metadata: dict[str, Any],
    *,
    benchmark_sources: dict[str, list[dict[str, Any]]] | None = None,
) -> tuple[MarketPlayer, ...]:
    benchmark_sources = benchmark_sources or {}
    fftoday_index = _source_index(fftoday_rows, name_key="name", team_key="team")
    fantasypros_index = _source_index(
        fantasypros_rows, name_key="player_name", team_key="player_team_id"
    )
    benchmark_indexes = {
        source_name: _source_index(rows, name_key="name", team_key="team")
        for source_name, rows in benchmark_sources.items()
    }
    players: list[MarketPlayer] = []
    for entity in entities:
        fftoday = _match_source(entity, fftoday_index, "position")
        fantasypros = _match_source(entity, fantasypros_index, "player_position_id")
        benchmarks = {
            source_name: _match_source(entity, source_index, "position")
            for source_name, source_index in benchmark_indexes.items()
        }
        ranks: list[tuple[float, float]] = [(float(entity.rank), SOURCE_WEIGHTS["espn"])]
        if fantasypros is not None:
            ranks.append((float(fantasypros["rank_ecr"]), SOURCE_WEIGHTS["fantasypros"]))
        if fftoday is not None:
            ranks.append((float(fftoday["adp"]), SOURCE_WEIGHTS["fftoday"]))
        for source_name, benchmark in benchmarks.items():
            if benchmark is not None:
                ranks.append((float(benchmark["rank"]), SOURCE_WEIGHTS[source_name]))
        total_weight = sum(weight for _, weight in ranks)
        consensus_rank = sum(rank * weight for rank, weight in ranks) / total_weight
        rank_values = [rank for rank, _weight in ranks]
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
                rotoballer_rank=_benchmark_rank(benchmarks, "rotoballer"),
                fantasy_football_calculator_rank=_benchmark_rank(
                    benchmarks, "fantasy_football_calculator"
                ),
                lineupbeat_rank=_benchmark_rank(benchmarks, "lineupbeat"),
                pro_football_mania_rank=_benchmark_rank(benchmarks, "pro_football_mania"),
                consensus_rank=round(consensus_rank, 2),
                consensus_median=round(statistics.median(rank_values), 2),
                consensus_range=round(max(rank_values) - min(rank_values), 2),
                source_count=source_count,
                match_quality=f"{source_count}-source",
            )
        )
    return tuple(players)


def render_markdown(metadata: dict[str, Any], players: tuple[MarketPlayer, ...]) -> str:
    coverage = metadata["coverage"]
    lines = [
        "# 2026 multi-source market context",
        "",
        f"**Generated:** `{metadata['generated_at']}`  ",
        f"**Five-plus-source coverage:** {coverage['five_plus_sources']}/300  ",
        f"**Seven-source coverage:** {coverage['seven_sources']}/300  ",
        "",
        metadata["method"],
        "",
        "| ESPN | FP | FFToday | RotoBaller | FFC | LineupBeat | PFM |",
        "|---:|---:|---:|---:|---:|---:|---:|",
        f"| [Source]({ESPN_SOURCE_URL}) | [Source]({FANTASYPROS_URL}) | "
        f"[Source]({FFTODAY_URL}) | [Source]({SourceUrl.ROTOBALLER_HALF_PPR}) | "
        f"[Source]({SourceUrl.FANTASY_FOOTBALL_CALCULATOR_HALF_PPR}) | "
        f"[Source]({SourceUrl.LINEUPBEAT_HALF_PPR}) | "
        f"[Source]({SourceUrl.PRO_FOOTBALL_MANIA_HALF_PPR}) |",
        "",
        "| Player | Pos-Team | ESPN | FP | FFToday | Roto | FFC | Lineup | PFM | "
        "Mean | Median | Range | Sources |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for player in players:
        lines.append(
            f"| {player.name} | {player.position}-{player.team} | {player.espn_rank} | "
            f"{player.fantasypros_rank or '--'} | {_display(player.fftoday_adp)} | "
            f"{_display(player.rotoballer_rank)} | "
            f"{_display(player.fantasy_football_calculator_rank)} | "
            f"{_display(player.lineupbeat_rank)} | "
            f"{_display(player.pro_football_mania_rank)} | "
            f"{player.consensus_rank:.2f} | {player.consensus_median:.2f} | "
            f"{player.consensus_range:.2f} | {player.source_count} |"
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


def _benchmark_source_urls() -> dict[str, str]:
    return {
        "rotoballer": SourceUrl.ROTOBALLER_HALF_PPR,
        "fantasy_football_calculator": SourceUrl.FANTASY_FOOTBALL_CALCULATOR_HALF_PPR,
        "lineupbeat": SourceUrl.LINEUPBEAT_HALF_PPR,
        "pro_football_mania": SourceUrl.PRO_FOOTBALL_MANIA_HALF_PPR,
    }


def _benchmark_source_roles() -> dict[str, str]:
    return {
        "rotoballer": "independent expert half-PPR Top 300",
        "fantasy_football_calculator": "daily half-PPR mock-draft market",
        "lineupbeat": "projection and replacement-value half-PPR Top 200",
        "pro_football_mania": "editorial half-PPR board with mock ADP context",
    }


def _display(value: int | float | None) -> str:
    return "--" if value is None else str(value)


def _benchmark_rank(
    benchmarks: dict[str, dict[str, Any] | None],
    source_name: str,
) -> int | None:
    benchmark = benchmarks.get(source_name)
    return int(benchmark["rank"]) if benchmark is not None else None


def _optional_float(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


if __name__ == "__main__":
    raise SystemExit(main())
