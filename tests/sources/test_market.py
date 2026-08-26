import json

from fantasy_football_2026.sources.injuries import RankedEntity
from fantasy_football_2026.sources.market import (
    build_market_players,
    parse_fantasy_football_calculator,
    parse_lineupbeat,
    parse_pro_football_mania,
    parse_rotoballer,
)


def test_market_context_matches_explicit_player_nicknames() -> None:
    entities = (
        RankedEntity(
            rank=1,
            position_rank="TE1",
            position="TE",
            name="Chig Okonkwo",
            team="WAS",
            bye_week=7,
            entity_type="player",
        ),
        RankedEntity(
            rank=2,
            position_rank="RB1",
            position="RB",
            name="Kenny Gainwell",
            team="TB",
            bye_week=9,
            entity_type="player",
        ),
    )
    fftoday = [
        {
            "rank": 143,
            "name": "Chigoziem Okonkwo",
            "team": "WAS",
            "position": "TE",
            "position_rank": 16,
            "adp": 144.5,
        },
        {
            "rank": 112,
            "name": "Kenneth Gainwell",
            "team": "TB",
            "position": "RB",
            "position_rank": 40,
            "adp": 112.5,
        },
    ]
    fantasypros = [
        {
            "player_name": "Chig Okonkwo",
            "player_team_id": "WAS",
            "player_position_id": "TE",
            "rank_ecr": 150,
            "pos_rank": "TE19",
            "tier": 9,
        },
        {
            "player_name": "Kenny Gainwell",
            "player_team_id": "TB",
            "player_position_id": "RB",
            "rank_ecr": 106,
            "pos_rank": "RB39",
            "tier": 7,
        },
    ]

    players = build_market_players(entities, fftoday, fantasypros, {"total_experts": 103})

    assert players[0].fftoday_adp == 144.5
    assert players[0].source_count == 3
    assert players[1].fftoday_adp == 112.5
    assert players[1].source_count == 3


def test_market_context_matches_defense_by_team() -> None:
    entities = (RankedEntity(1, "DST1", "DST", "Lions D/ST", "DET", 6, "defense"),)
    fftoday = [
        {
            "rank": 170,
            "name": "Detroit Lions",
            "team": "DET",
            "position": "DEF",
            "position_rank": 1,
            "adp": 170.0,
        }
    ]
    fantasypros = [
        {
            "player_name": "Detroit Lions",
            "player_team_id": "DET",
            "player_position_id": "DST",
            "rank_ecr": 175,
            "pos_rank": "DST1",
            "tier": 10,
        }
    ]

    player = build_market_players(entities, fftoday, fantasypros, {"total_experts": 103})[0]

    assert player.source_count == 3
    assert player.fftoday_adp == 170.0


def test_market_context_uses_equal_mean_across_seven_available_sources() -> None:
    entities = (RankedEntity(10, "RB1", "RB", "Test Back", "DET", 6, "player"),)
    fftoday = [
        {
            "rank": 30,
            "name": "Test Back",
            "team": "DET",
            "position": "RB",
            "position_rank": 10,
            "adp": 30.0,
        }
    ]
    fantasypros = [
        {
            "player_name": "Test Back",
            "player_team_id": "DET",
            "player_position_id": "RB",
            "rank_ecr": 20,
            "pos_rank": "RB8",
            "tier": 2,
        }
    ]
    benchmark_sources = {
        source_name: [
            {
                "rank": rank,
                "name": "Test Back",
                "team": "DET",
                "position": "RB",
            }
        ]
        for source_name, rank in (
            ("rotoballer", 40),
            ("fantasy_football_calculator", 50),
            ("lineupbeat", 60),
            ("pro_football_mania", 70),
        )
    }

    player = build_market_players(
        entities,
        fftoday,
        fantasypros,
        {"total_experts": 100},
        benchmark_sources=benchmark_sources,
    )[0]

    assert player.source_count == 7
    assert player.consensus_rank == 40.0
    assert player.consensus_median == 40.0
    assert player.consensus_range == 60.0


def test_additional_half_ppr_source_parsers_enforce_complete_ranked_rows() -> None:
    rotoballer_html = (
        "<table>"
        + "".join(
            f"<tr><td>1</td><td>{rank}</td><td>Player {rank}</td><td>RB</td></tr>"
            for rank in range(1, 301)
        )
        + "</table>"
    )
    calculator_html = (
        "<table>"
        + "".join(
            f"<tr><td>{rank}.</td><td>Player {rank}</td><td>DET</td><td>RB</td></tr>"
            for rank in range(1, 101)
        )
        + "</table>"
    )
    lineupbeat_html = (
        '<script type="application/ld+json">'
        + json.dumps(
            {
                "@type": "ItemList",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": rank,
                        "name": f"Player {rank} (DET, RB)",
                    }
                    for rank in range(1, 191)
                ],
            }
        )
        + "</script>"
    )
    pfm_html = (
        "<table>"
        + "".join(
            f'<tr data-pfm-player-name="Player {rank}" '
            f'data-pfm-ranks="{{&quot;overall&quot;:{rank}}}">'
            '<button data-position="RB" data-team-abbr="DET"></button></tr>'
            for rank in range(1, 251)
        )
        + "</table>"
    )

    assert len(parse_rotoballer(rotoballer_html)) == 300
    assert len(parse_fantasy_football_calculator(calculator_html)) == 100
    assert len(parse_lineupbeat(lineupbeat_html)) == 190
    assert len(parse_pro_football_mania(pfm_html)) == 250
