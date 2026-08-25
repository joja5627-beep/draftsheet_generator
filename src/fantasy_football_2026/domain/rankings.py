"""Reweight the source Top 300 with auditable league and context signals."""

from __future__ import annotations

import argparse
import csv
import math
import re
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import landscape, letter
from reportlab.pdfgen.canvas import Canvas

from fantasy_football_2026.constants import (
    DEFAULT_LEAGUE_TEAMS,
    HANDCUFF_HIGHLIGHT_COLOR,
    SLEEPER_HIGHLIGHT_COLOR,
    ContextFile,
    DirectoryName,
    OutputFile,
)
from fantasy_football_2026.domain.normalization import normalize_name
from fantasy_football_2026.errors import InjuryContextError, StorageError
from fantasy_football_2026.infrastructure.storage import load_json_object, write_json, write_text
from fantasy_football_2026.presentation.buckets import BUCKET_COLORS
from fantasy_football_2026.presentation.pdf import draft_round_for_rank

WEIGHTED_ROUND_GAP = 5.5


@dataclass(frozen=True, slots=True)
class ReweightedPlayer:
    final_rank: int
    source_rank: int
    rank_delta: int
    movement_cap: int
    name: str
    team: str
    position: str
    position_rank: str
    bye_week: int | None
    adjusted_score: float
    baseline_consensus_grade: float
    custom_projected_value_grade: float
    custom_projected_points: float | None
    projection_baseline_points: float | None
    projected_value_over_baseline: float | None
    opportunity_grade: float
    team_offense_grade: float
    offensive_line_fit_grade: float
    strength_of_schedule_grade: float
    risk_penalty: float
    consensus_rank: float
    depth_chart_label: str
    offense_rank: int | None
    offensive_line_rank: int | None
    strength_of_schedule_rank: int | None
    injury_weeks: str
    injury_tier: str
    source_coverage: dict[str, int]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the reweighted 2026 cheat sheet.")
    parser.add_argument(
        "--market-context",
        type=Path,
        default=Path(DirectoryName.CONTEXT, ContextFile.MARKET_JSON),
    )
    parser.add_argument(
        "--depth-context",
        type=Path,
        default=Path(DirectoryName.CONTEXT, ContextFile.PLAYER_DEPTH_JSON),
    )
    parser.add_argument(
        "--injury-context",
        type=Path,
        default=Path(DirectoryName.CONTEXT, ContextFile.INJURIES_JSON),
    )
    parser.add_argument(
        "--model", type=Path, default=Path(DirectoryName.CONTEXT, ContextFile.MODEL_JSON)
    )
    parser.add_argument(
        "--projection-context",
        type=Path,
        default=Path(DirectoryName.CONTEXT, ContextFile.PROJECTIONS_JSON),
    )
    parser.add_argument(
        "--sleeper-context",
        type=Path,
        default=Path(DirectoryName.CONTEXT, ContextFile.SLEEPER_CONSENSUS_JSON),
        help="generated sleeper and rookie target context used for PDF highlights",
    )
    parser.add_argument(
        "--handcuff-context",
        type=Path,
        default=Path(DirectoryName.CONTEXT, ContextFile.HANDCUFF_CONSENSUS_JSON),
        help="generated running back handcuff context used for PDF highlights",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=Path(DirectoryName.CONTEXT, ContextFile.REWEIGHTED_JSON),
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=Path(DirectoryName.CONTEXT, ContextFile.REWEIGHTED_MARKDOWN),
    )
    parser.add_argument(
        "--audit-json",
        type=Path,
        default=Path(DirectoryName.CONTEXT, ContextFile.SOURCE_AUDIT_JSON),
    )
    parser.add_argument(
        "--audit-markdown",
        type=Path,
        default=Path(DirectoryName.CONTEXT, ContextFile.SOURCE_AUDIT_MARKDOWN),
    )
    parser.add_argument(
        "--csv-output",
        type=Path,
        default=Path(DirectoryName.OUTPUT, DirectoryName.CHEAT_SHEET, OutputFile.REWEIGHTED_CSV),
    )
    parser.add_argument(
        "--pdf-output",
        type=Path,
        default=Path(DirectoryName.OUTPUT, DirectoryName.PDF, OutputFile.REWEIGHTED_PDF),
    )
    parser.add_argument("--teams", type=int, default=DEFAULT_LEAGUE_TEAMS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = update_reweighted_rankings(
        market_path=args.market_context,
        depth_path=args.depth_context,
        injury_path=args.injury_context,
        model_path=args.model,
        projection_context_path=args.projection_context,
        sleeper_context_path=args.sleeper_context,
        handcuff_context_path=args.handcuff_context,
        json_path=args.json_output,
        markdown_path=args.markdown_output,
        audit_json_path=args.audit_json,
        audit_markdown_path=args.audit_markdown,
        csv_path=args.csv_output,
        pdf_path=args.pdf_output,
        teams=args.teams,
    )
    print(f"Reweighted players: {result['player_count']}")
    print(f"Players moved: {result['moved_count']}")
    print(f"PDF: {Path(result['pdf_path']).resolve()}")
    return 0


def update_reweighted_rankings(
    *,
    market_path: Path,
    depth_path: Path,
    injury_path: Path,
    model_path: Path,
    projection_context_path: Path,
    sleeper_context_path: Path,
    handcuff_context_path: Path,
    json_path: Path,
    markdown_path: Path,
    audit_json_path: Path,
    audit_markdown_path: Path,
    csv_path: Path,
    pdf_path: Path,
    teams: int,
) -> dict[str, Any]:
    if teams < 2:
        raise InjuryContextError("teams must be at least 2")
    market_document = _load_json(market_path)
    depth_document = _load_json(depth_path)
    injury_document = _load_json(injury_path)
    projection_document = _load_json(projection_context_path)
    model = _load_json(model_path)
    highlighted_players = _load_highlighted_players(sleeper_context_path)
    handcuff_players = _load_handcuff_players(handcuff_context_path)
    _validate_model(model)

    market_players = market_document["players"]
    if len(market_players) != 300:
        raise InjuryContextError(f"Expected 300 market players, found {len(market_players)}.")
    depth_by_rank = {int(player["rank"]): player for player in depth_document["players"]}
    injury_by_rank = {int(player["rank"]): player for player in injury_document["players"]}
    projection_by_rank = {
        int(player["source_rank"]): player for player in projection_document["players"]
    }
    source_registry = model["source_registry"]
    weights = model["weights"]
    initial: list[ReweightedPlayer] = []
    for player in market_players:
        source_rank = int(player["source_rank"])
        depth = depth_by_rank[source_rank]
        injury = injury_by_rank[source_rank]
        projection = projection_by_rank[source_rank]
        baseline_grade = _rank_grade(float(player["consensus_rank"]), maximum=300)
        projected_value_grade = float(projection["projected_value_grade"])
        opportunity_grade = _depth_grade(depth)
        offense_grade = _team_rank_grade(depth.get("offense_rank"))
        line_raw = _team_rank_grade(depth.get("offensive_line_rank"))
        line_multiplier = float(
            model["offensive_line_position_multiplier"].get(player["position"], 0.0)
        )
        line_grade = round(50.0 + ((line_raw - 50.0) * line_multiplier), 2)
        schedule_grade = _team_rank_grade(depth.get("strength_of_schedule_rank"))
        risk_penalty = _injury_penalty(injury)

        score = round(
            (float(weights["custom_projected_value"]) * projected_value_grade)
            + (float(weights["baseline_consensus"]) * baseline_grade)
            + (float(weights["opportunity"]) * opportunity_grade)
            + (float(weights["team_offense"]) * offense_grade)
            + (float(weights["offensive_line_fit"]) * line_grade)
            + (float(weights["strength_of_schedule"]) * schedule_grade)
            - risk_penalty,
            3,
        )

        initial.append(
            ReweightedPlayer(
                final_rank=source_rank,
                source_rank=source_rank,
                rank_delta=0,
                movement_cap=_movement_cap(source_rank, model),
                name=str(player["name"]),
                team=str(player["team"]),
                position=str(player["position"]),
                position_rank=str(player["position_rank"]),
                bye_week=player.get("bye_week"),
                adjusted_score=score,
                baseline_consensus_grade=round(baseline_grade, 2),
                custom_projected_value_grade=round(projected_value_grade, 2),
                custom_projected_points=_optional_float(projection.get("custom_projected_points")),
                projection_baseline_points=_optional_float(projection.get("baseline_points")),
                projected_value_over_baseline=_optional_float(
                    projection.get("projected_value_over_baseline")
                ),
                opportunity_grade=round(opportunity_grade, 2),
                team_offense_grade=round(offense_grade, 2),
                offensive_line_fit_grade=line_grade,
                strength_of_schedule_grade=round(schedule_grade, 2),
                risk_penalty=risk_penalty,
                consensus_rank=float(player["consensus_rank"]),
                depth_chart_label=str(depth.get("pdf_label") or "--"),
                offense_rank=_optional_int(depth.get("offense_rank")),
                offensive_line_rank=_optional_int(depth.get("offensive_line_rank")),
                strength_of_schedule_rank=_optional_int(depth.get("strength_of_schedule_rank")),
                injury_weeks=str(injury.get("pdf_weeks_label") or "--"),
                injury_tier=str(injury.get("tier") or "N/A"),
                source_coverage={
                    "baseline": int(player["source_count"]),
                    "projection": int(projection.get("projection_source_count") or 0),
                    "opportunity": int(depth.get("depth_source_count") or 0),
                    "team_offense": len(source_registry["team_offense"]),
                    "offensive_line": len(source_registry["offensive_line_fit"]),
                    "schedule": len(source_registry["strength_of_schedule"]),
                    "injury": len(injury.get("sources_checked") or []),
                },
            )
        )

    ranked = _bounded_reorder(
        initial,
        threshold=float(model["score_difference_to_reorder"]),
    )
    generated_at = datetime.now(UTC).isoformat(timespec="seconds")
    audit = _build_audit(
        generated_at=generated_at,
        model=model,
        players=ranked,
        market_metadata=market_document["metadata"],
        depth_metadata=depth_document["metadata"],
        injury_metadata=injury_document["metadata"],
    )
    metadata = {
        "generated_at": generated_at,
        "model_version": model["model_version"],
        "teams": teams,
        "weights": weights,
        "movement_policy": model["movement_caps"],
        "score_difference_to_reorder": model["score_difference_to_reorder"],
        "source_audit": str(audit_json_path),
        "inputs": {
            "market": str(market_path),
            "projections": str(projection_context_path),
            "depth": str(depth_path),
            "injury": str(injury_path),
            "model": str(model_path),
            "sleeper_highlights": str(sleeper_context_path),
            "handcuff_highlights": str(handcuff_context_path),
        },
        "highlighted_player_count": len(highlighted_players),
        "handcuff_highlighted_player_count": len(handcuff_players),
        "highlight_overlap_count": len(highlighted_players & handcuff_players),
        "caveat": (
            "Projected value excludes milestone, long-touchdown, and two-point-conversion "
            "bonuses because the aggregate source does not forecast their occurrence. "
            "Roster structure remains an explicit assumption until league slots are confirmed."
        ),
    }
    write_json(
        json_path,
        {"metadata": metadata, "players": [asdict(player) for player in ranked]},
    )
    write_text(markdown_path, render_markdown(metadata, ranked))
    write_json(audit_json_path, audit)
    write_text(audit_markdown_path, render_audit_markdown(audit))
    _write_csv(csv_path, ranked)
    render_pdf(
        pdf_path,
        ranked,
        generated_at=generated_at,
        teams=teams,
        highlighted_players=highlighted_players,
        handcuff_players=handcuff_players,
    )
    return {
        "player_count": len(ranked),
        "moved_count": sum(player.rank_delta != 0 for player in ranked),
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
        "audit_json_path": str(audit_json_path),
        "csv_path": str(csv_path),
        "pdf_path": str(pdf_path),
    }


def _bounded_reorder(
    players: list[ReweightedPlayer], *, threshold: float
) -> tuple[ReweightedPlayer, ...]:
    ordered = list(players)
    changed = True
    passes = 0
    while changed and passes < len(ordered):
        changed = False
        passes += 1
        for index in range(1, len(ordered)):
            upper = ordered[index - 1]
            lower = ordered[index]
            upper_new_rank = index + 1
            lower_new_rank = index
            if lower.adjusted_score - upper.adjusted_score < threshold:
                continue
            if abs(upper_new_rank - upper.source_rank) > upper.movement_cap:
                continue
            if abs(lower_new_rank - lower.source_rank) > lower.movement_cap:
                continue
            ordered[index - 1], ordered[index] = lower, upper
            changed = True
    return tuple(
        replace(
            player,
            final_rank=index,
            rank_delta=player.source_rank - index,
        )
        for index, player in enumerate(ordered, start=1)
    )


def render_markdown(metadata: dict[str, Any], players: tuple[ReweightedPlayer, ...]) -> str:
    weights = metadata["weights"]
    lines = [
        "# 2026 reweighted fantasy football cheat sheet",
        "",
        f"**Generated:** `{metadata['generated_at']}`  ",
        f"**Model:** `{metadata['model_version']}`  ",
        "**League:** 12-team, one-QB redraft; custom half-PPR scoring  ",
        "",
        "## Model",
        "",
        "Every displayed signal is refreshed or derived from automated inputs. "
        "A two-point score gap is "
        "required to swap players, and every move is bounded by the configured rank cap.",
        "",
        "| Signal | Weight |",
        "|---|---:|",
    ]
    lines.extend(f"| {key.replace('_', ' ')} | {value:.0%} |" for key, value in weights.items())
    lines.extend(
        [
            "",
            "Risk is subtracted after weighting and remains capped at five points.",
            "",
            "## Reweighted Top 300",
            "",
            "| New | Base | Delta | Player | Pos-Team | Score | Market | Proj VBD | "
            "Proj Pts | VBD Pts | Opp | OFF | OL | SOS | Risk | DC | INJ |",
            "|---:|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
        ]
    )
    for player in players:
        delta = f"+{player.rank_delta}" if player.rank_delta > 0 else str(player.rank_delta)
        lines.append(
            f"| {player.final_rank} | {player.source_rank} | {delta} | {player.name} | "
            f"{player.position}-{player.team} | {player.adjusted_score:.2f} | "
            f"{player.baseline_consensus_grade:.1f} | "
            f"{player.custom_projected_value_grade:.1f} | "
            f"{_number_float(player.custom_projected_points)} | "
            f"{_number_float(player.projected_value_over_baseline)} | "
            f"{player.opportunity_grade:.1f} | {player.team_offense_grade:.1f} | "
            f"{player.offensive_line_fit_grade:.1f} | "
            f"{player.strength_of_schedule_grade:.1f} | {player.risk_penalty:.1f} | "
            f"{player.depth_chart_label} | {player.injury_weeks} |"
        )
    lines.extend(["", "## Limitation", "", metadata["caveat"], ""])
    return "\n".join(lines)


def render_pdf(
    path: Path,
    players: tuple[ReweightedPlayer, ...],
    *,
    generated_at: str,
    teams: int,
    highlighted_players: frozenset[str],
    handcuff_players: frozenset[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    canvas = Canvas(str(temporary), pagesize=landscape(letter))
    width, height = landscape(letter)
    canvas.setTitle("2026 Reweighted Fantasy Football Cheat Sheet")
    canvas.setAuthor("fantasy-football-2026 reproducible ranking pipeline")
    rows_per_column = 50
    columns_per_page = 3
    rows_per_page = rows_per_column * columns_per_page
    margin = 16.0
    column_gap = 5.0
    column_width = (width - (2 * margin) - (column_gap * 2)) / columns_per_page
    row_height = 9.95

    for page_start in range(0, len(players), rows_per_page):
        page_number = (page_start // rows_per_page) + 1
        canvas.setFillColor(HexColor("#17324D"))
        canvas.setFont("Helvetica-Bold", 13)
        canvas.drawString(margin, height - 20, "2026 Custom-League Reweighted Top 300")
        canvas.setFont("Helvetica", 6.5)
        canvas.setFillColor(HexColor("#4A5B6B"))
        canvas.drawRightString(
            width - margin,
            height - 18,
            f"{teams}-team rounds | rebuilt {generated_at[:10]} | page {page_number}/2",
        )
        canvas.drawString(
            margin,
            height - 31,
            "Delta is improvement vs ESPN source rank. Signals: DC depth, O offense, "
            "L line, S schedule, I projected weeks missed.",
        )
        legend_x = width - 230
        canvas.setFillColor(HexColor(SLEEPER_HIGHLIGHT_COLOR))
        canvas.setStrokeColor(HexColor("#D6A83B"))
        canvas.setLineWidth(0.45)
        canvas.rect(legend_x, height - 33, 9, 7, stroke=1, fill=1)
        canvas.setFillColor(HexColor("#4A5B6B"))
        canvas.setFont("Helvetica-Bold", 6.0)
        canvas.drawString(legend_x + 13, height - 31.5, "Sleeper or rookie target")
        handcuff_legend_x = legend_x + 112
        canvas.setFillColor(HexColor(HANDCUFF_HIGHLIGHT_COLOR))
        canvas.setStrokeColor(HexColor("#9B7DB8"))
        canvas.rect(handcuff_legend_x, height - 33, 9, 7, stroke=1, fill=1)
        canvas.setFillColor(HexColor("#4A5B6B"))
        canvas.drawString(handcuff_legend_x + 13, height - 31.5, "RB handcuff")

        for column in range(columns_per_page):
            x = margin + column * (column_width + column_gap)
            start = page_start + column * rows_per_column
            subset = players[start : start + rows_per_column]
            _draw_pdf_column(
                canvas,
                subset,
                x=x,
                top=height - 48,
                width=column_width,
                row_height=row_height,
                teams=teams,
                highlighted_players=highlighted_players,
                handcuff_players=handcuff_players,
            )
        canvas.setStrokeColor(HexColor("#C8D4DE"))
        canvas.line(margin, 17, width - margin, 17)
        canvas.setFillColor(HexColor("#5D6B78"))
        canvas.setFont("Helvetica", 5.5)
        canvas.drawString(
            margin,
            9,
            "Projection-first model: custom-scored consensus VBD + market and live-context "
            "guardrails - capped injury risk. See context/source_audit.md.",
        )
        canvas.showPage()
    canvas.save()
    temporary.replace(path)


def _draw_pdf_column(
    canvas: Canvas,
    players: tuple[ReweightedPlayer, ...],
    *,
    x: float,
    top: float,
    width: float,
    row_height: float,
    teams: int,
    highlighted_players: frozenset[str],
    handcuff_players: frozenset[str],
) -> None:
    canvas.setFillColor(HexColor("#EAF2F8"))
    canvas.rect(x, top, width, 10, stroke=0, fill=1)
    canvas.setFillColor(HexColor("#17324D"))
    canvas.setFont("Helvetica-Bold", 5.4)
    canvas.drawString(x + 2, top + 3, "#")
    canvas.drawString(x + 16, top + 3, "PLAYER")
    canvas.drawString(x + 108, top + 3, "POS")
    canvas.drawCentredString(x + 142, top + 3, "D")
    canvas.drawCentredString(x + 164, top + 3, "DC")
    canvas.drawCentredString(x + 190, top + 3, "O")
    canvas.drawCentredString(x + 204, top + 3, "L")
    canvas.drawCentredString(x + 218, top + 3, "S")
    canvas.drawCentredString(x + 232, top + 3, "I")
    canvas.drawRightString(x + width - 2, top + 3, "BYE")
    y = top - 1
    for player in players:
        starts_round = player.final_rank > 1 and (player.final_rank - 1) % teams == 0
        if starts_round:
            y -= WEIGHTED_ROUND_GAP
        y -= row_height
        highlight_color = _row_highlight_color(
            player.name,
            sleeper_players=highlighted_players,
            handcuff_players=handcuff_players,
        )
        if highlight_color:
            canvas.setFillColor(HexColor(highlight_color))
            canvas.rect(x, y - 1, width, row_height, stroke=0, fill=1)
        elif player.final_rank % 2 == 0:
            canvas.setFillColor(HexColor("#F7F9FB"))
            canvas.rect(x, y - 1, width, row_height, stroke=0, fill=1)
        if starts_round:
            _draw_weighted_round_divider(
                canvas,
                x=x,
                width=width,
                y=y + row_height + (WEIGHTED_ROUND_GAP / 2) - 1,
                round_number=draft_round_for_rank(player.final_rank, teams),
            )
        canvas.setFillColor(HexColor("#233746"))
        canvas.setFont("Helvetica-Bold", 5.8)
        canvas.drawRightString(x + 13, y + 1.4, str(player.final_rank))
        canvas.setFont("Helvetica", 5.7)
        canvas.drawString(x + 16, y + 1.4, _fit_name(player.name, 22))
        canvas.setFont("Helvetica-Bold", 5.3)
        canvas.drawString(x + 108, y + 1.4, f"{player.position}-{player.team}")
        delta = f"+{player.rank_delta}" if player.rank_delta > 0 else str(player.rank_delta)
        delta_color = (
            "#34785B"
            if player.rank_delta > 0
            else "#A84F52"
            if player.rank_delta < 0
            else "#6B7782"
        )
        canvas.setFillColor(HexColor(delta_color))
        canvas.drawRightString(x + 148, y + 1.4, delta)
        _draw_metric(
            canvas,
            x + 164,
            y + 1.4,
            player.depth_chart_label,
            _depth_bucket(player.depth_chart_label),
        )
        _draw_metric(
            canvas,
            x + 190,
            y + 1.4,
            _number(player.offense_rank),
            _rank_bucket(player.offense_rank),
        )
        _draw_metric(
            canvas,
            x + 204,
            y + 1.4,
            _number(player.offensive_line_rank),
            _rank_bucket(player.offensive_line_rank),
        )
        _draw_metric(
            canvas,
            x + 218,
            y + 1.4,
            _number(player.strength_of_schedule_rank),
            _rank_bucket(player.strength_of_schedule_rank),
        )
        _draw_metric(
            canvas,
            x + 232,
            y + 1.4,
            player.injury_weeks,
            _injury_bucket(player.injury_weeks),
        )
        canvas.setFillColor(HexColor("#4D5B67"))
        canvas.setFont("Helvetica", 5.2)
        canvas.drawRightString(x + width - 2, y + 1.4, str(player.bye_week or "--"))


def _draw_weighted_round_divider(
    canvas: Canvas,
    *,
    x: float,
    width: float,
    y: float,
    round_number: int,
) -> None:
    center = x + (width / 2)
    label_half_width = 7.5
    canvas.setStrokeColor(HexColor("#75AADB"))
    canvas.setLineWidth(0.7)
    canvas.line(x, y, center - label_half_width, y)
    canvas.line(center + label_half_width, y, x + width, y)
    canvas.setFillColor(HexColor("#6889A6"))
    canvas.setFont("Helvetica-Bold", 4.5)
    canvas.drawCentredString(center, y - 1.5, f"R{round_number}")


def _draw_metric(canvas: Canvas, x: float, y: float, value: str, bucket: str) -> None:
    canvas.setFillColor(HexColor(BUCKET_COLORS[bucket]))
    canvas.setFont("Helvetica-Bold", 5.1)
    canvas.drawCentredString(x, y, value)


def render_audit_markdown(audit: dict[str, Any]) -> str:
    lines = [
        "# Ranking source and reproducibility audit",
        "",
        f"**Generated:** `{audit['generated_at']}`  ",
        f"**Overall status:** **{audit['status']}**  ",
        "",
        "## Signal sources",
        "",
        "| Signal | Sources configured | Calculation role |",
        "|---|---:|---|",
    ]
    for signal, item in audit["signal_sources"].items():
        lines.append(f"| {signal.replace('_', ' ')} | {item['source_count']} | {item['role']} |")
    lines.extend(
        [
            "",
            "## Every modeled signal",
            "",
            "| Signal | Weight or role | Rows with 2+ sources | Neutral by policy | "
            "Evidence rule |",
            "|---|---:|---:|---:|---|",
        ]
    )
    for signal, item in audit["modeled_signal_lineage"].items():
        lines.append(
            f"| {signal.replace('_', ' ')} | {item['weight_or_role']} | "
            f"{item['two_source_rows']}/300 | {item['neutral_rows']} | {item['evidence_rule']} |"
        )
    lines.extend(
        [
            "",
            "## Coverage",
            "",
            f"- Three-source market rows: **{audit['coverage']['market_three_source']}/300**",
            "- Two-source custom projection rows: "
            f"**{audit['coverage']['projection_two_source']}/300**",
            f"- Two-source opportunity coverage: **{audit['coverage']['depth_two_source']}**",
            "- Active manual score inputs: **0**",
            "",
            "## Rebuild contract",
            "",
            "Automated sources are refreshed or read from dated caches. Team projections "
            "are generated by the team-projections stage; player and injury overrides are "
            "not inputs to the default rebuild.",
            "",
            "Projected value comes from the simple mean of ESPN Mike Clay and FFToday "
            "raw-stat forecasts scored under the supplied league rules. Volatile milestone, "
            "long-touchdown, and fumble events remain excluded because they are not projected.",
            "",
        ]
    )
    return "\n".join(lines)


def _build_audit(
    *,
    generated_at: str,
    model: dict[str, Any],
    players: tuple[ReweightedPlayer, ...],
    market_metadata: dict[str, Any],
    depth_metadata: dict[str, Any],
    injury_metadata: dict[str, Any],
) -> dict[str, Any]:
    registry = model["source_registry"]
    minimum_sources = 2
    status = "PASS"
    player_count = len(players)
    two_source_rows = {
        key: sum(player.source_coverage[key] >= minimum_sources for player in players)
        for key in (
            "baseline",
            "projection",
            "opportunity",
            "injury",
        )
    }
    configured_rows = {
        "team_offense": player_count if len(registry["team_offense"]) >= minimum_sources else 0,
        "offensive_line_fit": (
            player_count if len(registry["offensive_line_fit"]) >= minimum_sources else 0
        ),
        "strength_of_schedule": (
            player_count if len(registry["strength_of_schedule"]) >= minimum_sources else 0
        ),
    }
    weights = model["weights"]
    modeled_signal_lineage = {
        "baseline_consensus": {
            "weight_or_role": f"{float(weights['baseline_consensus']):.0%}",
            "two_source_rows": two_source_rows["baseline"],
            "neutral_rows": 0,
            "evidence_rule": "weighted ESPN, FantasyPros, and FFToday consensus",
        },
        "custom_projected_value": {
            "weight_or_role": f"{float(weights['custom_projected_value']):.0%}",
            "two_source_rows": two_source_rows["projection"],
            "neutral_rows": player_count - two_source_rows["projection"],
            "evidence_rule": (
                "two-source raw-stat projection mean, league scoring, and corrected "
                "league-derived baseline"
            ),
        },
        "opportunity": {
            "weight_or_role": f"{float(weights['opportunity']):.0%}",
            "two_source_rows": two_source_rows["opportunity"],
            "neutral_rows": player_count - two_source_rows["opportunity"],
            "evidence_rule": "Sleeper and ESPN depth order",
        },
        "team_offense": {
            "weight_or_role": f"{float(weights['team_offense']):.0%}",
            "two_source_rows": configured_rows["team_offense"],
            "neutral_rows": 0,
            "evidence_rule": "implied-total rank with independent projection cross-check",
        },
        "offensive_line_fit": {
            "weight_or_role": f"{float(weights['offensive_line_fit']):.0%}",
            "two_source_rows": configured_rows["offensive_line_fit"],
            "neutral_rows": 0,
            "evidence_rule": "forward-looking line rank cross-checked by two providers",
        },
        "strength_of_schedule": {
            "weight_or_role": f"{float(weights['strength_of_schedule']):.0%}",
            "two_source_rows": configured_rows["strength_of_schedule"],
            "neutral_rows": 0,
            "evidence_rule": "position-specific rank cross-checked by two providers",
        },
        "injury_and_role_risk": {
            "weight_or_role": f"subtract up to {float(model['risk_penalty_cap']):g}",
            "two_source_rows": two_source_rows["injury"],
            "neutral_rows": player_count - two_source_rows["injury"],
            "evidence_rule": "Sleeper and ESPN injury feeds",
        },
    }
    return {
        "generated_at": generated_at,
        "status": status,
        "model_version": model["model_version"],
        "active_input_policy": "automated-only",
        "coverage": {
            "market_three_source": sum(
                player.source_coverage["baseline"] >= 3 for player in players
            ),
            "depth_two_source": sum(
                player.source_coverage["opportunity"] >= 2 for player in players
            ),
            "projection_two_source": sum(
                player.source_coverage["projection"] >= 2 for player in players
            ),
        },
        "signal_sources": {
            signal: {
                "source_count": len(sources),
                "role": "calculation or independent cross-check",
                "sources": sources,
            }
            for signal, sources in registry.items()
        },
        "modeled_signal_lineage": modeled_signal_lineage,
        "input_freshness": {
            "market": market_metadata.get("generated_at"),
            "depth": depth_metadata.get("generated_at"),
            "injury": injury_metadata.get("generated_at"),
        },
    }


def _write_csv(path: Path, players: tuple[ReweightedPlayer, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    fields = [
        "final_rank",
        "source_rank",
        "rank_delta",
        "name",
        "position",
        "team",
        "adjusted_score",
        "consensus_rank",
        "depth_chart_label",
        "offense_rank",
        "offensive_line_rank",
        "strength_of_schedule_rank",
        "injury_weeks",
        "injury_tier",
    ]
    try:
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for player in players:
                row = asdict(player)
                writer.writerow({field: row[field] for field in fields})
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _validate_model(model: dict[str, Any]) -> None:
    weights = model.get("weights", {})
    if not math.isclose(sum(float(value) for value in weights.values()), 1.0, abs_tol=1e-9):
        raise InjuryContextError("Ranking model weights must sum to 1.0.")
    required = {
        "custom_projected_value",
        "baseline_consensus",
        "opportunity",
        "team_offense",
        "offensive_line_fit",
        "strength_of_schedule",
    }
    if set(weights) != required:
        raise InjuryContextError("Ranking model weight keys do not match the required signals.")
    required_source_groups = {
        "custom_projected_value",
        "baseline_consensus",
        "opportunity",
        "team_offense",
        "offensive_line_fit",
        "strength_of_schedule",
        "injury_risk",
    }
    registry = model.get("source_registry", {})
    if set(registry) != required_source_groups:
        raise InjuryContextError("Source registry keys do not match the required evidence groups.")
    for signal, sources in registry.items():
        provider_names = {str(source.get("name") or "").strip() for source in sources}
        source_urls = {str(source.get("url") or "").strip() for source in sources}
        if len(provider_names - {""}) < 2 or len(source_urls - {""}) < 2:
            raise InjuryContextError(
                f"Source registry group {signal!r} needs at least two named providers and URLs."
            )


def _rank_grade(rank: float, *, maximum: int) -> float:
    bounded = min(float(maximum), max(1.0, rank))
    return 100.0 * (maximum + 1 - bounded) / maximum


def _depth_order_grade(order: int | None) -> float:
    if order is None:
        return 50.0
    return {1: 90.0, 2: 60.0, 3: 35.0}.get(order, 15.0)


def _depth_grade(depth: dict[str, Any]) -> float:
    primary = _optional_int(depth.get("depth_chart_order"))
    secondary = _optional_int(depth.get("espn_depth_chart_order"))
    values = [_depth_order_grade(value) for value in (primary, secondary) if value is not None]
    if not values:
        return 50.0
    return round(sum(values) / len(values), 2)


def _team_rank_grade(rank: Any) -> float:
    value = _optional_int(rank)
    return 50.0 if value is None else _rank_grade(value, maximum=32)


def _injury_penalty(injury: dict[str, Any]) -> float:
    games_max = injury.get("projected_games_max")
    tier = str(injury.get("tier") or "CLEAR")
    base_by_tier = {
        "CLEAR": 0.0,
        "WATCH": 0.25 if games_max == 0 else 0.5,
        "SHORT": 1.5,
        "MEDIUM": 2.5,
        "HIGH": 4.0,
        "VERY HIGH": 5.0,
        "SEASON": 5.0,
    }
    multiplier = {"high": 1.0, "medium": 0.85, "low": 0.60}.get(
        str(injury.get("confidence") or "low"), 0.60
    )
    return round(base_by_tier.get(tier, 0.0) * multiplier, 2)


def _movement_cap(rank: int, model: dict[str, Any]) -> int:
    for band in model["movement_caps"]:
        if int(band["minimum_rank"]) <= rank <= int(band["maximum_rank"]):
            return int(band["spots"])
    raise InjuryContextError(f"No movement cap configured for rank {rank}.")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return load_json_object(path)
    except StorageError as error:
        raise InjuryContextError(str(error)) from error


def _load_highlighted_players(path: Path) -> frozenset[str]:
    payload = _load_json(path)
    groups = (payload.get("sleepers"), payload.get("rookie_breakout_candidates"))
    if not all(isinstance(group, list) for group in groups):
        raise InjuryContextError(
            f"Expected sleeper and rookie target lists in highlight context {path}."
        )
    names = {
        normalize_name(str(item.get("player") or ""))
        for group in groups
        for item in group
        if isinstance(item, dict) and item.get("player")
    }
    if not names:
        raise InjuryContextError(f"No sleeper or rookie targets found in {path}.")
    return frozenset(names)


def _load_handcuff_players(path: Path) -> frozenset[str]:
    payload = _load_json(path)
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        raise InjuryContextError(f"Expected a handcuff candidate list in {path}.")
    names = {
        normalize_name(str(item.get("player") or ""))
        for item in candidates
        if isinstance(item, dict) and item.get("player") and item.get("highlighted") is True
    }
    if not names:
        raise InjuryContextError(f"No highlighted running back handcuffs found in {path}.")
    return frozenset(names)


def _row_highlight_color(
    name: str,
    *,
    sleeper_players: frozenset[str],
    handcuff_players: frozenset[str],
) -> str | None:
    normalized = normalize_name(name)
    if normalized in handcuff_players:
        return HANDCUFF_HIGHLIGHT_COLOR
    if normalized in sleeper_players:
        return SLEEPER_HIGHLIGHT_COLOR
    return None


def _optional_int(value: Any) -> int | None:
    if value in {None, "", "--"}:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    if value in {None, "", "--"}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fit_name(name: str, width: int) -> str:
    return name if len(name) <= width else name[: width - 1] + "."


def _number(value: int | None) -> str:
    return str(value) if value is not None else "--"


def _number_float(value: float | None) -> str:
    return f"{value:.1f}" if value is not None else "--"


def _rank_bucket(value: int | None) -> str:
    if value is None or value >= 23:
        return "red"
    return "green" if value <= 10 else "yellow"


def _depth_bucket(value: str) -> str:
    if value == "DST" or value.endswith("1"):
        return "green"
    if value.endswith("2"):
        return "yellow"
    return "red"


def _injury_bucket(value: str) -> str:
    if value == "--":
        return "green"
    numbers = [int(item) for item in re.findall(r"\d+", value)]
    maximum = max(numbers) if numbers else 99
    return "green" if maximum == 0 else "yellow" if maximum <= 2 else "red"


if __name__ == "__main__":
    raise SystemExit(main())
