import json
from dataclasses import replace
from pathlib import Path

import pytest

from fantasy_football_2026.domain.rankings import (
    ReweightedPlayer,
    _annotate_round_value_picks,
    _apply_major_injury_displacement_allowance,
    _apply_same_team_depth_chart_tiebreaker,
    _bounded_reorder,
    _build_consensus_anomaly_audit,
    _injury_adjustment,
    _load_handcuff_players,
    _load_highlighted_players,
    _movement_is_allowed,
    _refresh_position_ranks,
)

REWEIGHTED_CONTEXT = Path("context/reweighted_cheat_sheet.json")
SOURCE_AUDIT = Path("context/source_audit.json")
requires_reweighted_context = pytest.mark.skipif(
    not REWEIGHTED_CONTEXT.is_file(),
    reason="requires generated reweighted rankings",
)
requires_source_audit = pytest.mark.skipif(
    not SOURCE_AUDIT.is_file(),
    reason="requires generated source audit",
)


def test_bounded_reorder_requires_score_gap_and_respects_caps() -> None:
    players = [
        _player(rank=1, score=50.0, cap=1),
        _player(rank=2, score=55.0, cap=1),
        _player(rank=3, score=60.0, cap=1),
    ]

    reordered = _bounded_reorder(players, threshold=2.0)

    assert [player.source_rank for player in reordered] == [2, 1, 3]
    assert all(_movement_is_allowed(player, player.final_rank) for player in reordered)


def test_movement_cap_uses_consensus_anchor_instead_of_espn_source_rank() -> None:
    player = _player(rank=10, score=50.0, cap=2, source_rank=80)

    assert _movement_is_allowed(player, 8)
    assert _movement_is_allowed(player, 12)
    assert not _movement_is_allowed(player, 7)
    assert not _movement_is_allowed(player, 13)


def test_corroborated_injury_reduces_availability_and_expands_only_downside() -> None:
    model = {
        "risk_penalty_cap": 8.0,
        "injury_adjustment": {
            "availability_penalty_per_game": 0.65,
            "downside_cap_bonus_per_game": 4.0,
            "maximum_downside_cap_bonus": 24,
            "unbounded_downside_minimum_games": 5.0,
            "unbounded_downside_cap_bonus": 300,
        },
    }
    injury = {
        "tier": "HIGH",
        "confidence": "medium",
        "projected_games_max": 6,
        "projected_games_estimate": 5.5,
        "source_agreement": "corroborated",
        "signal_source_count": 2,
    }

    adjustment = _injury_adjustment(injury, model=model)
    player = _player(
        rank=100,
        score=50.0,
        cap=8,
        injury_movement_bonus=adjustment.movement_bonus,
    )

    assert adjustment.availability_factor == pytest.approx(0.725, abs=0.001)
    assert adjustment.penalty == pytest.approx(6.44, abs=0.01)
    assert adjustment.movement_bonus == 300
    assert _movement_is_allowed(player, 300)
    assert not _movement_is_allowed(player, 91)


def test_single_source_injury_never_expands_movement_cap() -> None:
    model = {
        "risk_penalty_cap": 8.0,
        "injury_adjustment": {
            "availability_penalty_per_game": 0.65,
            "downside_cap_bonus_per_game": 4.0,
            "maximum_downside_cap_bonus": 24,
            "unbounded_downside_minimum_games": 5.0,
            "unbounded_downside_cap_bonus": 300,
        },
    }
    injury = {
        "tier": "HIGH",
        "confidence": "low",
        "projected_games_max": 6,
        "projected_games_estimate": 5.5,
        "source_agreement": "single-source",
        "signal_source_count": 1,
    }

    assert _injury_adjustment(injury, model=model).movement_bonus == 0


def test_major_absence_creates_passive_promotion_allowance_below_vacancy() -> None:
    injured = _player(
        rank=2,
        score=10.0,
        cap=1,
        name="Major Absence",
        injury_movement_bonus=300,
    )
    above = _player(rank=1, score=50.0, cap=1, name="Above")
    below = _player(rank=3, score=50.0, cap=1, name="Below")

    adjusted = _apply_major_injury_displacement_allowance((above, injured, below))

    assert adjusted[0].injury_displacement_bonus == 0
    assert adjusted[1].injury_displacement_bonus == 0
    assert adjusted[2].injury_displacement_bonus == 1
    assert _movement_is_allowed(adjusted[2], 1)


def test_major_absence_demotes_on_any_real_score_disadvantage() -> None:
    players = _apply_major_injury_displacement_allowance(
        (
            _player(
                rank=1,
                score=50.0,
                cap=1,
                name="Major Absence",
                injury_movement_bonus=300,
            ),
            _player(rank=2, score=50.5, cap=1, name="Small Edge"),
            _player(rank=3, score=55.0, cap=1, name="Large Edge"),
        )
    )

    reordered = _bounded_reorder(list(players), threshold=2.0)

    assert [player.name for player in reordered] == ["Large Edge", "Small Edge", "Major Absence"]


def test_same_team_depth_chart_tiebreaker_promotes_higher_scoring_starter() -> None:
    players = (
        _player(
            rank=1,
            score=50.0,
            cap=3,
            name="Backup",
            team="CAR",
            depth_chart_label="RB2",
        ),
        _player(rank=2, score=60.0, cap=3, name="Unrelated", team="BUF"),
        _player(
            rank=3,
            score=50.5,
            cap=3,
            name="Starter",
            team="CAR",
            depth_chart_label="RB1",
        ),
    )

    reordered, corrections = _apply_same_team_depth_chart_tiebreaker(
        players,
        positions=frozenset({"QB", "RB", "TE"}),
        minimum_score_advantage=0.0,
    )

    assert [player.name for player in reordered] == ["Starter", "Unrelated", "Backup"]
    assert corrections[0].promoted_player == "Starter"
    assert corrections[0].demoted_player == "Backup"
    assert all(_movement_is_allowed(player, player.final_rank) for player in reordered)


def test_same_team_depth_chart_tiebreaker_promotes_starter_on_tied_score() -> None:
    players = (
        _player(
            rank=1,
            score=50.0,
            cap=2,
            name="Backup",
            team="CAR",
            depth_chart_label="RB2",
        ),
        _player(
            rank=2,
            score=50.0,
            cap=2,
            name="Starter",
            team="CAR",
            depth_chart_label="RB1",
        ),
    )

    reordered, corrections = _apply_same_team_depth_chart_tiebreaker(
        players,
        positions=frozenset({"QB", "RB", "TE"}),
        minimum_score_advantage=0.0,
    )

    assert [player.name for player in reordered] == ["Starter", "Backup"]
    assert corrections[0].score_advantage == 0.0


def test_same_team_depth_chart_tiebreaker_requires_better_score_and_role() -> None:
    players = (
        _player(
            rank=1,
            score=55.0,
            cap=2,
            name="Valuable Backup",
            team="BUF",
            depth_chart_label="RB2",
        ),
        _player(
            rank=2,
            score=50.0,
            cap=2,
            name="Starter",
            team="BUF",
            depth_chart_label="RB1",
        ),
    )

    reordered, corrections = _apply_same_team_depth_chart_tiebreaker(
        players,
        positions=frozenset({"QB", "RB", "TE"}),
        minimum_score_advantage=0.0,
    )

    assert [player.name for player in reordered] == ["Valuable Backup", "Starter"]
    assert corrections == ()


def test_position_ranks_are_recalculated_from_final_overall_order() -> None:
    players = (
        _player(rank=1, score=60.0, cap=2, position="WR", name="First Receiver"),
        _player(rank=2, score=55.0, cap=2, position="RB", name="First Back"),
        _player(rank=3, score=50.0, cap=2, position="WR", name="Second Receiver"),
    )

    refreshed = _refresh_position_ranks(players)

    assert [player.position_rank for player in refreshed] == ["WR1", "RB1", "WR2"]


def test_consensus_anomaly_guardrail_allows_only_supported_injury_exception() -> None:
    policy = {
        "consensus_anomaly_guardrail": {
            "minimum_sources": 5,
            "rank_band_tolerances": [{"minimum_rank": 1, "maximum_rank": 300, "spots": 20}],
        },
        "same_team_depth_chart_tiebreaker": {
            "positions": ["QB", "RB", "TE"],
            "minimum_score_advantage": 0.0,
        },
    }
    market = [
        {
            "source_rank": 100,
            "source_count": 5,
            "consensus_median": 100.0,
            "consensus_rank": 102.0,
            "consensus_range": 30.0,
        }
    ]
    unexplained = replace(
        _player(rank=100, score=50.0, cap=8, source_rank=100),
        final_rank=140,
    )
    injured = replace(unexplained, injury_movement_bonus=50)

    failed = _build_consensus_anomaly_audit(
        players=(unexplained,), market_players=market, model=policy
    )
    passed = _build_consensus_anomaly_audit(players=(injured,), market_players=market, model=policy)

    assert failed["status"] == "FAIL"
    assert failed["unresolved_count"] == 1
    assert passed["status"] == "PASS"
    assert passed["explained_count"] == 1


@requires_reweighted_context
def test_real_reweighted_output_has_complete_bounded_ranks() -> None:
    payload = json.loads(REWEIGHTED_CONTEXT.read_text(encoding="utf-8"))
    players = payload["players"]

    assert [player["final_rank"] for player in players] == list(range(1, 301))
    assert all(
        (
            player["rank_delta"] <= player["movement_cap"] + player["injury_displacement_bonus"]
            if player["rank_delta"] >= 0
            else abs(player["rank_delta"])
            <= player["movement_cap"] + player["injury_movement_bonus"]
        )
        for player in players
    )
    assert all(player["source_coverage"]["baseline"] >= 2 for player in players)
    value_picks = [player for player in players if player["round_value_pick"]]
    assert {player["draft_round"] for player in value_picks} == set(range(1, 26))
    assert len(value_picks) == 25
    assert all(player["position"] not in {"K", "DST"} for player in value_picks)
    assert all(player["unconstrained_value_delta"] >= 1 for player in value_picks)


@requires_source_audit
def test_source_audit_accounts_for_every_weighted_signal() -> None:
    model = json.loads(Path("context/ranking_model.json").read_text(encoding="utf-8"))
    audit = json.loads(SOURCE_AUDIT.read_text(encoding="utf-8"))

    assert set(model["weights"]) <= set(audit["modeled_signal_lineage"])
    assert "injury_and_role_risk" in audit["modeled_signal_lineage"]
    assert all(item["source_count"] >= 2 for item in audit["signal_sources"].values())
    assert audit["ranking_anomalies"]["unresolved_count"] == 0


def test_pdf_highlights_are_driven_by_sleeper_and_rookie_context(tmp_path: Path) -> None:
    context_path = tmp_path / "sleepers.json"
    context_path.write_text(
        json.dumps(
            {
                "sleepers": [{"player": "Chig Okonkwo"}],
                "rookie_breakout_candidates": [
                    {"player": "Denzel Boston"},
                    {"player": "Chig Okonkwo"},
                ],
            }
        ),
        encoding="utf-8",
    )

    assert _load_highlighted_players(context_path) == {
        "chig okonkwo",
        "denzel boston",
    }


def test_pdf_handcuffs_only_include_eligible_generated_candidates(tmp_path: Path) -> None:
    context_path = tmp_path / "handcuffs.json"
    context_path.write_text(
        json.dumps(
            {
                "candidates": [
                    {"player": "Blake Corum", "highlighted": True},
                    {"player": "Will Shipley", "highlighted": False},
                ]
            }
        ),
        encoding="utf-8",
    )

    assert _load_handcuff_players(context_path) == {"blake corum"}


def test_round_value_picks_select_one_model_discount_per_round() -> None:
    players = (
        _player(rank=1, score=100.0, cap=2, name="Round One Favorite"),
        _player(rank=2, score=80.0, cap=2, name="Round One Alternative"),
        _player(rank=3, score=95.0, cap=2, name="Round Two Value"),
        _player(rank=4, score=70.0, cap=2, name="Round Two Kicker", position="K"),
    )

    annotated = _annotate_round_value_picks(
        players,
        teams=2,
        picks_per_round=1,
        minimum_value_delta=1,
        excluded_positions=frozenset({"K", "DST"}),
    )

    picks = [player for player in annotated if player.round_value_pick]
    assert [(player.draft_round, player.name) for player in picks] == [(2, "Round Two Value")]
    assert picks[0].score_supported_rank == 2
    assert picks[0].unconstrained_value_delta == 1


def _player(
    *,
    rank: int,
    score: float,
    cap: int,
    name: str | None = None,
    team: str = "DET",
    depth_chart_label: str = "RB1",
    source_rank: int | None = None,
    injury_movement_bonus: int = 0,
    injury_displacement_bonus: int = 0,
    position: str = "RB",
) -> ReweightedPlayer:
    return ReweightedPlayer(
        final_rank=rank,
        source_rank=source_rank or rank,
        movement_anchor_rank=rank,
        rank_delta=0,
        source_rank_delta=(source_rank or rank) - rank,
        movement_cap=cap,
        injury_movement_bonus=injury_movement_bonus,
        injury_displacement_bonus=injury_displacement_bonus,
        score_supported_rank=rank,
        unconstrained_value_delta=0,
        draft_round=((rank - 1) // 12) + 1,
        round_value_pick=False,
        name=name or f"Player {rank}",
        team=team,
        position=position,
        position_rank=f"{position}{rank}",
        bye_week=6,
        adjusted_score=score,
        baseline_consensus_grade=50.0,
        custom_projected_value_grade=50.0,
        availability_adjusted_projected_value_grade=50.0,
        availability_factor=1.0,
        custom_projected_points=200.0,
        projection_baseline_points=150.0,
        projected_value_over_baseline=50.0,
        opportunity_grade=50.0,
        team_offense_grade=50.0,
        offensive_line_fit_grade=50.0,
        strength_of_schedule_grade=50.0,
        risk_penalty=0.0,
        consensus_rank=float(rank),
        depth_chart_label=depth_chart_label,
        offense_rank=1,
        offensive_line_rank=1,
        strength_of_schedule_rank=1,
        injury_weeks="0",
        injury_tier="CLEAR",
        source_coverage={},
    )
