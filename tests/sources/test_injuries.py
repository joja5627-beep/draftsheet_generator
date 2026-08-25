import json
from datetime import date
from pathlib import Path

import pytest

from fantasy_football_2026.sources.injuries import (
    PlayerContext,
    RankedEntity,
    SourceRecord,
    _explicit_games_range,
    _fallback_injury_penalty,
    extract_ranked_entities,
    normalize_name,
    project_games_missed,
    update_reweighting_context,
)

SOURCE_PDF = Path("NFL26_CS_PPR300.pdf")
INJURY_CONTEXT = Path("context/player_injuries.json")
requires_source_pdf = pytest.mark.skipif(
    not SOURCE_PDF.is_file(),
    reason="requires the locally downloaded ESPN draft-kit PDF",
)
requires_injury_context = pytest.mark.skipif(
    not INJURY_CONTEXT.is_file(),
    reason="requires generated injury context",
)


@requires_source_pdf
def test_extracts_all_ranked_entities_from_real_sheet() -> None:
    entities = extract_ranked_entities(SOURCE_PDF)
    assert len(entities) == 300
    assert entities[0].name == "Jahmyr Gibbs"
    assert entities[0].position == "RB"
    assert entities[0].team == "DET"
    assert entities[-1].entity_type == "defense"


def test_name_normalization_handles_initials_suffixes_and_punctuation() -> None:
    assert normalize_name("Marvin Mims Jr.") == normalize_name("Marvin Mims")
    assert normalize_name("D.J. Giddens") == "d j giddens"
    assert normalize_name("Wan'Dale Robinson") == "wan dale robinson"


def test_explicit_games_pattern_ignores_historical_missed_games() -> None:
    assert _explicit_games_range("he missed 14 games in 2025") is None
    assert _explicit_games_range("he is expected to miss 3-5 games") == (3, 5)


def test_return_date_maps_to_team_schedule() -> None:
    entity = RankedEntity(1, "RB1", "RB", "Example Player", "DET", 6, "player")
    record = SourceRecord(
        provider="ESPN",
        source_id="1",
        name=entity.name,
        team="DET",
        position=None,
        roster_status=None,
        injury_status="Questionable",
        injury_type="Hamstring",
        return_date="2026-09-21",
        updated_at="2026-08-21T00:00:00Z",
        source_url="https://example.com",
    )
    projection = project_games_missed(
        entity,
        (record,),
        schedules={"DET": (date(2026, 9, 10), date(2026, 9, 17), date(2026, 9, 24))},
        season_phase="pre",
        as_of=date(2026, 8, 21),
        override=None,
    )
    assert projection.games_min == 2
    assert projection.games_max == 2
    assert projection.tier == "SHORT"


def test_return_date_on_game_day_keeps_that_game_uncertain() -> None:
    entity = RankedEntity(1, "RB1", "RB", "Example Player", "DET", 6, "player")
    record = SourceRecord(
        provider="ESPN",
        source_id="1",
        name=entity.name,
        team="DET",
        position=None,
        roster_status=None,
        injury_status="Questionable",
        injury_type="Hamstring",
        return_date="2026-09-17",
        updated_at="2026-08-21T00:00:00Z",
        source_url="https://example.com",
    )
    projection = project_games_missed(
        entity,
        (record,),
        schedules={"DET": (date(2026, 9, 10), date(2026, 9, 17))},
        season_phase="pre",
        as_of=date(2026, 8, 21),
        override=None,
    )
    assert (projection.games_min, projection.games_max) == (1, 2)


def test_preseason_pup_is_a_range_not_an_automatic_four_game_absence() -> None:
    entity = RankedEntity(1, "RB1", "RB", "Example Player", "DET", 6, "player")
    record = SourceRecord(
        provider="Sleeper",
        source_id="1",
        name=entity.name,
        team="DET",
        position="RB",
        roster_status="Active",
        injury_status="PUP",
        injury_type="Knee",
        return_date=None,
        updated_at="2026-08-21T00:00:00Z",
        source_url="https://example.com",
    )
    projection = project_games_missed(
        entity,
        (record,),
        schedules={},
        season_phase="pre",
        as_of=date(2026, 8, 21),
        override=None,
    )
    assert (projection.games_min, projection.games_max) == (0, 4)
    assert projection.confidence == "low"


def test_teammate_season_ending_news_does_not_set_player_to_season() -> None:
    entity = RankedEntity(1, "WR1", "WR", "Example Smith", "DET", 6, "player")
    record = SourceRecord(
        provider="ESPN",
        source_id="1",
        name=entity.name,
        team="DET",
        position=None,
        roster_status=None,
        injury_status="Questionable",
        injury_type="Hamstring",
        return_date=None,
        updated_at="2026-08-21T00:00:00Z",
        source_url="https://example.com",
        news_text="Smith could see more work after a teammate suffered a season-ending injury.",
    )
    projection = project_games_missed(
        entity,
        (record,),
        schedules={},
        season_phase="pre",
        as_of=date(2026, 8, 21),
        override=None,
    )
    assert projection.tier == "WATCH"


def test_injury_penalty_uses_tier_and_confidence_without_exceeding_cap() -> None:
    context = _example_player_context(tier="HIGH", confidence="medium", games=(5, 6))
    assert _fallback_injury_penalty(context) == 3.4


def test_reweighting_context_update_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "guide.md"
    path.write_text(
        "# Guide\n\n## Current injury and role watchlist\n\nEditorial notes.\n",
        encoding="utf-8",
    )
    metadata = {"effective_date": "2026-08-21"}
    contexts = [_example_player_context(tier="WATCH", confidence="medium", games=(0, 1))]

    update_reweighting_context(path, metadata, contexts)
    update_reweighting_context(path, metadata, contexts)

    result = path.read_text(encoding="utf-8")
    assert result.count("BEGIN GENERATED INJURY REWEIGHTING") == 1
    assert result.count("END GENERATED INJURY REWEIGHTING") == 1
    assert "Editorial notes." in result
    assert "Example Player" in result


@requires_injury_context
def test_real_injury_context_corroborates_every_current_signal() -> None:
    payload = json.loads(INJURY_CONTEXT.read_text(encoding="utf-8"))
    flagged = [
        player
        for player in payload["players"]
        if player["entity_type"] == "player" and player["tier"] != "CLEAR"
    ]

    assert flagged
    single_source = [player for player in flagged if player["source_agreement"] == "single-source"]
    assert all(
        player["signal_source_count"] >= 2 for player in flagged if player not in single_source
    )
    assert all(player["signal_source_count"] == 1 for player in single_source)
    assert all(player["confidence"] == "low" for player in single_source)


def _example_player_context(*, tier: str, confidence: str, games: tuple[int, int]) -> PlayerContext:
    return PlayerContext(
        rank=1,
        name="Example Player",
        position="RB",
        position_rank="RB1",
        team="DET",
        bye_week=6,
        entity_type="player",
        tier=tier,
        risk_score=4,
        projected_games_min=games[0],
        projected_games_max=games[1],
        projected_games_estimate=(games[0] + games[1]) / 2,
        projected_weeks_min=games[0],
        projected_weeks_max=games[1],
        projected_weeks_estimate=(games[0] + games[1]) / 2,
        pdf_weeks_label=str(games[0]) if games[0] == games[1] else f"{games[0]}-{games[1]}",
        injury_bucket="red" if games[1] >= 3 else "yellow" if games[1] else "green",
        confidence=confidence,
        current_signals="ESPN Questionable knee",
        rationale="Test rationale.",
        last_evidence_update="2026-08-21T00:00:00Z",
        sleeper_match="exact-name (high)",
        espn_match="exact-name (high)",
        sources_checked=("Sleeper", "ESPN"),
        signal_source_count=2,
        source_agreement="corroborated",
        evidence=(),
    )
