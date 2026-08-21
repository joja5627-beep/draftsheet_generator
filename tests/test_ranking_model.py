import json
from pathlib import Path

import pytest
from pypdf import PdfReader

from fantasy_football_2026.ranking_model import (
    ReweightedPlayer,
    _bounded_reorder,
    _load_highlighted_players,
    render_pdf,
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
    assert all(abs(player.rank_delta) <= player.movement_cap for player in reordered)


@requires_reweighted_context
def test_real_reweighted_output_has_complete_bounded_ranks() -> None:
    payload = json.loads(REWEIGHTED_CONTEXT.read_text(encoding="utf-8"))
    players = payload["players"]

    assert [player["final_rank"] for player in players] == list(range(1, 301))
    assert all(abs(player["rank_delta"]) <= player["movement_cap"] for player in players)
    assert all(player["source_coverage"]["baseline"] >= 2 for player in players)


@requires_source_audit
def test_source_audit_accounts_for_every_weighted_signal() -> None:
    model = json.loads(Path("context/ranking_model.json").read_text(encoding="utf-8"))
    audit = json.loads(SOURCE_AUDIT.read_text(encoding="utf-8"))

    assert set(model["weights"]) <= set(audit["modeled_signal_lineage"])
    assert "injury_and_role_risk" in audit["modeled_signal_lineage"]
    assert all(item["source_count"] >= 2 for item in audit["signal_sources"].values())


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


def test_reweighted_pdf_labels_each_new_round(tmp_path: Path) -> None:
    output = tmp_path / "round-labels.pdf"
    players = tuple(_player(rank=rank, score=50.0, cap=2) for rank in range(1, 38))

    render_pdf(
        output,
        players,
        generated_at="2026-08-21T00:00:00+00:00",
        teams=12,
        highlighted_players=frozenset(),
    )

    text = "\n".join(page.extract_text() or "" for page in PdfReader(output).pages)
    assert "R2" in text
    assert "R3" in text
    assert "R4" in text


def _player(*, rank: int, score: float, cap: int) -> ReweightedPlayer:
    return ReweightedPlayer(
        final_rank=rank,
        source_rank=rank,
        rank_delta=0,
        movement_cap=cap,
        name=f"Player {rank}",
        team="DET",
        position="RB",
        position_rank=f"RB{rank}",
        bye_week=6,
        adjusted_score=score,
        baseline_consensus_grade=50.0,
        league_vorp_proxy_grade=50.0,
        opportunity_grade=50.0,
        team_offense_grade=50.0,
        offensive_line_fit_grade=50.0,
        coaching_continuity_grade=50.0,
        custom_scoring_fit_grade=50.0,
        strength_of_schedule_grade=50.0,
        risk_penalty=0.0,
        consensus_rank=float(rank),
        depth_chart_label="RB1",
        offense_rank=1,
        offensive_line_rank=1,
        strength_of_schedule_rank=1,
        injury_weeks="0",
        injury_tier="CLEAR",
        source_coverage={},
        manual_signal_status="not-configured",
        rationale="test",
    )
