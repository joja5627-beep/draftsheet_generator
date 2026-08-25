"""Build current injury context for every ranked entity in the draft-sheet PDF."""

from __future__ import annotations

import argparse
import math
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import pdfplumber

from fantasy_football_2026.constants import (
    DEFAULT_SOURCE_PDF,
    DEFAULT_TIMEOUT_SECONDS,
    INJURY_REWEIGHTING_END,
    INJURY_REWEIGHTING_START,
    INJURY_SOURCE_LINKS,
    RESERVE_STATUSES,
    ContextFile,
    DirectoryName,
    SourceUrl,
)
from fantasy_football_2026.domain.normalization import normalize_name, normalize_team
from fantasy_football_2026.errors import ContextError, InjuryContextError, StorageError
from fantasy_football_2026.infrastructure.storage import DEFAULT_STORE, write_json, write_text
from fantasy_football_2026.infrastructure.web import CachedWebClient, CachePolicy, FetchResult
from fantasy_football_2026.presentation.buckets import injury_bucket
from fantasy_football_2026.presentation.pdf import SALARY_TOKEN, inspect_draft_sheet

SLEEPER_PLAYERS_URL = SourceUrl.SLEEPER_PLAYERS
SLEEPER_STATE_URL = SourceUrl.SLEEPER_STATE
ESPN_INJURIES_URL = SourceUrl.ESPN_INJURIES
ESPN_SCOREBOARD_URL = SourceUrl.ESPN_SCOREBOARD
SOURCE_LINKS = INJURY_SOURCE_LINKS
REWEIGHTING_START = INJURY_REWEIGHTING_START
REWEIGHTING_END = INJURY_REWEIGHTING_END


@dataclass(frozen=True, slots=True)
class RankedEntity:
    rank: int
    position_rank: str
    position: str
    name: str
    team: str
    bye_week: int | None
    entity_type: str


@dataclass(frozen=True, slots=True)
class SourceRecord:
    provider: str
    source_id: str | None
    name: str
    team: str | None
    position: str | None
    roster_status: str | None
    injury_status: str | None
    injury_type: str | None
    return_date: str | None
    updated_at: str | None
    source_url: str
    news_text: str = ""

    def public_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("news_text", None)
        return value


@dataclass(frozen=True, slots=True)
class MatchResult:
    record: SourceRecord | None
    method: str
    confidence: str


@dataclass(frozen=True, slots=True)
class Projection:
    games_min: int | None
    games_max: int | None
    games_estimate: float | None
    tier: str
    score: int | None
    confidence: str
    rationale: str


@dataclass(frozen=True, slots=True)
class PlayerContext:
    rank: int
    name: str
    position: str
    position_rank: str
    team: str
    bye_week: int | None
    entity_type: str
    tier: str
    risk_score: int | None
    projected_games_min: int | None
    projected_games_max: int | None
    projected_games_estimate: float | None
    projected_weeks_min: int | None
    projected_weeks_max: int | None
    projected_weeks_estimate: float | None
    pdf_weeks_label: str
    injury_bucket: str
    confidence: str
    current_signals: str
    rationale: str
    last_evidence_update: str | None
    sleeper_match: str
    espn_match: str
    sources_checked: tuple[str, ...]
    signal_source_count: int
    source_agreement: str
    evidence: tuple[dict[str, Any], ...]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build current injury context for the PPR Top 300 draft sheet."
    )
    parser.add_argument("--pdf", type=Path, default=Path(DEFAULT_SOURCE_PDF))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(DirectoryName.CONTEXT, ContextFile.INJURIES_MARKDOWN),
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=Path(DirectoryName.CONTEXT, ContextFile.INJURIES_JSON),
    )
    parser.add_argument(
        "--overrides",
        type=Path,
        default=None,
        help="optional explicit manual overrides; disabled in the automated rebuild",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path(DirectoryName.CONTEXT, DirectoryName.CACHE),
    )
    parser.add_argument(
        "--reweighting-context",
        type=Path,
        default=Path(DirectoryName.CONTEXT, ContextFile.GEMINI_RESEARCH_MARKDOWN),
        help="Markdown guide that receives the generated injury reweighting snapshot",
    )
    parser.add_argument(
        "--skip-reweighting-context",
        action="store_true",
        help="do not update the reweighting guide",
    )
    parser.add_argument("--refresh", action="store_true", help="ignore today's cache")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="use cached source data without making network requests",
    )
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = update_injury_context(
            pdf_path=args.pdf,
            markdown_path=args.output,
            json_path=args.json_output,
            overrides_path=args.overrides,
            cache_dir=args.cache_dir,
            refresh=args.refresh,
            offline=args.offline,
            timeout=args.timeout,
            reweighting_context_path=(
                None if args.skip_reweighting_context else args.reweighting_context
            ),
        )
    except (InjuryContextError, OSError, ValueError) as error:
        raise SystemExit(f"error: {error}") from error

    print(f"Ranked entities: {result['entity_count']}")
    print(f"NFL players: {result['player_count']}")
    print(f"Current injury signals: {result['flagged_count']}")
    print(f"Manual-review matches: {result['manual_review_count']}")
    print(f"Markdown: {Path(result['markdown_path']).resolve()}")
    print(f"JSON: {Path(result['json_path']).resolve()}")
    if result["reweighting_context_path"]:
        print(f"Reweighting context: {Path(result['reweighting_context_path']).resolve()}")
    return 0


def update_injury_context(
    *,
    pdf_path: Path,
    markdown_path: Path,
    json_path: Path,
    overrides_path: Path | None,
    cache_dir: Path,
    refresh: bool,
    offline: bool,
    timeout: float,
    reweighting_context_path: Path | None,
) -> dict[str, Any]:
    entities = extract_ranked_entities(pdf_path)
    if len(entities) != 300:
        raise InjuryContextError(f"Expected 300 ranked entities, extracted {len(entities)}.")

    now = datetime.now(UTC)
    fetches = _fetch_sources(
        cache_dir=cache_dir,
        refresh=refresh,
        offline=offline,
        timeout=timeout,
        now=now,
    )
    sleeper_records = parse_sleeper_records(fetches["sleeper_players"].payload)
    season_state = fetches["sleeper_state"].payload
    season = int(season_state.get("season", now.year))
    schedule_payloads = [
        fetches[f"espn_schedule_{season}"].payload,
        fetches[f"espn_schedule_{season + 1}"].payload,
    ]
    team_id_map = parse_espn_team_map(schedule_payloads)
    espn_records = parse_espn_records(fetches["espn_injuries"].payload, team_id_map)
    schedules = parse_espn_schedules(
        schedule_payloads,
        season=season,
    )
    overrides = load_overrides(overrides_path) if overrides_path is not None else {}

    sleeper_index = _record_index(sleeper_records)
    espn_index = _record_index(espn_records)
    contexts: list[PlayerContext] = []
    for entity in entities:
        if entity.entity_type != "player":
            contexts.append(_defense_context(entity))
            continue
        sleeper_match = match_record(entity, sleeper_index)
        espn_match = match_record(entity, espn_index)
        records = tuple(
            match.record for match in (sleeper_match, espn_match) if match.record is not None
        )
        override = overrides.get(normalize_name(entity.name))
        projection = project_games_missed(
            entity,
            records,
            schedules=schedules,
            season_phase=str(season_state.get("season_type") or "unknown"),
            as_of=now.date(),
            override=override,
        )
        contexts.append(
            _player_context(
                entity,
                sleeper_match,
                espn_match,
                projection,
                records,
                supplemental_evidence=_override_evidence(override),
            )
        )

    metadata = {
        "generated_at": now.isoformat(timespec="seconds"),
        "effective_date": now.date().isoformat(),
        "season": season,
        "season_phase": season_state.get("season_type"),
        "source_pdf": str(pdf_path),
        "sources": SOURCE_LINKS,
        "source_retrieval": {
            name: {
                "retrieved_at": fetch.retrieved_at,
                "from_cache": fetch.from_cache,
            }
            for name, fetch in fetches.items()
        },
        "model_scope": (
            "Current reported availability only; it does not predict future injuries "
            "for otherwise healthy players."
        ),
        "display_column": {
            "header": "INJ",
            "meaning": (
                "Projected regular-season fantasy weeks missed; ranges preserve uncertainty."
            ),
            "buckets": {
                "green": "0 weeks or D/ST not applicable",
                "yellow": "1-2 weeks at the upper end of the range",
                "red": "3+ weeks or unresolved current injury",
            },
        },
        "source_policy": (
            "Sleeper and ESPN are checked for every ranked player. Current signals require "
            "cross-source corroboration when available. Manual overrides are disabled in the "
            "automated rebuild and activate only through the explicit CLI option."
        ),
        "manual_overrides_enabled": overrides_path is not None,
    }
    json_document = {
        "metadata": metadata,
        "tier_definitions": tier_definitions(),
        "players": [asdict(context) for context in contexts],
    }
    write_json(json_path, json_document)
    write_text(markdown_path, render_markdown(metadata, contexts))
    if reweighting_context_path is not None:
        update_reweighting_context(reweighting_context_path, metadata, contexts)

    flagged = [
        context
        for context in contexts
        if context.entity_type == "player" and context.tier not in {"CLEAR", "N/A"}
    ]
    manual_review = [
        context
        for context in contexts
        if context.entity_type == "player"
        and context.sleeper_match.startswith("unmatched")
        and context.espn_match.startswith("unmatched")
    ]
    return {
        "entity_count": len(contexts),
        "player_count": sum(context.entity_type == "player" for context in contexts),
        "flagged_count": len(flagged),
        "manual_review_count": len(manual_review),
        "markdown_path": str(markdown_path),
        "json_path": str(json_path),
        "reweighting_context_path": (
            str(reweighting_context_path) if reweighting_context_path is not None else None
        ),
    }


def extract_ranked_entities(pdf_path: Path) -> tuple[RankedEntity, ...]:
    inspections = inspect_draft_sheet(pdf_path)
    entities: list[RankedEntity] = []
    with pdfplumber.open(pdf_path) as document:
        for inspection in inspections:
            page = document.pages[inspection.page_number - 1]
            words = page.extract_words(
                x_tolerance=1.5,
                y_tolerance=2.0,
                keep_blank_chars=False,
                use_text_flow=False,
            )
            for row in inspection.rows:
                column = inspection.columns[row.column]
                center = (row.top + row.bottom) / 2
                row_words = sorted(
                    (
                        word
                        for word in words
                        if column.x_start <= float(word["x0"]) <= column.x_end
                        and abs(((float(word["top"]) + float(word["bottom"])) / 2) - center) <= 1.5
                    ),
                    key=lambda word: float(word["x0"]),
                )
                entities.append(_parse_ranked_row(row.rank, row_words))
    return tuple(sorted(entities, key=lambda entity: entity.rank))


def _parse_ranked_row(rank: int, words: list[dict[str, Any]]) -> RankedEntity:
    texts = [str(word["text"]).strip() for word in words]
    if len(texts) < 6 or texts[0] != f"{rank}.":
        raise InjuryContextError(f"Could not parse ranking row {rank}: {texts}")
    position_rank = texts[1].strip("()")
    position_match = re.match(r"[A-Z/]+", position_rank)
    if not position_match:
        raise InjuryContextError(f"Could not parse position on ranking row {rank}: {texts}")
    position = position_match.group(0).replace("/", "")
    salary_index = next(
        (index for index, text in enumerate(texts) if SALARY_TOKEN.fullmatch(text)),
        None,
    )
    if salary_index is None or salary_index < 4:
        raise InjuryContextError(f"Could not find salary column on ranking row {rank}: {texts}")
    team = normalize_team(texts[salary_index - 1].rstrip(","))
    name = " ".join(texts[2 : salary_index - 1]).rstrip(",")
    bye_week = None
    if salary_index + 1 < len(texts) and texts[salary_index + 1].isdigit():
        bye_week = int(texts[salary_index + 1])
    return RankedEntity(
        rank=rank,
        position_rank=position_rank,
        position=position,
        name=name,
        team=team,
        bye_week=bye_week,
        entity_type="defense" if position == "DST" else "player",
    )


def parse_sleeper_records(payload: dict[str, Any]) -> tuple[SourceRecord, ...]:
    records: list[SourceRecord] = []
    for player_id, player in payload.items():
        name = player.get("full_name") or " ".join(
            part for part in (player.get("first_name"), player.get("last_name")) if part
        )
        if not name:
            continue
        news_updated = player.get("news_updated")
        updated_at = None
        if isinstance(news_updated, (int, float)) and news_updated > 0:
            updated_at = datetime.fromtimestamp(news_updated / 1000, tz=UTC).isoformat(
                timespec="seconds"
            )
        records.append(
            SourceRecord(
                provider="Sleeper",
                source_id=str(player_id),
                name=str(name),
                team=normalize_team(player.get("team")),
                position=str(player.get("position") or "") or None,
                roster_status=_clean_value(player.get("status")),
                injury_status=_clean_value(player.get("injury_status")),
                injury_type=_clean_value(player.get("injury_notes")),
                return_date=None,
                updated_at=updated_at,
                source_url=SLEEPER_PLAYERS_URL,
            )
        )
    return tuple(records)


def parse_espn_team_map(payloads: list[dict[str, Any]]) -> dict[str, str]:
    teams: dict[str, str] = {}
    for payload in payloads:
        for event in payload.get("events", []):
            for competition in event.get("competitions", []):
                for competitor in competition.get("competitors", []):
                    team = competitor.get("team") or {}
                    team_id = team.get("id")
                    abbreviation = normalize_team(team.get("abbreviation"))
                    if team_id and abbreviation:
                        teams[str(team_id)] = abbreviation
    return teams


def parse_espn_records(
    payload: dict[str, Any],
    team_id_map: dict[str, str],
) -> tuple[SourceRecord, ...]:
    records: list[SourceRecord] = []
    for team in payload.get("injuries", []):
        team_abbreviation = team_id_map.get(str(team.get("id")))
        for injury in team.get("injuries", []):
            athlete = injury.get("athlete") or {}
            name = athlete.get("displayName")
            if not name:
                continue
            details = injury.get("details") or {}
            links = athlete.get("links") or []
            source_url = next(
                (
                    link.get("href")
                    for link in links
                    if "news" in (link.get("rel") or []) and link.get("href")
                ),
                SourceUrl.ESPN_INJURY_PAGE,
            )
            injury_type = _clean_value(details.get("type"))
            records.append(
                SourceRecord(
                    provider="ESPN",
                    source_id=_clean_value(injury.get("id")),
                    name=str(name),
                    team=team_abbreviation,
                    position=None,
                    roster_status=None,
                    injury_status=_clean_value(injury.get("status")),
                    injury_type=injury_type,
                    return_date=_clean_value(details.get("returnDate")),
                    updated_at=_clean_value(injury.get("date")),
                    source_url=str(source_url),
                    # Long analysis often mentions injuries to teammates; using it for
                    # player-level inference creates false attribution.
                    news_text=str(injury.get("shortComment") or ""),
                )
            )
    return tuple(records)


def parse_espn_schedules(
    payloads: list[dict[str, Any]],
    *,
    season: int,
) -> dict[str, tuple[date, ...]]:
    schedules: dict[str, set[date]] = defaultdict(set)
    for payload in payloads:
        for event in payload.get("events", []):
            season_data = event.get("season") or {}
            if season_data.get("year") != season or season_data.get("type") != 2:
                continue
            event_date = _parse_date(event.get("date"))
            if event_date is None:
                continue
            competitions = event.get("competitions") or []
            if not competitions:
                continue
            for competitor in competitions[0].get("competitors", []):
                abbreviation = normalize_team((competitor.get("team") or {}).get("abbreviation"))
                if abbreviation:
                    schedules[abbreviation].add(event_date)
    return {team: tuple(sorted(dates)) for team, dates in schedules.items()}


def _record_index(records: tuple[SourceRecord, ...]) -> dict[str, list[SourceRecord]]:
    index: dict[str, list[SourceRecord]] = defaultdict(list)
    for record in records:
        index[normalize_name(record.name)].append(record)
    return index


def match_record(
    entity: RankedEntity,
    index: dict[str, list[SourceRecord]],
) -> MatchResult:
    target = normalize_name(entity.name)
    exact = index.get(target, [])
    if exact:
        return _choose_candidate(entity, exact, method="exact-name")

    target_last = target.split()[-1] if target else ""
    candidates: list[tuple[float, SourceRecord]] = []
    for candidate_name, records in index.items():
        if not candidate_name or candidate_name.split()[-1] != target_last:
            continue
        ratio = SequenceMatcher(None, target, candidate_name).ratio()
        if ratio < 0.88:
            continue
        for record in records:
            if record.team and normalize_team(record.team) != entity.team:
                continue
            candidates.append((ratio, record))
    if not candidates:
        return MatchResult(None, "unmatched", "low")
    candidates.sort(key=lambda item: item[0], reverse=True)
    best_ratio, best = candidates[0]
    if len(candidates) > 1 and math.isclose(best_ratio, candidates[1][0], abs_tol=0.01):
        return MatchResult(None, "unmatched-ambiguous", "low")
    return MatchResult(best, f"fuzzy-name:{best_ratio:.2f}", "medium")


def _choose_candidate(
    entity: RankedEntity,
    candidates: list[SourceRecord],
    *,
    method: str,
) -> MatchResult:
    team_matches = [record for record in candidates if normalize_team(record.team) == entity.team]
    position_matches = [
        record
        for record in (team_matches or candidates)
        if not record.position or record.position == entity.position
    ]
    choices = position_matches or team_matches or candidates
    if len(choices) == 1:
        confidence = "high" if team_matches else "medium"
        return MatchResult(choices[0], method, confidence)
    return MatchResult(None, "unmatched-ambiguous", "low")


def project_games_missed(
    entity: RankedEntity,
    records: tuple[SourceRecord, ...],
    *,
    schedules: dict[str, tuple[date, ...]],
    season_phase: str,
    as_of: date,
    override: dict[str, Any] | None,
) -> Projection:
    if override:
        minimum = _optional_int(override.get("games_min"))
        maximum = _optional_int(override.get("games_max"))
        if minimum is None or maximum is None or maximum < minimum:
            raise InjuryContextError(f"Invalid override games range for {entity.name}: {override}")
        return _projection(
            minimum,
            maximum,
            current_injury=True,
            confidence=str(override.get("confidence") or "high"),
            rationale=str(override.get("reason") or "Human-reviewed override."),
        )

    active_records = tuple(record for record in records if _record_has_signal(record))
    if not active_records:
        return Projection(
            games_min=0,
            games_max=0,
            games_estimate=0.0,
            tier="CLEAR",
            score=0,
            confidence="medium",
            rationale=(
                "No current injury designation was found in the matched live feeds; "
                "this is not a prediction of future health."
            ),
        )

    text_records = tuple(
        record
        for record in active_records
        if (record.injury_status or "").strip().lower()
        not in {"", "active", "healthy", "available"}
    )
    all_news = " ".join(record.news_text for record in text_records).lower()
    if re.search(
        r"season[- ]ending|out for (?:the )?season|miss (?:the )?(?:entire )?season|"
        r"will not play (?:again )?(?:this season|in 2026)",
        all_news,
    ) and any(
        value in " ".join(filter(None, (record.injury_status, record.roster_status))).lower()
        for record in text_records
        for value in ("out", "ir", "injured reserve")
    ):
        return _projection(
            17,
            17,
            current_injury=True,
            confidence="high",
            rationale="A current report explicitly describes a season-long absence.",
        )

    explicit_games = _explicit_games_range(all_news)
    if explicit_games:
        return _projection(
            *explicit_games,
            current_injury=True,
            confidence="high",
            rationale="A current report explicitly states an expected games-missed range.",
        )

    return_dates = sorted(
        parsed
        for parsed in (_parse_date(record.return_date) for record in active_records)
        if parsed is not None
    )
    if return_dates:
        expected_return = return_dates[-1]
        minimum, maximum = _games_range_for_return(schedules.get(entity.team, ()), expected_return)
        return _projection(
            minimum,
            maximum,
            current_injury=True,
            confidence="medium",
            rationale=(
                f"Structured expected return date {expected_return.isoformat()} maps to "
                f"{minimum}-{maximum} scheduled regular-season games before return; a game "
                "on the return date remains uncertain."
            ),
        )

    explicit_weeks = _explicit_weeks_range(all_news)
    if explicit_weeks:
        early_return = as_of + timedelta(weeks=explicit_weeks[0])
        late_return = as_of + timedelta(weeks=explicit_weeks[1])
        minimum = _games_range_for_return(schedules.get(entity.team, ()), early_return)[0]
        maximum = _games_range_for_return(schedules.get(entity.team, ()), late_return)[1]
        return _projection(
            minimum,
            maximum,
            current_injury=True,
            confidence="medium",
            rationale=(
                f"Reported {explicit_weeks[0]}-{explicit_weeks[1]} week recovery window "
                "was mapped against the team's regular-season schedule."
            ),
        )

    statuses = " ".join(
        value.lower()
        for record in active_records
        for value in (record.injury_status, record.roster_status)
        if value
    )
    if any(status in statuses for status in RESERVE_STATUSES):
        minimum, maximum = (0, 4) if season_phase == "pre" else (4, 8)
        return _projection(
            minimum,
            maximum,
            current_injury=True,
            confidence="low" if season_phase == "pre" else "medium",
            rationale=(
                "Reserve/PUP/NFI status lacks a reliable return date. During preseason, "
                "active-list versus reserve-list treatment is not yet final."
                if season_phase == "pre"
                else (
                    "Reserve-list status implies a multi-game absence without a reported "
                    "return date."
                )
            ),
        )
    if "out" in statuses:
        minimum = 0 if season_phase == "pre" else 1
        return _projection(
            minimum,
            1,
            current_injury=True,
            confidence="low" if season_phase == "pre" else "medium",
            rationale=(
                "An Out designation in preseason may apply only to an exhibition game."
                if season_phase == "pre"
                else "The current game-status designation is Out."
            ),
        )
    if "doubtful" in statuses:
        return _projection(
            0 if season_phase == "pre" else 1,
            1,
            current_injury=True,
            confidence="low",
            rationale="Doubtful indicates the player is unlikely to participate in the next game.",
        )
    if "questionable" in statuses or "limited" in statuses:
        return _projection(
            0,
            1,
            current_injury=True,
            confidence="low",
            rationale=(
                "Questionable/limited is a watch status, not evidence of a multi-game absence."
            ),
        )
    return Projection(
        games_min=None,
        games_max=None,
        games_estimate=None,
        tier="UNKNOWN",
        score=None,
        confidence="low",
        rationale="A current injury signal exists, but no defensible absence window was found.",
    )


def _explicit_games_range(news: str) -> tuple[int, int] | None:
    match = re.search(
        r"(?:expected|set|likely|will|could)\s+to\s+miss\s+"
        r"(?:at least\s+)?(\d{1,2})(?:\s*(?:-|to)\s*(\d{1,2}))?\s+games?",
        news,
    )
    if not match:
        return None
    minimum = int(match.group(1))
    maximum = int(match.group(2) or minimum)
    return min(minimum, maximum), max(minimum, maximum)


def _explicit_weeks_range(news: str) -> tuple[int, int] | None:
    match = re.search(
        r"(?:expected|set|likely|will|could)\s+to\s+(?:miss|be out|be sidelined)\s+"
        r"(?:for\s+)?(\d{1,2})(?:\s*(?:-|to)\s*(\d{1,2}))?\s+weeks?",
        news,
    )
    if not match:
        return None
    minimum = int(match.group(1))
    maximum = int(match.group(2) or minimum)
    return min(minimum, maximum), max(minimum, maximum)


def _projection(
    minimum: int,
    maximum: int,
    *,
    current_injury: bool,
    confidence: str,
    rationale: str,
) -> Projection:
    minimum = max(0, min(17, minimum))
    maximum = max(minimum, min(17, maximum))
    estimate = round((minimum + maximum) / 2, 1)
    if maximum == 0:
        tier, score = ("WATCH", 1) if current_injury else ("CLEAR", 0)
    elif maximum <= 1:
        tier, score = "WATCH", 1
    elif maximum <= 2:
        tier, score = "SHORT", 2
    elif maximum <= 4:
        tier, score = "MEDIUM", 3
    elif maximum <= 8:
        tier, score = "HIGH", 4
    elif maximum <= 16:
        tier, score = "VERY HIGH", 5
    else:
        tier, score = "SEASON", 6
    return Projection(minimum, maximum, estimate, tier, score, confidence, rationale)


def _record_has_signal(record: SourceRecord) -> bool:
    injury_status = (record.injury_status or "").strip().lower()
    if injury_status and injury_status not in {"active", "healthy", "available"}:
        return True
    if record.injury_type or record.return_date:
        return True
    roster_status = (record.roster_status or "").lower()
    return any(status in roster_status for status in RESERVE_STATUSES)


def _games_range_for_return(schedule: tuple[date, ...], return_date: date) -> tuple[int, int]:
    minimum = min(17, sum(game_date < return_date for game_date in schedule))
    maximum = min(17, sum(game_date <= return_date for game_date in schedule))
    return minimum, maximum


def _player_context(
    entity: RankedEntity,
    sleeper_match: MatchResult,
    espn_match: MatchResult,
    projection: Projection,
    records: tuple[SourceRecord, ...],
    *,
    supplemental_evidence: tuple[dict[str, Any], ...] = (),
) -> PlayerContext:
    signals: list[str] = []
    for record in records:
        if not _record_has_signal(record):
            continue
        parts = [record.provider]
        if record.injury_status:
            parts.append(record.injury_status)
        if record.injury_type:
            parts.append(record.injury_type)
        if record.return_date:
            parts.append(f"return {record.return_date}")
        if len(parts) > 1:
            signals.append(" ".join(parts))
    updated_values = [record.updated_at for record in records if record.updated_at]
    updated_values.extend(
        str(item["updated_at"])
        for item in supplemental_evidence
        if item.get("updated_at") and item.get("updated_at") != "date unavailable"
    )
    evidence = tuple(record.public_dict() for record in records if _record_has_signal(record))
    evidence += supplemental_evidence
    providers = {str(item.get("provider")) for item in evidence if item.get("provider")}
    weeks_label = _projection_weeks_label(projection)
    return PlayerContext(
        rank=entity.rank,
        name=entity.name,
        position=entity.position,
        position_rank=entity.position_rank,
        team=entity.team,
        bye_week=entity.bye_week,
        entity_type=entity.entity_type,
        tier=projection.tier,
        risk_score=projection.score,
        projected_games_min=projection.games_min,
        projected_games_max=projection.games_max,
        projected_games_estimate=projection.games_estimate,
        projected_weeks_min=projection.games_min,
        projected_weeks_max=projection.games_max,
        projected_weeks_estimate=projection.games_estimate,
        pdf_weeks_label=weeks_label,
        injury_bucket=injury_bucket(weeks_label),
        confidence=projection.confidence,
        current_signals="; ".join(signals) or "No current designation found",
        rationale=projection.rationale,
        last_evidence_update=max(updated_values) if updated_values else None,
        sleeper_match=f"{sleeper_match.method} ({sleeper_match.confidence})",
        espn_match=f"{espn_match.method} ({espn_match.confidence})",
        sources_checked=("Sleeper", "ESPN"),
        signal_source_count=len(providers),
        source_agreement=(
            "corroborated"
            if len(providers) >= 2
            else "single-source"
            if providers
            else "no-current-signal"
        ),
        evidence=evidence,
    )


def _defense_context(entity: RankedEntity) -> PlayerContext:
    return PlayerContext(
        rank=entity.rank,
        name=entity.name,
        position=entity.position,
        position_rank=entity.position_rank,
        team=entity.team,
        bye_week=entity.bye_week,
        entity_type="defense",
        tier="N/A",
        risk_score=None,
        projected_games_min=None,
        projected_games_max=None,
        projected_games_estimate=None,
        projected_weeks_min=None,
        projected_weeks_max=None,
        projected_weeks_estimate=None,
        pdf_weeks_label="--",
        injury_bucket=injury_bucket("--"),
        confidence="n/a",
        current_signals="Team defense - individual injury model not applicable",
        rationale="D/ST rows represent a unit, not one player.",
        last_evidence_update=None,
        sleeper_match="not-applicable",
        espn_match="not-applicable",
        sources_checked=(),
        signal_source_count=0,
        source_agreement="not-applicable",
        evidence=(),
    )


def _projection_weeks_label(projection: Projection) -> str:
    minimum = projection.games_min
    maximum = projection.games_max
    if minimum is None or maximum is None:
        return "?"
    return str(minimum) if minimum == maximum else f"{minimum}-{maximum}"


def _override_evidence(override: dict[str, Any] | None) -> tuple[dict[str, Any], ...]:
    if not override:
        return ()
    sources = override.get("sources") or []
    if not isinstance(sources, list):
        raise InjuryContextError("Injury override sources must be a list.")
    evidence: list[dict[str, Any]] = []
    for source in sources:
        if not isinstance(source, dict) or not source.get("provider") or not source.get("url"):
            raise InjuryContextError(
                "Each injury override source requires provider and url fields."
            )
        evidence.append(
            {
                "provider": str(source["provider"]),
                "source_url": str(source["url"]),
                "updated_at": str(source.get("updated_at") or "date unavailable"),
                "note": str(source.get("note") or "Human-reviewed corroboration."),
            }
        )
    return tuple(evidence)


def render_markdown(metadata: dict[str, Any], contexts: list[PlayerContext]) -> str:
    counts = Counter(context.tier for context in contexts)
    player_count = sum(context.entity_type == "player" for context in contexts)
    review_count = sum(
        context.entity_type == "player"
        and context.sleeper_match.startswith("unmatched")
        and context.espn_match.startswith("unmatched")
        for context in contexts
    )
    flagged_players = [
        context
        for context in contexts
        if context.entity_type == "player" and context.tier not in {"CLEAR", "N/A"}
    ]
    corroborated_count = sum(
        context.source_agreement == "corroborated" for context in flagged_players
    )
    lines = [
        "# 2026 PPR Top 300 injury context",
        "",
        f"**Effective date:** {metadata['effective_date']}",
        f"**Generated:** {metadata['generated_at']}",
        f"**Season phase:** {metadata['season_phase']}",
        f"**Coverage:** {player_count} players plus {len(contexts) - player_count} D/ST rows; "
        f"{review_count} players require manual identity review.",
        (
            f"**Cross-source coverage:** {corroborated_count}/{len(flagged_players)} current "
            "injury signals are corroborated by at least two named providers."
        ),
        "",
        "> This is fantasy-football availability context, not medical advice. A blank live-feed "
        "designation means no current designation was found; it does not guarantee health or "
        "predict future injury.",
        "",
        "## Ranking model",
        "",
        "The PDF's `INJ` value is the projected regular-season fantasy weeks missed. Because an "
        "NFL team ordinarily plays once per week, it uses the same schedule-mapped range as the "
        "games-missed model. Structured expected-return dates are mapped to each team's schedule. "
        "Status-only projections are deliberately broad, especially during preseason.",
        "",
        "Color buckets use the shared PDF palette: green for 0 weeks, yellow when the upper end "
        "is 1-2 weeks, and red for 3+ weeks or an unresolved active injury. D/ST is `--` because "
        "the individual-player estimate does not apply.",
        "",
        "| Score | Tier | Projected games missed | Interpretation |",
        "|---:|---|---:|---|",
    ]
    for tier in tier_definitions():
        lines.append(f"| {tier['score']} | {tier['tier']} | {tier['games']} | {tier['meaning']} |")

    lines.extend(["", "## Current tier counts", ""])
    lines.append(
        ", ".join(
            f"**{tier}:** {counts.get(tier, 0)}"
            for tier in ("SEASON", "VERY HIGH", "HIGH", "MEDIUM", "SHORT", "WATCH", "CLEAR")
        )
    )

    risky = sorted(
        (
            context
            for context in contexts
            if context.entity_type == "player"
            and context.projected_games_max is not None
            and context.projected_games_max >= 2
        ),
        key=lambda context: (
            -(context.projected_games_max or 0),
            -(context.projected_games_estimate or 0),
            context.rank,
        ),
    )
    lines.extend(
        [
            "",
            "## Highest current absence risk",
            "",
            "| Rank | Player | Pos-Team | Tier | Weeks | Confidence | Sources | Current signals |",
            "|---:|---|---|---|---:|---|---:|---|",
        ]
    )
    if risky:
        for context in risky:
            lines.append(_markdown_row(context, include_signal=True))
    else:
        lines.append(
            "| - | No players currently project above one missed week | - | - | - | - | - | - |"
        )

    lines.extend(
        [
            "",
            "## Full draft-sheet context",
            "",
            "| Rank | Player | Pos-Team | Tier | Weeks | Confidence | Sources | Current signals |",
            "|---:|---|---|---|---:|---|---:|---|",
        ]
    )
    for context in contexts:
        lines.append(_markdown_row(context, include_signal=True))

    flagged = flagged_players
    lines.extend(["", "## Evidence notes for flagged players", ""])
    if not flagged:
        lines.append("No current injury signals were found.")
    for context in flagged:
        lines.extend(
            [
                f"### {context.rank}. {context.name} ({context.position}, {context.team})",
                "",
                f"- **Projection:** {context.tier}, {context.pdf_weeks_label} fantasy weeks, "
                f"{context.confidence} confidence.",
                f"- **Cross-source status:** {context.source_agreement}; "
                f"{context.signal_source_count} signal provider(s).",
                f"- **Why:** {_escape_markdown(context.rationale)}",
                f"- **Signals:** {_escape_markdown(context.current_signals)}",
            ]
        )
        for evidence in context.evidence:
            label = evidence["provider"]
            url = evidence["source_url"]
            updated = evidence.get("updated_at") or "date unavailable"
            lines.append(f"- **Source:** [{label}]({url}), updated {updated}.")
        lines.append("")

    lines.extend(
        [
            "## Method and limitations",
            "",
            "- Sleeper is the broad player-identity/status feed and should be cached no more than "
            "once daily. Its game-week injury labels can reset early Wednesday.",
            "- ESPN supplies structured injury type, status, news date, and expected return date "
            "when available. Return dates are estimates, not guarantees.",
            "- Sleeper and ESPN are queried for every ranked player. An explicitly requested "
            "diagnostic run can opt into `injury_overrides.json`; the default rebuild never "
            "loads it.",
            "- Official NFL Questionable, Doubtful, and Out labels describe the upcoming game's "
            "availability. Formal regular-season reports begin in Week 1, so preseason labels are "
            "lower-confidence.",
            "- Reserve/PUP and reserve/NFI can impose multi-game minimums, but active/PUP during "
            "training camp can be removed before final roster decisions. The model therefore uses "
            "0-4 games for preseason status-only cases.",
            "- Published injury-risk systems also use history, age, position, workload, and prior "
            "games missed. This file intentionally does not imitate a proprietary future-injury "
            "model; it ranks only current reported absence risk.",
            "- Exact source comments are not copied into this context. Follow the linked player "
            "source before making a draft decision, especially when feeds disagree.",
            "",
            "## Sources",
            "",
        ]
    )
    for label, url in SOURCE_LINKS.items():
        lines.append(f"- [{label}]({url})")
    lines.append("")
    return "\n".join(lines)


def update_reweighting_context(
    path: Path,
    metadata: dict[str, Any],
    contexts: list[PlayerContext],
) -> None:
    if not path.exists():
        raise InjuryContextError(f"Reweighting context does not exist: {path}")
    content = path.read_text(encoding="utf-8")
    section = render_reweighting_section(metadata, contexts)
    if REWEIGHTING_START in content or REWEIGHTING_END in content:
        if content.count(REWEIGHTING_START) != 1 or content.count(REWEIGHTING_END) != 1:
            raise InjuryContextError(
                f"Reweighting markers must each appear exactly once in {path}."
            )
        start = content.index(REWEIGHTING_START)
        end = content.index(REWEIGHTING_END, start) + len(REWEIGHTING_END)
        updated = content[:start] + section + content[end:]
    else:
        heading = "## Current injury and role watchlist"
        if content.count(heading) != 1:
            raise InjuryContextError(f"Could not find one injury watchlist heading in {path}.")
        insertion = content.index("\n", content.index(heading)) + 1
        updated = content[:insertion] + "\n" + section + "\n" + content[insertion:]
    write_text(path, updated)


def render_reweighting_section(metadata: dict[str, Any], contexts: list[PlayerContext]) -> str:
    players = [context for context in contexts if context.entity_type == "player"]
    tier_counts = Counter(context.tier for context in players)
    material = sorted(
        (
            context
            for context in players
            if context.projected_games_max is not None and context.projected_games_max >= 1
        ),
        key=lambda context: (-(context.projected_games_max or 0), context.rank),
    )
    zero_game_watch = [
        context
        for context in players
        if context.tier == "WATCH" and context.projected_games_max == 0
    ]
    lines = [
        REWEIGHTING_START,
        "### Live injury reweighting snapshot",
        "",
        f"**Effective date:** {metadata['effective_date']}",
        "",
        "**Source:** [generated player injury context](./player_injuries.md)",
        "**Evidence policy:** Sleeper and ESPN are checked for every player; active signals "
        "are corroborated with dated team or specialist reports when a feed is incomplete.",
        "",
        "Apply injury information through the existing **0-5 total risk penalty**, not as "
        "an additional uncapped deduction:",
        "",
        "1. If the baseline projection does **not** include the reported absence, multiply its "
        "season points by `availability factor = (17 - projected games missed) / 17`, then "
        "recalculate VORP. Use the midpoint when the context reports a range.",
        "2. If the baseline already includes the absence, do not apply that factor again. Use "
        "only residual role/timeline uncertainty inside the existing risk penalty.",
        "3. If the tool cannot reproject games, use the fallback penalty below. Never apply "
        "both the availability factor and the full fallback injury penalty.",
        "",
        "| Injury tier | Base fallback penalty | Draft treatment |",
        "|---|---:|---|",
        "| CLEAR | 0 | No injury adjustment |",
        "| WATCH, 0 games projected | 0.25 | Tiebreaker only |",
        "| WATCH, up to 1 game | 0.5 | Small same-tier downgrade |",
        "| SHORT | 1.5 | Meaningful same-tier downgrade |",
        "| MEDIUM | 2.5 | Move toward the bottom of the tier |",
        "| HIGH | 4.0 | Major discount; require roster/IR plan |",
        "| VERY HIGH | 5.0 | Late stash only when format supports it |",
        "| SEASON | Remove | Do not leave on the active redraft board |",
        "",
        "Multiply the fallback penalty by confidence: **high 1.0**, **medium 0.85**, "
        "**low 0.60**. Injury plus suspension, role, and other uncertainty remains capped at "
        "the guide's existing five-point total risk penalty.",
        "",
        "Current player tiers: "
        + ", ".join(
            f"**{tier} {tier_counts.get(tier, 0)}**"
            for tier in ("SEASON", "VERY HIGH", "HIGH", "MEDIUM", "SHORT", "WATCH", "CLEAR")
        )
        + ".",
        "",
        "#### Players with possible regular-season availability impact",
        "",
        "| Rank | Player | Tier | Weeks | Availability factor | Fallback penalty | "
        "Confidence | Sources | Signal |",
        "|---:|---|---|---:|---:|---:|---|---:|---|",
    ]
    if material:
        for context in material:
            lines.append(
                f"| {context.rank} | {_escape_markdown(context.name)} | {context.tier} | "
                f"{_games_label(context)} | {_availability_factor(context):.2f} | "
                f"{_fallback_injury_penalty(context):.1f} | {context.confidence} | "
                f"{context.signal_source_count} | "
                f"{_escape_markdown(context.current_signals)} |"
            )
    else:
        lines.append("| - | None currently identified | - | - | - | - | - | - | - |")

    lines.extend(
        [
            "",
            "#### Watchlist with no regular-season games currently projected",
            "",
            (
                ", ".join(f"{context.name} (#{context.rank})" for context in zero_game_watch)
                if zero_game_watch
                else "None."
            ),
            "",
            "Treat this snapshot as time-sensitive. The full context includes evidence dates, "
            "source links, confidence, and rationale for every ranked player. A CLEAR result "
            "means no current designation was found; it is not a forecast of future health.",
            REWEIGHTING_END,
        ]
    )
    return "\n".join(lines)


def _availability_factor(context: PlayerContext) -> float:
    if context.projected_games_estimate is None:
        return 1.0
    return max(0.0, min(1.0, (17 - context.projected_games_estimate) / 17))


def _fallback_injury_penalty(context: PlayerContext) -> float:
    base_by_tier = {
        "CLEAR": 0.0,
        "WATCH": 0.25 if context.projected_games_max == 0 else 0.5,
        "SHORT": 1.5,
        "MEDIUM": 2.5,
        "HIGH": 4.0,
        "VERY HIGH": 5.0,
        "SEASON": 5.0,
    }
    confidence_multiplier = {"high": 1.0, "medium": 0.85, "low": 0.60}
    base = base_by_tier.get(context.tier, 0.0)
    multiplier = confidence_multiplier.get(context.confidence, 0.60)
    return min(5.0, round(base * multiplier, 1))


def _markdown_row(context: PlayerContext, *, include_signal: bool) -> str:
    signal = _escape_markdown(context.current_signals) if include_signal else ""
    return (
        f"| {context.rank} | {_escape_markdown(context.name)} | "
        f"{context.position}-{context.team} | {context.tier} | {context.pdf_weeks_label} | "
        f"{context.confidence} | {context.signal_source_count} | {signal} |"
    )


def _games_label(context: PlayerContext) -> str:
    minimum = context.projected_games_min
    maximum = context.projected_games_max
    if minimum is None or maximum is None:
        return "?"
    return str(minimum) if minimum == maximum else f"{minimum}-{maximum}"


def tier_definitions() -> list[dict[str, Any]]:
    return [
        {"score": 0, "tier": "CLEAR", "games": "0", "meaning": "No current absence projected"},
        {"score": 1, "tier": "WATCH", "games": "0-1", "meaning": "Monitor; next-game uncertainty"},
        {"score": 2, "tier": "SHORT", "games": "2", "meaning": "Short absence"},
        {
            "score": 3,
            "tier": "MEDIUM",
            "games": "3-4",
            "meaning": "Meaningful early-season absence",
        },
        {"score": 4, "tier": "HIGH", "games": "5-8", "meaning": "Large availability discount"},
        {"score": 5, "tier": "VERY HIGH", "games": "9-16", "meaning": "Most of season at risk"},
        {"score": 6, "tier": "SEASON", "games": "17", "meaning": "Season-long absence reported"},
    ]


def load_overrides(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        payload = DEFAULT_STORE.load_object(path)
    except StorageError as error:
        raise InjuryContextError(str(error)) from error
    players = payload.get("players", {})
    if not isinstance(players, dict):
        raise InjuryContextError(f"Override file must contain a players object: {path}")
    return {normalize_name(name): value for name, value in players.items()}


def _clean_value(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    text = str(value).strip()
    try:
        if "T" in text:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _escape_markdown(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _fetch_sources(
    *,
    cache_dir: Path,
    refresh: bool,
    offline: bool,
    timeout: float,
    now: datetime,
) -> dict[str, FetchResult[Any]]:
    state = _fetch_json(
        "sleeper_state",
        SLEEPER_STATE_URL,
        cache_dir=cache_dir,
        refresh=refresh,
        offline=offline,
        timeout=timeout,
        now=now,
    )
    season = int(state.payload.get("season", now.year))
    requests = {
        "sleeper_state": state,
        "sleeper_players": _fetch_json(
            "sleeper_players",
            SLEEPER_PLAYERS_URL,
            cache_dir=cache_dir,
            refresh=refresh,
            offline=offline,
            timeout=timeout,
            now=now,
        ),
        "espn_injuries": _fetch_json(
            "espn_injuries",
            ESPN_INJURIES_URL,
            cache_dir=cache_dir,
            refresh=refresh,
            offline=offline,
            timeout=timeout,
            now=now,
        ),
    }
    for schedule_year in (season, season + 1):
        name = f"espn_schedule_{schedule_year}"
        requests[name] = _fetch_json(
            name,
            ESPN_SCOREBOARD_URL.format(year=schedule_year),
            cache_dir=cache_dir,
            refresh=refresh,
            offline=offline,
            timeout=timeout,
            now=now,
        )
    return requests


def _fetch_json(
    name: str,
    url: str,
    *,
    cache_dir: Path,
    refresh: bool,
    offline: bool,
    timeout: float,
    now: datetime,
) -> FetchResult[Any]:
    cache_path = cache_dir / f"{name}.json"
    try:
        return CachedWebClient(
            CachePolicy(
                refresh=refresh,
                offline=offline,
                timeout=timeout,
                current_day_only=True,
                stale_if_error=True,
            ),
            now=lambda: now,
        ).fetch_json(name=name, url=url, cache_path=cache_path)
    except (ContextError, StorageError) as error:
        raise InjuryContextError(str(error)) from error
