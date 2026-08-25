"""Build custom-scored projection value from an aggregated raw-stat forecast."""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from fantasy_football_2026.constants import (
    DEFAULT_LEAGUE_TEAMS,
    DEFAULT_TIMEOUT_SECONDS,
    FFTODAY_POSITION_IDS,
    PLAYER_NAME_ALIASES,
    TOTAL_RANKED_PLAYERS,
    CacheName,
    ContextFile,
    DirectoryName,
    SourceUrl,
)
from fantasy_football_2026.domain.normalization import normalize_name
from fantasy_football_2026.errors import FantasyFootballError, InjuryContextError, StorageError
from fantasy_football_2026.infrastructure.storage import load_json_object, write_json, write_text
from fantasy_football_2026.infrastructure.web import CachedWebClient, CachePolicy

ESPN_CLAY_PROJECTION_URL = SourceUrl.ESPN_CLAY_PROJECTIONS
FFTODAY_PROJECTION_URLS = {
    position: SourceUrl.FFTODAY_PROJECTIONS.format(position_id=position_id)
    for position, position_id in FFTODAY_POSITION_IDS.items()
}

MINIMUM_ESPN_ROWS = {"QB": 35, "RB": 80, "WR": 120, "TE": 50}
MINIMUM_FFTODAY_ROWS = {"QB": 55, "RB": 85, "WR": 120, "TE": 60}


@dataclass(frozen=True, slots=True)
class ProjectionPlayer:
    source_rank: int
    name: str
    team: str
    position: str
    projected_stats: dict[str, float]
    custom_projected_points: float | None
    baseline_points: float | None
    projected_value_over_baseline: float | None
    projected_value_grade: float
    projection_source_count: int


class _FFTodayProjectionParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._player_name: str | None = None
        self._in_player_link = False
        self.rows: list[tuple[str, tuple[str, ...]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "tr":
            self._row = []
            self._player_name = None
        elif self._row is not None and tag == "td":
            self._cell = []
        elif (
            self._cell is not None
            and tag == "a"
            and str(attributes.get("href", "")).startswith("/stats/players/")
        ):
            self._player_name = ""
            self._in_player_link = True

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)
            if self._in_player_link and self._player_name is not None:
                self._player_name += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_player_link:
            self._in_player_link = False
        elif self._cell is not None and tag == "td":
            assert self._row is not None
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif self._row is not None and tag == "tr":
            if self._player_name and len(self._row) >= 2:
                self.rows.append((" ".join(self._player_name.split()), tuple(self._row)))
            self._row = None
            self._player_name = None


class ProjectionContextBuilder:
    """Score aggregate projections with league rules and derive scarcity baselines."""

    def __init__(
        self,
        *,
        scoring_path: Path,
        market_path: Path,
        model_path: Path,
        cache_dir: Path,
        refresh: bool,
        offline: bool,
        timeout: float,
        teams: int,
    ) -> None:
        self.scoring_path = scoring_path
        self.market_path = market_path
        self.model_path = model_path
        self.cache_dir = cache_dir
        self.refresh = refresh
        self.offline = offline
        self.timeout = timeout
        self.teams = teams

    def build(self, *, json_path: Path, markdown_path: Path) -> dict[str, Any]:
        if self.teams < 2:
            raise InjuryContextError("teams must be at least 2")
        market = self._load_json(self.market_path)
        model = self._load_json(self.model_path)
        scoring = self._parse_scoring(self.scoring_path)
        espn_pdf, espn_fetch_metadata = self._fetch_pdf(
            name="espn_mike_clay_2026_projections",
            url=ESPN_CLAY_PROJECTION_URL,
        )
        espn_projections = self._parse_espn_clay(espn_pdf)
        fftoday_projections, fftoday_fetch_metadata = self._fetch_fftoday()
        all_projections = self._aggregate_sources(
            {"ESPN Mike Clay": espn_projections, "FFToday": fftoday_projections},
            scoring,
        )
        source_metadata = {
            "ESPN Mike Clay": {
                "url": ESPN_CLAY_PROJECTION_URL,
                "player_count": len(espn_projections),
                **espn_fetch_metadata,
            },
            "FFToday": {
                "urls": FFTODAY_PROJECTION_URLS,
                "player_count": len(fftoday_projections),
                **fftoday_fetch_metadata,
            },
        }

        baselines = self._derive_baselines(all_projections, model)
        value_by_name: dict[str, float] = {}
        for name, projection in all_projections.items():
            position = str(projection["position"])
            baseline = baselines.get(position)
            if baseline is not None:
                value_by_name[name] = float(projection["points"]) - baseline
        maximum_value = max((value for value in value_by_name.values() if value > 0), default=1.0)

        market_players = market.get("players")
        if not isinstance(market_players, list) or len(market_players) != TOTAL_RANKED_PLAYERS:
            raise InjuryContextError(
                f"Projection context requires the {TOTAL_RANKED_PLAYERS}-player market context."
            )
        players: list[ProjectionPlayer] = []
        matched_skill_players = 0
        for market_player in market_players:
            normalized = self._resolve_name(market_player.get("name"), all_projections)
            projection = all_projections.get(normalized or "")
            position = str(market_player.get("position") or "")
            if projection is None:
                points = None
                baseline = None
                value = None
                grade = 0.0
                stats: dict[str, float] = {}
                source_count = 0
            else:
                matched_skill_players += 1
                points = float(projection["points"])
                baseline = baselines.get(position)
                value = points - baseline if baseline is not None else None
                grade = 100.0 * max(0.0, value or 0.0) / maximum_value
                stats = dict(projection["stats"])
                source_count = int(projection["source_count"])
            players.append(
                ProjectionPlayer(
                    source_rank=int(market_player["source_rank"]),
                    name=str(market_player["name"]),
                    team=str(market_player["team"]),
                    position=position,
                    projected_stats=stats,
                    custom_projected_points=self._round_optional(points),
                    baseline_points=self._round_optional(baseline),
                    projected_value_over_baseline=self._round_optional(value),
                    projected_value_grade=round(grade, 2),
                    projection_source_count=source_count,
                )
            )

        generated_at = datetime.now(UTC).isoformat(timespec="seconds")
        metadata = {
            "schema_version": "1.0.0",
            "generated_at": generated_at,
            "teams": self.teams,
            "method": (
                "The simple mean of ESPN Mike Clay and FFToday raw-stat projections is "
                "scored under the league's base rules. RB/WR baselines come from a "
                "league-wide starter and flex simulation; one-QB and one-TE baselines use "
                "the configured median-starter correction. K/DST receive no projected-value "
                "premium because they are streamable and historically difficult to project."
            ),
            "scoring": scoring,
            "scoring_caveat": (
                "Projection feeds do not forecast counts of 300/400-yard games, 100/200-yard "
                "games, long touchdowns, two-point conversions, or fumbles lost. Those "
                "volatile events are excluded rather than estimated with an unsupported "
                "constant. A one-source projection is retained when only one feed lists a "
                "player; the Sources column makes that coverage visible."
            ),
            "league_structure": model["league_structure"],
            "baselines": {key: round(value, 2) for key, value in baselines.items()},
            "maximum_positive_value": round(maximum_value, 2),
            "matched_skill_players": matched_skill_players,
            "sources": source_metadata,
            "inputs": {
                "scoring": str(self.scoring_path),
                "market": str(self.market_path),
                "model": str(self.model_path),
            },
        }
        document = {"metadata": metadata, "players": [asdict(player) for player in players]}
        write_json(json_path, document)
        write_text(markdown_path, self.render_markdown(metadata, players))
        return {
            "player_count": len(players),
            "matched_skill_players": matched_skill_players,
            "json_path": str(json_path),
            "markdown_path": str(markdown_path),
        }

    def _fetch_fftoday(self) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        output: dict[str, dict[str, Any]] = {}
        retrieved_at: list[str] = []
        all_from_cache = True
        page_count = 0
        client = CachedWebClient(
            CachePolicy(
                refresh=self.refresh,
                offline=self.offline,
                timeout=self.timeout,
            )
        )
        for position, base_url in FFTODAY_PROJECTION_URLS.items():
            position_count = 0
            for page in range(5):
                url = f"{base_url}&order_by=FFPts&sort_order=DESC&cur_page={page}"
                name = f"fftoday_{position.lower()}_projections_{page}"
                try:
                    fetch = client.fetch_text(
                        name=name,
                        url=url,
                        cache_path=self.cache_dir / f"{name}.html",
                    )
                except FantasyFootballError as error:
                    raise InjuryContextError(str(error)) from error
                parsed = self._parse_fftoday_position(position, fetch.payload)
                if not parsed:
                    break
                new_names = set(parsed) - set(output)
                if not new_names:
                    break
                output.update(parsed)
                position_count += len(parsed)
                page_count += 1
                retrieved_at.append(fetch.retrieved_at)
                all_from_cache = all_from_cache and fetch.from_cache
            if position_count < MINIMUM_FFTODAY_ROWS[position]:
                raise InjuryContextError(
                    f"FFToday {position} projections contained only {position_count} rows."
                )
        return output, {
            "retrieved_at": max(retrieved_at),
            "from_cache": all_from_cache,
            "page_count": page_count,
        }

    @staticmethod
    def _parse_fftoday_position(
        position: str,
        html: str,
    ) -> dict[str, dict[str, Any]]:
        parser = _FFTodayProjectionParser()
        parser.feed(html)
        indexes = {
            "QB": {
                "pass_cmp": 4,
                "pass_att": 5,
                "pass_yds": 6,
                "pass_td": 7,
                "pass_int": 8,
                "rush_att": 9,
                "rush_yds": 10,
                "rush_td": 11,
            },
            "RB": {
                "rush_att": 4,
                "rush_yds": 5,
                "rush_td": 6,
                "receptions": 7,
                "rec_yds": 8,
                "rec_td": 9,
            },
            "WR": {
                "receptions": 4,
                "rec_yds": 5,
                "rec_td": 6,
                "rush_att": 7,
                "rush_yds": 8,
                "rush_td": 9,
            },
            "TE": {"receptions": 4, "rec_yds": 5, "rec_td": 6},
        }
        minimum_cells = {"QB": 13, "RB": 11, "WR": 11, "TE": 8}
        output: dict[str, dict[str, Any]] = {}
        for name, cells in parser.rows:
            if len(cells) < minimum_cells[position]:
                continue
            stats = {
                stat: ProjectionContextBuilder._number(cells[index])
                for stat, index in indexes[position].items()
            }
            output[normalize_name(name)] = {
                "name": name,
                "team": cells[2],
                "position": position,
                "stats": stats,
            }
        return output

    @staticmethod
    def _parse_espn_clay(path: Path) -> dict[str, dict[str, Any]]:
        output: dict[str, dict[str, Any]] = {}
        counts: dict[str, int] = defaultdict(int)
        reader = PdfReader(path)
        section_pattern = re.compile(
            r"(Quarterback|Running Back|Wide Receiver|Tight End) Projections"
        )
        position_names = {
            "Quarterback": "QB",
            "Running Back": "RB",
            "Wide Receiver": "WR",
            "Tight End": "TE",
        }
        row_pattern = re.compile(r"^\s*(?P<name>.+?)\s+(?P<team>[A-Z]{2,3})\s+(?P<data>\d.+)$")
        for page in reader.pages:
            text = page.extract_text(extraction_mode="layout") or ""
            section = section_pattern.search(text)
            if not section:
                continue
            position = position_names[section.group(1)]
            for line in text.splitlines():
                match = row_pattern.match(line)
                if not match:
                    continue
                tokens = match.group("data").replace("%", "").split()
                if len(tokens) != 12 or not all(token.isdigit() for token in tokens):
                    continue
                values = [float(token) for token in tokens]
                if position == "QB":
                    stats = {
                        "pass_att": values[3],
                        "pass_cmp": values[4],
                        "pass_yds": values[5],
                        "pass_td": values[6],
                        "pass_int": values[7],
                        "rush_att": values[9],
                        "rush_yds": values[10],
                        "rush_td": values[11],
                    }
                else:
                    stats = {
                        "rush_att": values[3],
                        "rush_yds": values[4],
                        "rush_td": values[5],
                        "receptions": values[7],
                        "rec_yds": values[8],
                        "rec_td": values[9],
                    }
                name = " ".join(match.group("name").split())
                output[normalize_name(name)] = {
                    "name": name,
                    "team": match.group("team"),
                    "position": position,
                    "stats": stats,
                }
                counts[position] += 1
        for position, minimum in MINIMUM_ESPN_ROWS.items():
            if counts[position] < minimum:
                raise InjuryContextError(
                    f"ESPN Mike Clay {position} projections contained only {counts[position]} rows."
                )
        return output

    @staticmethod
    def _aggregate_sources(
        sources: dict[str, dict[str, dict[str, Any]]],
        scoring: dict[str, float],
    ) -> dict[str, dict[str, Any]]:
        output: dict[str, dict[str, Any]] = {}
        all_names = set().union(*(set(source) for source in sources.values()))
        for normalized in all_names:
            rows = [source[normalized] for source in sources.values() if normalized in source]
            positions = {str(row["position"]) for row in rows}
            if len(positions) != 1:
                continue
            stats: dict[str, float] = {}
            stat_names = set().union(*(set(row["stats"]) for row in rows))
            for stat in stat_names:
                values = [float(row["stats"][stat]) for row in rows if stat in row["stats"]]
                stats[stat] = sum(values) / len(values)
            output[normalized] = {
                "name": rows[0]["name"],
                "team": rows[0]["team"],
                "position": rows[0]["position"],
                "stats": stats,
                "points": ProjectionContextBuilder._custom_points(stats, scoring),
                "source_count": len(rows),
            }
        return output

    def _fetch_pdf(self, *, name: str, url: str) -> tuple[Path, dict[str, Any]]:
        cache = self.cache_dir / f"{name}.pdf"
        try:
            result = CachedWebClient(
                CachePolicy(
                    refresh=self.refresh,
                    offline=self.offline,
                    timeout=self.timeout,
                )
            ).fetch_bytes(
                name=name,
                url=url,
                cache_path=cache,
                accept="application/pdf",
                validator=lambda payload: payload.startswith(b"%PDF"),
            )
        except FantasyFootballError as error:
            raise InjuryContextError(str(error)) from error
        return cache, {
            "retrieved_at": result.retrieved_at,
            "from_cache": result.from_cache,
        }

    def _derive_baselines(
        self,
        projections: dict[str, dict[str, Any]],
        model: dict[str, Any],
    ) -> dict[str, float]:
        structure = model.get("league_structure")
        if not isinstance(structure, dict):
            raise InjuryContextError("Ranking model is missing league_structure.")
        slots = structure.get("starting_slots")
        if not isinstance(slots, dict):
            raise InjuryContextError("league_structure.starting_slots must be an object.")
        by_position: dict[str, list[tuple[str, float]]] = {}
        for name, player in projections.items():
            by_position.setdefault(str(player["position"]), []).append(
                (name, float(player["points"]))
            )
        for values in by_position.values():
            values.sort(key=lambda item: item[1], reverse=True)

        dedicated: set[str] = set()
        for position in ("RB", "WR", "TE"):
            count = self.teams * int(slots.get(position, 0))
            dedicated.update(name for name, _points in by_position.get(position, [])[:count])
        flex_positions = {str(value) for value in structure.get("flex_positions", [])}
        flex_pool = sorted(
            (
                (name, float(player["points"]))
                for name, player in projections.items()
                if str(player["position"]) in flex_positions and name not in dedicated
            ),
            key=lambda item: item[1],
            reverse=True,
        )
        flex_count = self.teams * int(structure.get("flex_slots", 0))
        selected = dedicated | {name for name, _points in flex_pool[:flex_count]}
        baselines: dict[str, float] = {}
        for position in ("RB", "WR"):
            available = [
                points for name, points in by_position.get(position, []) if name not in selected
            ]
            if not available:
                raise InjuryContextError(f"Could not derive a {position} replacement baseline.")
            baselines[position] = available[0]

        fraction = float(structure.get("onesie_baseline_fraction", 0.5))
        for position in ("QB", "TE"):
            starter_count = self.teams * int(slots.get(position, 0))
            baseline_rank = max(1, round(starter_count * fraction))
            values = by_position.get(position, [])
            if len(values) < baseline_rank:
                raise InjuryContextError(f"Could not derive a {position} median-starter baseline.")
            baselines[position] = values[baseline_rank - 1][1]
        return baselines

    @staticmethod
    def _custom_points(stats: dict[str, float], scoring: dict[str, float]) -> float:
        return round(
            (stats.get("pass_yds", 0.0) * scoring["pass_yds"])
            + (stats.get("pass_td", 0.0) * scoring["pass_td"])
            + (stats.get("pass_int", 0.0) * scoring["pass_int"])
            + (stats.get("rush_yds", 0.0) * scoring["rush_yds"])
            + (stats.get("rush_td", 0.0) * scoring["rush_td"])
            + (stats.get("receptions", 0.0) * scoring["reception"])
            + (stats.get("rec_yds", 0.0) * scoring["rec_yds"])
            + (stats.get("rec_td", 0.0) * scoring["rec_td"])
            + (stats.get("fumbles_lost", 0.0) * scoring["fumble_lost"]),
            3,
        )

    @staticmethod
    def _parse_scoring(path: Path) -> dict[str, float]:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as error:
            raise InjuryContextError(f"Could not read league scoring {path}: {error}") from error
        labels = {
            "pass_yds": (r"Every 10 passing yards \(PY10\)\s+(-?\d+(?:\.\d+)?)", 0.1),
            "pass_td": (r"TD Pass \(PTD\)\s+(-?\d+(?:\.\d+)?)", 1.0),
            "pass_int": (r"Interceptions Thrown \(INT\)\s+(-?\d+(?:\.\d+)?)", 1.0),
            "rush_yds": (r"Rushing Yards \(RY\)\s+(-?\d+(?:\.\d+)?)", 1.0),
            "rush_td": (r"TD Rush \(RTD\)\s+(-?\d+(?:\.\d+)?)", 1.0),
            "reception": (r"Each reception \(REC\)\s+(-?\d+(?:\.\d+)?)", 1.0),
            "rec_yds": (r"Receiving Yards \(REY\)\s+(-?\d+(?:\.\d+)?)", 1.0),
            "rec_td": (r"TD Reception \(RETD\)\s+(-?\d+(?:\.\d+)?)", 1.0),
            "fumble_lost": (r"Total Fumbles Lost \(FUML\)\s+(-?\d+(?:\.\d+)?)", 1.0),
        }
        scoring: dict[str, float] = {}
        for key, (pattern, multiplier) in labels.items():
            match = re.search(pattern, text)
            if not match:
                raise InjuryContextError(f"Could not parse {key} from league scoring {path}.")
            scoring[key] = float(match.group(1)) * multiplier
        return scoring

    @staticmethod
    def render_markdown(metadata: dict[str, Any], players: list[ProjectionPlayer]) -> str:
        lines = [
            "# Custom-scored projection value",
            "",
            f"**Generated:** `{metadata['generated_at']}`  ",
            f"**Matched ranked skill players:** {metadata['matched_skill_players']}  ",
            "",
            metadata["method"],
            "",
            f"> {metadata['scoring_caveat']}",
            "",
            "| Rank | Player | Pos-Team | Projected | Baseline | Value | Grade | Sources |",
            "|---:|---|---|---:|---:|---:|---:|---:|",
        ]
        for player in players:
            lines.append(
                f"| {player.source_rank} | {player.name} | {player.position}-{player.team} | "
                f"{ProjectionContextBuilder._display(player.custom_projected_points)} | "
                f"{ProjectionContextBuilder._display(player.baseline_points)} | "
                f"{ProjectionContextBuilder._display(player.projected_value_over_baseline)} | "
                f"{player.projected_value_grade:.1f} | {player.projection_source_count} |"
            )
        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _resolve_name(value: Any, projections: dict[str, dict[str, Any]]) -> str | None:
        normalized = normalize_name(value)
        if normalized in projections:
            return normalized
        alias = PLAYER_NAME_ALIASES.get(normalized)
        if alias in projections:
            return alias
        reverse = next(
            (short for short, full in PLAYER_NAME_ALIASES.items() if full == normalized),
            None,
        )
        return reverse if reverse in projections else None

    @staticmethod
    def _number(value: str) -> float:
        try:
            return float(value.replace(",", ""))
        except ValueError as error:
            raise InjuryContextError(f"Invalid projection number {value!r}.") from error

    @staticmethod
    def _round_optional(value: float | None) -> float | None:
        return round(value, 2) if value is not None else None

    @staticmethod
    def _display(value: float | None) -> str:
        return f"{value:.1f}" if value is not None else "--"

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        try:
            return load_json_object(path)
        except StorageError as error:
            raise InjuryContextError(str(error)) from error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build custom-scored projection value.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--refresh", action="store_true")
    mode.add_argument("--offline", action="store_true")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--teams", type=int, default=DEFAULT_LEAGUE_TEAMS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    builder = ProjectionContextBuilder(
        scoring_path=Path(DirectoryName.CONTEXT, ContextFile.LEAGUE_SCORING),
        market_path=Path(DirectoryName.CONTEXT, ContextFile.MARKET_JSON),
        model_path=Path(DirectoryName.CONTEXT, ContextFile.MODEL_JSON),
        cache_dir=Path(DirectoryName.CONTEXT, DirectoryName.CACHE, CacheName.PROJECTIONS),
        refresh=args.refresh,
        offline=args.offline,
        timeout=args.timeout,
        teams=args.teams,
    )
    result = builder.build(
        json_path=Path(DirectoryName.CONTEXT, ContextFile.PROJECTIONS_JSON),
        markdown_path=Path(DirectoryName.CONTEXT, ContextFile.PROJECTIONS_MARKDOWN),
    )
    print(f"Projected players: {result['player_count']}")
    print(f"Matched skill players: {result['matched_skill_players']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
