"""Build current team depth-chart context for the ranked draft sheet."""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fantasy_football_2026.constants import (
    DEFAULT_SOURCE_PDF,
    DEFAULT_TIMEOUT_SECONDS,
    NFL_TEAM_COUNT,
    TOTAL_RANKED_PLAYERS,
    CacheName,
    ContextFile,
    DirectoryName,
    SourceUrl,
)
from fantasy_football_2026.domain.normalization import normalize_name, normalize_team
from fantasy_football_2026.errors import FantasyFootballError, InjuryContextError, StorageError
from fantasy_football_2026.infrastructure.storage import load_json_object, write_json, write_text
from fantasy_football_2026.infrastructure.web import CachedWebClient, CachePolicy
from fantasy_football_2026.presentation.buckets import (
    depth_chart_bucket,
    rank_bucket,
)
from fantasy_football_2026.presentation.buckets import injury_bucket as injury_color_bucket
from fantasy_football_2026.sources.injuries import (
    SLEEPER_PLAYERS_URL,
    RankedEntity,
    extract_ranked_entities,
)
from fantasy_football_2026.sources.schedule import load_schedule_ranks

ESPN_DEPTH_URL = SourceUrl.ESPN_DEPTH_CHART


@dataclass(frozen=True, slots=True)
class DepthChartEntry:
    rank: int
    name: str
    team: str
    fantasy_position: str
    depth_chart_position: str | None
    depth_chart_order: int | None
    pdf_label: str
    depth_chart_bucket: str
    offense_rank: int | None
    offense_bucket: str
    offensive_line_rank: int | None
    offensive_line_bucket: str
    strength_of_schedule_rank: int | None
    strength_of_schedule_bucket: str
    projected_injury_weeks: str
    injury_bucket: str
    match: str
    sleeper_player_id: str | None
    espn_depth_chart_position: str | None
    espn_depth_chart_order: int | None
    depth_source_count: int
    depth_source_agreement: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build current team depth-chart context for the PPR Top 300."
    )
    parser.add_argument("--pdf", type=Path, default=Path(DEFAULT_SOURCE_PDF))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(DirectoryName.CONTEXT, ContextFile.PLAYER_DEPTH_MARKDOWN),
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=Path(DirectoryName.CONTEXT, ContextFile.PLAYER_DEPTH_JSON),
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path(DirectoryName.CONTEXT, DirectoryName.CACHE),
    )
    parser.add_argument(
        "--team-projections",
        type=Path,
        default=Path(DirectoryName.CONTEXT, ContextFile.TEAM_PROJECTIONS_JSON),
    )
    parser.add_argument(
        "--strength-of-schedule",
        type=Path,
        default=Path(DirectoryName.CONTEXT, ContextFile.SCHEDULE_JSON),
    )
    parser.add_argument(
        "--injury-context",
        type=Path,
        default=Path(DirectoryName.CONTEXT, ContextFile.INJURIES_JSON),
    )
    parser.add_argument("--refresh", action="store_true", help="refresh the Sleeper feed")
    parser.add_argument("--offline", action="store_true", help="require cached source data")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = update_depth_chart_context(
            pdf_path=args.pdf,
            markdown_path=args.output,
            json_path=args.json_output,
            cache_dir=args.cache_dir,
            team_projections_path=args.team_projections,
            strength_of_schedule_path=args.strength_of_schedule,
            injury_context_path=args.injury_context,
            refresh=args.refresh,
            offline=args.offline,
            timeout=args.timeout,
        )
    except (InjuryContextError, OSError, ValueError) as error:
        raise SystemExit(f"error: {error}") from error
    print(f"Ranked entities: {result['entity_count']}")
    print(f"Matched players: {result['matched_player_count']}")
    print(f"Unassigned players: {result['unassigned_player_count']}")
    print(f"Markdown: {Path(result['markdown_path']).resolve()}")
    print(f"JSON: {Path(result['json_path']).resolve()}")
    return 0


def update_depth_chart_context(
    *,
    pdf_path: Path,
    markdown_path: Path,
    json_path: Path,
    cache_dir: Path,
    team_projections_path: Path,
    strength_of_schedule_path: Path,
    injury_context_path: Path,
    refresh: bool,
    offline: bool,
    timeout: float,
) -> dict[str, Any]:
    entities = extract_ranked_entities(pdf_path)
    if len(entities) != TOTAL_RANKED_PLAYERS:
        raise InjuryContextError(
            f"Expected {TOTAL_RANKED_PLAYERS} ranked entities, extracted {len(entities)}."
        )

    now = datetime.now(UTC)
    client = CachedWebClient(
        CachePolicy(
            refresh=refresh,
            offline=offline,
            timeout=timeout,
            current_day_only=True,
            stale_if_error=True,
        ),
        now=lambda: now,
    )
    try:
        fetch = client.fetch_json(
            name="sleeper_players",
            url=SLEEPER_PLAYERS_URL,
            cache_path=cache_dir / CacheName.SLEEPER_PLAYERS_JSON,
        )
    except FantasyFootballError as error:
        raise InjuryContextError(str(error)) from error
    team_projections = load_team_projections(team_projections_path)
    try:
        espn_fetches = {
            team: client.fetch_json(
                name=f"espn_depth_{team.lower()}",
                url=ESPN_DEPTH_URL.format(team=team.lower()),
                cache_path=cache_dir / f"espn_depth_{team.lower()}.json",
            )
            for team in sorted(team_projections)
        }
    except FantasyFootballError as error:
        raise InjuryContextError(str(error)) from error
    espn_depths = parse_espn_depth_charts(
        {team: result.payload for team, result in espn_fetches.items()}
    )
    schedule_ranks = load_schedule_ranks(strength_of_schedule_path)
    injury_displays = load_injury_displays(injury_context_path)
    entries = build_depth_chart_entries(
        entities,
        fetch.payload,
        team_projections,
        schedule_ranks,
        injury_displays,
        espn_depths,
    )
    metadata = {
        "generated_at": now.isoformat(timespec="seconds"),
        "source": "Sleeper NFL player API",
        "source_url": SLEEPER_PLAYERS_URL,
        "depth_sources": {
            "primary": SLEEPER_PLAYERS_URL,
            "cross_check": ESPN_DEPTH_URL.format(team="det"),
        },
        "source_retrieved_at": fetch.retrieved_at,
        "source_from_cache": fetch.from_cache,
        "espn_depth_retrieval": {
            team: {
                "retrieved_at": result.retrieved_at,
                "from_cache": result.from_cache,
            }
            for team, result in sorted(espn_fetches.items())
        },
        "source_pdf": str(pdf_path),
        "team_projections": str(team_projections_path),
        "strength_of_schedule": str(strength_of_schedule_path),
        "injury_context": str(injury_context_path),
        "column_validation": "context/column_validation.json",
        "color_buckets": {
            "rank": "green 1-10; yellow 11-22; red 23-32 or unavailable",
            "depth_chart": "green order 1/DST; yellow order 2; red order 3+ or unavailable",
            "injury": "green 0 weeks/DST; yellow 1-2 weeks; red 3+ or unresolved",
        },
        "label_method": (
            "Sleeper depth_chart_position plus depth_chart_order; DST for team defenses; "
            "ESPN is an independent order cross-check and a fallback only when Sleeper "
            "has no unique match; -- means both sources are unavailable."
        ),
    }
    write_json(
        json_path,
        {"metadata": metadata, "players": [asdict(entry) for entry in entries]},
    )
    write_text(markdown_path, render_markdown(metadata, entries))
    return {
        "entity_count": len(entries),
        "matched_player_count": sum(entry.match == "exact-name-team" for entry in entries),
        "unassigned_player_count": sum(
            entry.pdf_label == "--" for entry in entries if entry.fantasy_position != "DST"
        ),
        "markdown_path": str(markdown_path),
        "json_path": str(json_path),
    }


def build_depth_chart_entries(
    entities: tuple[RankedEntity, ...],
    sleeper_payload: dict[str, Any],
    team_projections: dict[str, tuple[int, int]] | None = None,
    schedule_ranks: dict[str, dict[str, int]] | None = None,
    injury_displays: dict[int, tuple[str, str]] | None = None,
    espn_depths: dict[tuple[str, str], tuple[str, int]] | None = None,
) -> tuple[DepthChartEntry, ...]:
    index: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for player_id, player in sleeper_payload.items():
        name = player.get("full_name") or " ".join(
            part for part in (player.get("first_name"), player.get("last_name")) if part
        )
        if name:
            index[normalize_name(name)].append((str(player_id), player))

    entries: list[DepthChartEntry] = []
    projections = team_projections or {}
    schedules = schedule_ranks or {}
    injuries = injury_displays or {}
    espn = espn_depths or {}
    for entity in entities:
        offense_rank, offensive_line_rank = projections.get(entity.team, (None, None))
        schedule_position = "DEF" if entity.position == "DST" else entity.position
        schedule_rank = schedules.get(entity.team, {}).get(schedule_position)
        injury_label, injury_color = injuries.get(
            entity.rank,
            ("--", injury_color_bucket("--"))
            if entity.entity_type == "defense"
            else ("?", injury_color_bucket("?")),
        )
        if entity.entity_type == "defense":
            entries.append(_defense_entry(entity, schedule_rank, injury_label, injury_color))
            continue
        espn_depth = espn.get((entity.team, normalize_name(entity.name)))
        candidates = index.get(normalize_name(entity.name), [])
        team_matches = [
            candidate
            for candidate in candidates
            if normalize_team(candidate[1].get("team")) == entity.team
        ]
        position_matches = [
            candidate
            for candidate in (team_matches or candidates)
            if candidate[1].get("position") == entity.position
        ]
        choices = position_matches or team_matches or candidates
        if len(choices) != 1:
            if not choices and espn_depth is not None:
                espn_position, espn_order = espn_depth
                label = depth_chart_label(espn_position, espn_order)
                entries.append(
                    DepthChartEntry(
                        rank=entity.rank,
                        name=entity.name,
                        team=entity.team,
                        fantasy_position=entity.position,
                        depth_chart_position=espn_position,
                        depth_chart_order=espn_order,
                        pdf_label=label,
                        depth_chart_bucket=depth_chart_bucket(label),
                        offense_rank=offense_rank,
                        offense_bucket=rank_bucket(offense_rank),
                        offensive_line_rank=offensive_line_rank,
                        offensive_line_bucket=rank_bucket(offensive_line_rank),
                        strength_of_schedule_rank=schedule_rank,
                        strength_of_schedule_bucket=rank_bucket(schedule_rank),
                        projected_injury_weeks=injury_label,
                        injury_bucket=injury_color,
                        match="espn-only",
                        sleeper_player_id=None,
                        espn_depth_chart_position=espn_position,
                        espn_depth_chart_order=espn_order,
                        depth_source_count=1,
                        depth_source_agreement="espn-only",
                    )
                )
                continue
            entries.append(
                _unassigned_entry(
                    entity,
                    "unmatched" if not choices else "ambiguous",
                    offense_rank,
                    offensive_line_rank,
                    schedule_rank,
                    injury_label,
                    injury_color,
                    espn_depth,
                )
            )
            continue
        player_id, player = choices[0]
        chart_position = _clean_chart_position(player.get("depth_chart_position"))
        chart_order = _clean_chart_order(player.get("depth_chart_order"))
        match = "exact-name-team" if team_matches else "exact-name"
        espn_position, espn_order = espn_depth or (None, None)
        if espn_depth is None:
            agreement = "sleeper-only"
            source_count = 1
        elif chart_order == espn_order:
            agreement = "same-order"
            source_count = 2
        else:
            agreement = "different-order"
            source_count = 2
        entries.append(
            DepthChartEntry(
                rank=entity.rank,
                name=entity.name,
                team=entity.team,
                fantasy_position=entity.position,
                depth_chart_position=chart_position,
                depth_chart_order=chart_order,
                pdf_label=depth_chart_label(chart_position, chart_order),
                depth_chart_bucket=depth_chart_bucket(
                    depth_chart_label(chart_position, chart_order)
                ),
                offense_rank=offense_rank,
                offense_bucket=rank_bucket(offense_rank),
                offensive_line_rank=offensive_line_rank,
                offensive_line_bucket=rank_bucket(offensive_line_rank),
                strength_of_schedule_rank=schedule_rank,
                strength_of_schedule_bucket=rank_bucket(schedule_rank),
                projected_injury_weeks=injury_label,
                injury_bucket=injury_color,
                match=match,
                sleeper_player_id=player_id,
                espn_depth_chart_position=espn_position,
                espn_depth_chart_order=espn_order,
                depth_source_count=source_count,
                depth_source_agreement=agreement,
            )
        )
    return tuple(entries)


def parse_espn_depth_charts(
    payloads: dict[str, dict[str, Any]],
) -> dict[tuple[str, str], tuple[str, int]]:
    """Return ESPN offensive depth order keyed by team and normalized player name."""

    result: dict[tuple[str, str], tuple[str, int]] = {}
    for team, payload in payloads.items():
        for chart in payload.get("depthchart", []):
            for slot in chart.get("positions", {}).values():
                position = str(slot.get("position", {}).get("abbreviation") or "").upper()
                if position == "PK":
                    position = "K"
                if position not in {"QB", "RB", "WR", "TE", "K"}:
                    continue
                for order, athlete in enumerate(slot.get("athletes", []), start=1):
                    name = normalize_name(athlete.get("displayName"))
                    if name:
                        result.setdefault((team, name), (position, order))
    return result


def depth_chart_label(position: str | None, order: int | None) -> str:
    if not position or order is None:
        return "--"
    return f"{position}{order}"


def load_depth_chart_labels(path: Path) -> dict[int, str]:
    try:
        payload = load_json_object(path)
        players = payload["players"]
        labels = {int(player["rank"]): str(player["pdf_label"]) for player in players}
    except (StorageError, KeyError, TypeError, ValueError) as error:
        raise InjuryContextError(f"Could not load depth-chart context {path}: {error}") from error
    if len(labels) != TOTAL_RANKED_PLAYERS:
        raise InjuryContextError(
            f"Expected {TOTAL_RANKED_PLAYERS} depth-chart labels in {path}, found {len(labels)}."
        )
    return labels


def load_draft_sheet_context(path: Path) -> dict[int, tuple[str, str, str, str, str]]:
    try:
        payload = load_json_object(path)
        players = payload["players"]
        labels = {
            int(player["rank"]): (
                str(player["pdf_label"]),
                str(player["offense_rank"] or "--"),
                str(player["offensive_line_rank"] or "--"),
                str(player["strength_of_schedule_rank"] or "--"),
                str(player["projected_injury_weeks"]),
            )
            for player in players
        }
    except (StorageError, KeyError, TypeError, ValueError) as error:
        raise InjuryContextError(f"Could not load draft-sheet context {path}: {error}") from error
    if len(labels) != TOTAL_RANKED_PLAYERS:
        raise InjuryContextError(
            f"Expected {TOTAL_RANKED_PLAYERS} draft rows in {path}, found {len(labels)}."
        )
    return labels


def load_injury_displays(path: Path) -> dict[int, tuple[str, str]]:
    try:
        payload = load_json_object(path)
        displays = {
            int(player["rank"]): (
                str(player["pdf_weeks_label"]),
                str(player["injury_bucket"]),
            )
            for player in payload["players"]
        }
    except (StorageError, KeyError, TypeError, ValueError) as error:
        raise InjuryContextError(f"Could not load injury context {path}: {error}") from error
    if len(displays) != TOTAL_RANKED_PLAYERS:
        raise InjuryContextError(
            f"Expected {TOTAL_RANKED_PLAYERS} injury rows in {path}, found {len(displays)}."
        )
    for rank, (label, bucket) in displays.items():
        expected = injury_color_bucket(label)
        if bucket != expected:
            raise InjuryContextError(
                f"Injury bucket mismatch for rank {rank}: stored {bucket}, expected {expected}."
            )
    return displays


def load_team_projections(path: Path) -> dict[str, tuple[int, int]]:
    try:
        payload = load_json_object(path)
        projections = {
            normalize_team(team): (
                int(values["offense_rank"]),
                int(values["offensive_line_rank"]),
            )
            for team, values in payload["teams"].items()
        }
    except (StorageError, KeyError, TypeError, ValueError) as error:
        raise InjuryContextError(f"Could not load team projections {path}: {error}") from error
    if len(projections) != NFL_TEAM_COUNT or any(team is None for team in projections):
        raise InjuryContextError(f"Expected projections for {NFL_TEAM_COUNT} NFL teams in {path}.")
    return {str(team): ranks for team, ranks in projections.items()}


def render_markdown(metadata: dict[str, Any], entries: tuple[DepthChartEntry, ...]) -> str:
    assigned = sum(entry.pdf_label != "--" for entry in entries)
    lines = [
        "# 2026 PPR Top 300 Team Depth Charts",
        "",
        f"Generated: `{metadata['generated_at']}`",
        f"Sleeper feed retrieved: `{metadata['source_retrieved_at']}`",
        f"Source: [Sleeper NFL player API]({metadata['source_url']})",
        "Team context: [Offense and offensive-line projections](./team_projections.md)",
        "Schedule context: [Position-specific strength of schedule](./strength_of_schedule.md)",
        "Injury context: [Cross-referenced weeks-missed estimates](./player_injuries.md)",
        "Source audit: [Column cross-reference validation](./column_validation.md)",
        "",
        (
            f"Coverage: **{assigned}/{len(entries)} rows assigned**. Player labels combine "
            "Sleeper's team depth-chart slot and order (for example `RB1`, `LWR1`, or "
            "`SWR2`). Team defenses use `DST`; `--` means no current assignment."
        ),
        "",
        (
            "| Rank | Player | Team | Fantasy pos. | Depth-chart slot | Order | "
            "PDF label | OFF | OL | SOS | INJ weeks | Match |"
        ),
        ("| ---: | --- | :---: | :---: | :---: | ---: | :---: | ---: | ---: | ---: | ---: | --- |"),
    ]
    for entry in entries:
        lines.append(
            f"| {entry.rank} | {entry.name} | {entry.team} | {entry.fantasy_position} | "
            f"{entry.depth_chart_position or '--'} | "
            f"{entry.depth_chart_order if entry.depth_chart_order is not None else '--'} | "
            f"{entry.pdf_label} | {entry.offense_rank or '--'} | "
            f"{entry.offensive_line_rank or '--'} | "
            f"{entry.strength_of_schedule_rank or '--'} | "
            f"{entry.projected_injury_weeks} | {entry.match} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            (
                "These are current roster depth-chart assignments, not playing-time or fantasy "
                "rank projections. Wide-receiver slots retain Sleeper's alignment (`LWR`, `RWR`, "
                "or `SWR`) so multiple starters are not misleadingly collapsed into one `WR1`."
            ),
            (
                "`OFF` is the projected team scoring rank and `OL` is the projected overall "
                "offensive-line rank. `SOS` is the full-season schedule rank for the player's "
                "position, where 1 is easiest and 32 hardest. D/ST rows use their defense SOS "
                "rank but retain `--` for the two offensive team metrics."
            ),
            (
                "`INJ` is the projected regular-season fantasy weeks missed from the "
                "cross-referenced injury context. Ranges preserve uncertainty; D/ST is `--`."
            ),
            (
                "The machine-readable context stores a color bucket beside every displayed "
                "value. Rank columns use green 1-10, yellow 11-22, and red 23-32. Depth-chart "
                "labels use green for order 1/DST, yellow for order 2, and red for order 3+ or "
                "unavailable. Injury labels use green for 0 weeks, yellow for 1-2 weeks, and "
                "red for 3+ weeks or an unresolved current injury."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def _defense_entry(
    entity: RankedEntity,
    schedule_rank: int | None,
    injury_label: str,
    injury_color: str,
) -> DepthChartEntry:
    return DepthChartEntry(
        rank=entity.rank,
        name=entity.name,
        team=entity.team,
        fantasy_position="DST",
        depth_chart_position="DST",
        depth_chart_order=None,
        pdf_label="DST",
        depth_chart_bucket=depth_chart_bucket("DST"),
        offense_rank=None,
        offense_bucket=rank_bucket(None),
        offensive_line_rank=None,
        offensive_line_bucket=rank_bucket(None),
        strength_of_schedule_rank=schedule_rank,
        strength_of_schedule_bucket=rank_bucket(schedule_rank),
        projected_injury_weeks=injury_label,
        injury_bucket=injury_color,
        match="team-defense",
        sleeper_player_id=None,
        espn_depth_chart_position=None,
        espn_depth_chart_order=None,
        depth_source_count=0,
        depth_source_agreement="not-applicable",
    )


def _unassigned_entry(
    entity: RankedEntity,
    match: str,
    offense_rank: int | None,
    offensive_line_rank: int | None,
    schedule_rank: int | None,
    injury_label: str,
    injury_color: str,
    espn_depth: tuple[str, int] | None = None,
) -> DepthChartEntry:
    espn_position, espn_order = espn_depth or (None, None)
    return DepthChartEntry(
        rank=entity.rank,
        name=entity.name,
        team=entity.team,
        fantasy_position=entity.position,
        depth_chart_position=None,
        depth_chart_order=None,
        pdf_label="--",
        depth_chart_bucket=depth_chart_bucket("--"),
        offense_rank=offense_rank,
        offense_bucket=rank_bucket(offense_rank),
        offensive_line_rank=offensive_line_rank,
        offensive_line_bucket=rank_bucket(offensive_line_rank),
        strength_of_schedule_rank=schedule_rank,
        strength_of_schedule_bucket=rank_bucket(schedule_rank),
        projected_injury_weeks=injury_label,
        injury_bucket=injury_color,
        match=match,
        sleeper_player_id=None,
        espn_depth_chart_position=espn_position,
        espn_depth_chart_order=espn_order,
        depth_source_count=1 if espn_depth is not None else 0,
        depth_source_agreement="espn-only" if espn_depth is not None else "unavailable",
    )


def _clean_chart_position(value: Any) -> str | None:
    text = str(value).strip().upper() if value is not None else ""
    return text or None


def _clean_chart_order(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    raise SystemExit(main())
