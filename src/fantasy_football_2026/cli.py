"""Command-line interface for draft-sheet PDF tools."""

from __future__ import annotations

import argparse
from pathlib import Path

from fantasy_football_2026.constants import (
    DEFAULT_LEAGUE_TEAMS,
    ROUND_LINE_COLOR,
    TOTAL_RANKED_PLAYERS,
    ContextFile,
    DirectoryName,
)
from fantasy_football_2026.errors import DraftSheetError, InjuryContextError
from fantasy_football_2026.presentation.pdf import (
    HighlightStyle,
    highlight_draft_rounds,
    inspect_draft_sheet,
    reflow_draft_sheet,
)
from fantasy_football_2026.sources.depth_charts import load_draft_sheet_context


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fantasy-pdf",
        description="Inspect and highlight fantasy-football draft-sheet PDFs.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    inspect_parser = commands.add_parser(
        "inspect",
        help="show detected overall rankings and printed columns",
    )
    inspect_parser.add_argument("input", type=Path)
    _add_rank_range_arguments(inspect_parser)

    highlight_parser = commands.add_parser(
        "highlight-rounds",
        help="draw projected draft-round boundary lines",
    )
    highlight_parser.add_argument("input", type=Path)
    highlight_parser.add_argument(
        "--output",
        type=Path,
        help="output PDF (default: output/pdf/<input>-12-team-rounds.pdf)",
    )
    highlight_parser.add_argument("--teams", type=int, default=DEFAULT_LEAGUE_TEAMS)
    highlight_parser.add_argument("--color", default=ROUND_LINE_COLOR)
    highlight_parser.add_argument("--primary-opacity", type=float, default=0.0)
    highlight_parser.add_argument("--secondary-opacity", type=float, default=0.0)
    highlight_parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="write output even if some expected overall rankings are not detected",
    )
    highlight_parser.add_argument(
        "--keep-dollar-column",
        action="store_false",
        dest="remove_dollar_column",
        help="keep the source sheet's salary-cap dollar values",
    )
    highlight_parser.add_argument(
        "--keep-bye-week",
        action="store_true",
        help="keep bye weeks instead of replacing them with team depth-chart slots",
    )
    highlight_parser.add_argument(
        "--keep-footer-layout",
        action="store_true",
        help="keep the compact source layout and footer instead of expanding the rankings",
    )
    highlight_parser.add_argument(
        "--depth-chart-context",
        type=Path,
        default=Path(DirectoryName.CONTEXT, ContextFile.DRAFT_CONTEXT_JSON),
        help="unified market, depth-chart, offense, line, schedule, injury, and sleeper context",
    )
    highlight_parser.set_defaults(remove_dollar_column=True)
    _add_rank_range_arguments(highlight_parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            inspections = inspect_draft_sheet(
                args.input,
                minimum_rank=args.minimum_rank,
                maximum_rank=args.maximum_rank,
            )
            total = 0
            for inspection in inspections:
                ranks = sorted(row.rank for row in inspection.rows)
                total += len(ranks)
                rank_range = f"{ranks[0]}-{ranks[-1]}" if ranks else "none"
                print(
                    f"Page {inspection.page_number}: {len(ranks)} rankings "
                    f"({rank_range}), {len(inspection.columns)} columns"
                )
            print(f"Detected {total} rankings total.")
            return 0

        output = args.output or _default_output(args.input, args.teams)
        draft_context_labels = (
            None if args.keep_bye_week else load_draft_sheet_context(args.depth_chart_context)
        )
        reflowed_input = (
            Path(DirectoryName.TEMPORARY, DirectoryName.PDF)
            / f".{args.input.stem}-expanded-layout.pdf"
        )
        source_for_highlighting = args.input
        try:
            if not args.keep_footer_layout:
                source_for_highlighting = reflow_draft_sheet(
                    args.input,
                    reflowed_input,
                    teams=args.teams,
                )
            result = highlight_draft_rounds(
                source_for_highlighting,
                output,
                teams=args.teams,
                minimum_rank=args.minimum_rank,
                maximum_rank=args.maximum_rank,
                style=HighlightStyle(
                    color=args.color,
                    primary_opacity=args.primary_opacity,
                    secondary_opacity=args.secondary_opacity,
                ),
                allow_missing=args.allow_missing,
                remove_dollar_column=args.remove_dollar_column,
                draft_context_labels=draft_context_labels,
            )
        finally:
            if not args.keep_footer_layout:
                reflowed_input.unlink(missing_ok=True)
        print(
            f"Highlighted {len(result.ranks_found)} rankings across "
            f"{len(result.rounds_found)} projected rounds."
        )
        print(f"Line color: {result.color}")
        if result.salary_values_removed:
            print(f"Dollar values removed: {result.salary_values_removed}")
        if result.bye_week_values_replaced:
            print(f"Bye weeks replaced: {result.bye_week_values_replaced}")
        print(f"Output: {result.output_path}")
        return 0
    except (DraftSheetError, InjuryContextError) as error:
        parser.exit(2, f"error: {error}\n")


def _add_rank_range_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--minimum-rank", type=int, default=1)
    parser.add_argument("--maximum-rank", type=int, default=TOTAL_RANKED_PLAYERS)


def _default_output(input_path: Path, teams: int) -> Path:
    return Path(DirectoryName.OUTPUT, DirectoryName.PDF) / (
        f"{input_path.stem}-{teams}-team-rounds.pdf"
    )


if __name__ == "__main__":
    raise SystemExit(main())
