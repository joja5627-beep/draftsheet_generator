from pathlib import Path

import pytest

from fantasy_football_2026.depth_chart_context import (
    build_depth_chart_entries,
    depth_chart_label,
    load_injury_displays,
    load_team_projections,
    parse_espn_depth_charts,
)
from fantasy_football_2026.injury_context import RankedEntity
from fantasy_football_2026.schedule_context import load_schedule_ranks

SCHEDULE_CONTEXT = Path("context/strength_of_schedule.json")
INJURY_CONTEXT = Path("context/player_injuries.json")
requires_schedule_context = pytest.mark.skipif(
    not SCHEDULE_CONTEXT.is_file(),
    reason="requires generated strength-of-schedule context",
)
requires_injury_context = pytest.mark.skipif(
    not INJURY_CONTEXT.is_file(),
    reason="requires generated injury context",
)


def test_depth_chart_label_preserves_receiver_alignment() -> None:
    assert depth_chart_label("RB", 1) == "RB1"
    assert depth_chart_label("LWR", 1) == "LWR1"
    assert depth_chart_label(None, None) == "--"


def test_parse_espn_depth_charts_preserves_offensive_order() -> None:
    payload = {
        "DET": {
            "depthchart": [
                {
                    "positions": {
                        "rb": {
                            "position": {"abbreviation": "RB"},
                            "athletes": [
                                {"displayName": "Example Starter"},
                                {"displayName": "Example Backup"},
                            ],
                        }
                    }
                }
            ]
        }
    }

    depths = parse_espn_depth_charts(payload)

    assert depths[("DET", "example starter")] == ("RB", 1)
    assert depths[("DET", "example backup")] == ("RB", 2)


def test_build_depth_chart_entries_handles_players_and_defenses() -> None:
    entities = (
        RankedEntity(1, "RB1", "RB", "Example Runner", "DET", 6, "player"),
        RankedEntity(2, "DST1", "DST", "Lions D/ST", "DET", 6, "defense"),
    )
    sleeper_payload = {
        "123": {
            "full_name": "Example Runner",
            "team": "DET",
            "position": "RB",
            "depth_chart_position": "RB",
            "depth_chart_order": 1,
        }
    }

    schedules = {"DET": {"RB": 2, "DEF": 3}}
    entries = build_depth_chart_entries(
        entities,
        sleeper_payload,
        {"DET": (3, 14)},
        schedules,
        {1: ("0", "green"), 2: ("--", "green")},
    )

    assert entries[0].pdf_label == "RB1"
    assert entries[0].depth_chart_bucket == "green"
    assert entries[0].offense_rank == 3
    assert entries[0].offense_bucket == "green"
    assert entries[0].offensive_line_rank == 14
    assert entries[0].offensive_line_bucket == "yellow"
    assert entries[0].strength_of_schedule_rank == 2
    assert entries[0].strength_of_schedule_bucket == "green"
    assert entries[0].projected_injury_weeks == "0"
    assert entries[0].injury_bucket == "green"
    assert entries[0].match == "exact-name-team"
    assert entries[1].pdf_label == "DST"
    assert entries[1].depth_chart_bucket == "green"
    assert entries[1].offense_rank is None
    assert entries[1].offense_bucket == "red"
    assert entries[1].strength_of_schedule_rank == 3
    assert entries[1].strength_of_schedule_bucket == "green"
    assert entries[1].projected_injury_weeks == "--"
    assert entries[1].injury_bucket == "green"
    assert entries[1].match == "team-defense"


def test_real_team_projection_context_covers_every_nfl_team() -> None:
    projections = load_team_projections(Path("context/team_projections.json"))

    assert len(projections) == 32
    assert projections["LAR"] == (1, 5)
    assert projections["DEN"] == (21, 1)


@requires_schedule_context
def test_real_schedule_context_covers_every_team_and_position() -> None:
    schedules = load_schedule_ranks(SCHEDULE_CONTEXT)

    assert len(schedules) == 32
    assert all(len(positions) == 6 for positions in schedules.values())
    assert schedules["DET"]["RB"] == 2
    assert schedules["PHI"]["WR"] == 1


@requires_injury_context
def test_real_injury_context_covers_every_rank() -> None:
    displays = load_injury_displays(INJURY_CONTEXT)

    assert len(displays) == 300
    assert displays[152] == ("5-6", "red")
