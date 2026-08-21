from fantasy_football_2026.injury_context import RankedEntity
from fantasy_football_2026.market_context import build_market_players


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
