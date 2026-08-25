from pathlib import Path

from fantasy_football_2026.consensus.handcuffs import HandcuffConsensusBuilder


def _builder() -> HandcuffConsensusBuilder:
    return HandcuffConsensusBuilder(
        source_catalog_path=Path("unused"),
        market_path=Path("unused"),
        depth_path=Path("unused"),
        injury_path=Path("unused"),
        client=None,  # type: ignore[arg-type]
    )


def test_candidate_requires_current_rb2_role_and_two_publisher_families() -> None:
    candidate = _builder()._candidate(
        name="blake corum",
        families={"fantasypros", "pff"},
        market={
            "name": "Blake Corum",
            "team": "LAR",
            "position": "RB",
            "consensus_rank": 118.0,
            "fftoday_adp": 132.0,
        },
        depth={"depth_chart_order": 2, "pdf_label": "RB2", "offense_rank": 7},
        injury={"pdf_weeks_label": "0"},
        starter=("Kyren Williams", {}),
        injury_by_name={"kyren williams": {"pdf_weeks_label": "0"}},
        minimum_families=2,
    )

    assert candidate is not None
    assert candidate.highlighted is True
    assert candidate.starter == "Kyren Williams"
    assert candidate.source_family_count == 2


def test_candidate_keeps_rb3_and_single_source_mentions_on_watchlist() -> None:
    candidate = _builder()._candidate(
        name="will shipley",
        families={"pff"},
        market={
            "name": "Will Shipley",
            "team": "PHI",
            "position": "RB",
            "consensus_rank": 190.0,
        },
        depth={"depth_chart_order": 3, "pdf_label": "RB3", "offense_rank": 4},
        injury={"pdf_weeks_label": "0"},
        starter=("Saquon Barkley", {}),
        injury_by_name={"saquon barkley": {"pdf_weeks_label": "0"}},
        minimum_families=2,
    )

    assert candidate is not None
    assert candidate.highlighted is False
    assert "third-in-depth-order" in candidate.flags
