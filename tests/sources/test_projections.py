from pathlib import Path

from fantasy_football_2026.sources.projections import ProjectionContextBuilder


def _builder(*, teams: int = 12) -> ProjectionContextBuilder:
    return ProjectionContextBuilder(
        scoring_path=Path("unused"),
        market_path=Path("unused"),
        model_path=Path("unused"),
        cache_dir=Path("unused"),
        refresh=False,
        offline=True,
        timeout=1.0,
        teams=teams,
    )


def test_supplied_league_scoring_is_parsed_without_manual_duplication() -> None:
    scoring = ProjectionContextBuilder._parse_scoring(Path("context/broncon24_league_scoring.txt"))

    assert scoring == {
        "pass_yds": 0.05,
        "pass_td": 4.0,
        "pass_int": -2.0,
        "rush_yds": 0.1,
        "rush_td": 5.0,
        "reception": 0.5,
        "rec_yds": 0.1,
        "rec_td": 5.0,
        "fumble_lost": -2.0,
    }


def test_custom_projection_points_apply_league_rules() -> None:
    scoring = ProjectionContextBuilder._parse_scoring(Path("context/broncon24_league_scoring.txt"))
    points = ProjectionContextBuilder._custom_points(
        {
            "pass_yds": 4000.0,
            "pass_td": 30.0,
            "pass_int": 10.0,
            "rush_yds": 400.0,
            "rush_td": 4.0,
            "fumbles_lost": 2.0,
        },
        scoring,
    )

    assert points == 356.0


def test_fftoday_qb_row_maps_raw_stats_by_column() -> None:
    html = """
    <table><tr>
      <td>&nbsp;</td>
      <td><a href="/stats/players/1/Test_Player?LeagueID=1">Test Player</a></td>
      <td>DEN</td><td>8</td><td>300</td><td>450</td><td>3,900</td>
      <td>28</td><td>9</td><td>80</td><td>400</td><td>4</td><td>330.0</td>
    </tr></table>
    """

    parsed = ProjectionContextBuilder._parse_fftoday_position("QB", html)

    assert parsed["test player"]["team"] == "DEN"
    assert parsed["test player"]["stats"] == {
        "pass_cmp": 300.0,
        "pass_att": 450.0,
        "pass_yds": 3900.0,
        "pass_td": 28.0,
        "pass_int": 9.0,
        "rush_att": 80.0,
        "rush_yds": 400.0,
        "rush_td": 4.0,
    }


def test_projection_sources_are_averaged_at_raw_stat_level() -> None:
    scoring = ProjectionContextBuilder._parse_scoring(Path("context/broncon24_league_scoring.txt"))
    first = {
        "test player": {
            "name": "Test Player",
            "team": "DEN",
            "position": "RB",
            "stats": {"rush_yds": 1_000.0, "rush_td": 10.0, "receptions": 40.0},
        }
    }
    second = {
        "test player": {
            "name": "Test Player",
            "team": "DEN",
            "position": "RB",
            "stats": {"rush_yds": 800.0, "rush_td": 8.0, "receptions": 60.0},
        }
    }

    aggregate = ProjectionContextBuilder._aggregate_sources(
        {"first": first, "second": second}, scoring
    )["test player"]

    assert aggregate["stats"] == {
        "rush_yds": 900.0,
        "rush_td": 9.0,
        "receptions": 50.0,
    }
    assert aggregate["points"] == 160.0
    assert aggregate["source_count"] == 2


def test_rb_wr_replacement_baselines_follow_dedicated_and_flex_demand() -> None:
    projections = {}
    for position in ("RB", "WR"):
        for rank in range(1, 41):
            projections[f"{position.lower()} {rank}"] = {
                "position": position,
                "points": 301.0 - rank,
            }
    for rank in range(1, 21):
        projections[f"te {rank}"] = {"position": "TE", "points": 201.0 - rank}
    for rank in range(1, 21):
        projections[f"qb {rank}"] = {"position": "QB", "points": 401.0 - rank}
    model = {
        "league_structure": {
            "starting_slots": {"QB": 1, "RB": 2, "WR": 2, "TE": 1},
            "flex_slots": 1,
            "flex_positions": ["RB", "WR", "TE"],
            "onesie_baseline_fraction": 0.5,
        }
    }

    baselines = _builder()._derive_baselines(projections, model)

    assert baselines["QB"] == 395.0
    assert baselines["TE"] == 195.0
    assert baselines["RB"] == 270.0
    assert baselines["WR"] == 270.0
