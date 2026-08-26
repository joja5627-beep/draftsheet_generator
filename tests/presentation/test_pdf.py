from pathlib import Path

import pdfplumber
import pytest
from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen.canvas import Canvas

from fantasy_football_2026.presentation.pdf import (
    CONTEXT_RANGE_FONT_SIZE,
    CONTEXT_VALUE_FONT_SIZE,
    PLAYER_NAME_FONT_SIZE,
    DraftSheetError,
    HighlightStyle,
    PageInspection,
    RankRow,
    _context_column_centers,
    _context_lane_bounds,
    _movement_label,
    _register_metric_font,
    _template_column_geometry,
    draft_round_for_rank,
    highlight_draft_rounds,
    inspect_draft_sheet,
    reflow_draft_sheet,
    render_reweighted_template_pdf,
)

SOURCE_PDF = Path("NFL26_CS_PPR300.pdf")
requires_source_pdf = pytest.mark.skipif(
    not SOURCE_PDF.is_file(),
    reason="requires the locally downloaded ESPN draft-kit PDF",
)


def test_draft_round_for_rank_uses_league_size() -> None:
    assert draft_round_for_rank(1, teams=12) == 1
    assert draft_round_for_rank(12, teams=12) == 1
    assert draft_round_for_rank(13, teams=12) == 2
    assert draft_round_for_rank(300, teams=12) == 25


def test_style_rejects_non_hex_color() -> None:
    with pytest.raises(DraftSheetError, match="#RRGGBB"):
        HighlightStyle(color="light blue").validate()


def test_default_style_uses_lines_without_highlight_blocks() -> None:
    style = HighlightStyle()
    assert style.primary_opacity == 0
    assert style.secondary_opacity == 0


def test_highlight_draft_rounds_detects_columns_and_writes_pdf(tmp_path: Path) -> None:
    source = tmp_path / "draft-sheet.pdf"
    output = tmp_path / "draft-sheet-highlighted.pdf"
    _make_ranked_fixture(source)

    inspections = inspect_draft_sheet(source, maximum_rank=24)
    assert len(inspections) == 1
    assert len(inspections[0].columns) == 2
    assert len(inspections[0].salary_values) == 24
    assert len(inspections[0].bye_week_values) == 24
    assert inspections[0].bye_week_legend == ()
    assert sorted(row.rank for row in inspections[0].rows) == list(range(1, 25))

    result = highlight_draft_rounds(
        source,
        output,
        teams=12,
        maximum_rank=24,
        draft_context_labels={rank: ("RB1", "3", "14", "2", "0") for rank in range(1, 25)},
    )

    assert output.is_file()
    assert result.ranks_found == tuple(range(1, 25))
    assert result.rounds_found == (1, 2)
    assert result.salary_values_removed == 24
    assert result.bye_week_values_replaced == 24
    assert len(PdfReader(output).pages) == 1
    with pdfplumber.open(output) as document:
        assert "Player 24" in (document.pages[0].extract_text() or "")


def test_highlighter_refuses_missing_ranks_by_default(tmp_path: Path) -> None:
    source = tmp_path / "draft-sheet.pdf"
    _make_ranked_fixture(source)

    with pytest.raises(DraftSheetError, match="Missing"):
        highlight_draft_rounds(source, tmp_path / "output.pdf", maximum_rank=25)


@requires_source_pdf
def test_reflow_real_sheet_removes_footer_and_expands_round_gap(tmp_path: Path) -> None:
    source = SOURCE_PDF
    output = tmp_path / "reflowed.pdf"
    original = inspect_draft_sheet(source)[0]

    reflow_draft_sheet(source, output)

    expanded = inspect_draft_sheet(output)[0]
    original_rows = {row.rank: row for row in original.rows}
    expanded_rows = {row.rank: row for row in expanded.rows}
    original_gap = original_rows[13].top - original_rows[12].bottom
    expanded_gap = expanded_rows[13].top - expanded_rows[12].bottom
    assert expanded_gap > original_gap + 2.0
    assert expanded_rows[80].bottom > original_rows[80].bottom + 80.0
    with pdfplumber.open(output) as document:
        page = document.pages[0]
        text = page.extract_text() or ""
        words = page.extract_words(extra_attrs=["size"])
    assert "Salary Cap Value" not in text
    assert "Overall Rank (Positional Rank)" not in text
    name_word = next(word for word in words if word["text"] == "Rhamondre")
    rank_word = next(word for word in words if word["text"].startswith("64."))
    assert float(name_word["size"]) == pytest.approx(PLAYER_NAME_FONT_SIZE)
    assert float(name_word["size"]) < float(rank_word["size"])


@requires_source_pdf
def test_fixed_context_grid_has_gutters_for_widest_values() -> None:
    inspection = inspect_draft_sheet(SOURCE_PDF)[0]
    left, right = _context_lane_bounds(inspection, inspection.columns[0])
    centers = _context_column_centers(left, right)
    font = _register_metric_font()
    labels = ("RWR3", "32", "32", "32", "5-6")
    sizes = (
        CONTEXT_VALUE_FONT_SIZE,
        CONTEXT_VALUE_FONT_SIZE,
        CONTEXT_VALUE_FONT_SIZE,
        CONTEXT_VALUE_FONT_SIZE,
        CONTEXT_RANGE_FONT_SIZE,
    )
    boxes = [
        (
            center - (pdfmetrics.stringWidth(label, font, size) / 2),
            center + (pdfmetrics.stringWidth(label, font, size) / 2),
        )
        for center, label, size in zip(centers, labels, sizes, strict=True)
    ]

    assert all(
        current[1] + 0.5 < following[0]
        for current, following in zip(boxes, boxes[1:], strict=False)
    )


@requires_source_pdf
def test_reflow_real_sheet_can_apply_reweighted_order(tmp_path: Path) -> None:
    mapping = {rank: rank for rank in range(1, 301)}
    mapping[1], mapping[2] = 2, 1
    position_labels = {rank: f"RB{rank}" for rank in range(1, 301)}
    position_labels[1] = "WR1"

    with pdfplumber.open(SOURCE_PDF) as source:
        source_words = source.pages[0].extract_words()
        source_inspection = inspect_draft_sheet(SOURCE_PDF)[0]
        first_row = next(row for row in source_inspection.rows if row.rank == 1)
        second_row = next(row for row in source_inspection.rows if row.rank == 2)
        first_name = _row_words(source_words, first_row, source_inspection)[2]["text"]
        second_name = _row_words(source_words, second_row, source_inspection)[2]["text"]

    output = tmp_path / "test-reweighted-template.pdf"
    try:
        reflow_draft_sheet(
            SOURCE_PDF,
            output,
            rank_mapping=mapping,
            position_rank_labels=position_labels,
            title="2026 Custom-League Reweighted Top 300",
        )
        inspection = inspect_draft_sheet(output)[0]
        reader = PdfReader(output)
        assert reader.metadata is not None
        assert reader.metadata.title == "2026 Custom-League Reweighted Top 300"
        with pdfplumber.open(output) as document:
            words = document.pages[0].extract_words()
            text = document.pages[0].extract_text() or ""
        output_first = next(row for row in inspection.rows if row.rank == 1)
        output_second = next(row for row in inspection.rows if row.rank == 2)

        assert second_name in {word["text"] for word in _row_words(words, output_first, inspection)}
        assert first_name in {word["text"] for word in _row_words(words, output_second, inspection)}
        assert any(
            "(WR1)" in str(word["text"]) for word in _row_words(words, output_first, inspection)
        )
        assert "2026 Custom-League Reweighted Top 300" in text
    finally:
        output.unlink(missing_ok=True)


@requires_source_pdf
def test_two_sided_template_uses_two_wider_columns_per_page(tmp_path: Path) -> None:
    output = tmp_path / "two-sided.pdf"
    players = [
        {
            "final_rank": rank,
            "position_rank": f"RB{rank}",
            "name": f"Player {rank}",
            "team": "DET",
            "depth_chart_label": "RB1",
            "offense_rank": 3,
            "offensive_line_rank": 14,
            "strength_of_schedule_rank": 2,
            "injury_weeks": "0",
            "rank_delta": 2 if rank == 1 else -3 if rank == 2 else 0,
        }
        for rank in range(1, 301)
    ]

    render_reweighted_template_pdf(
        SOURCE_PDF,
        output,
        players=players,
        row_highlight_colors={1: "#FFF1A8", 151: "#E5D8F5"},
    )

    reader = PdfReader(output)
    assert len(reader.pages) == 2
    with pdfplumber.open(output) as document:
        first_text = document.pages[0].extract_text() or ""
        second_text = document.pages[1].extract_text() or ""
        first_words = document.pages[0].extract_words(extra_attrs=["size"])
    assert "RANKINGS 1-75" in first_text
    assert "RANKINGS 76-150" in first_text
    assert "RANKINGS 151-225" in second_text
    assert "RANKINGS 226-300" in second_text
    assert "1. (RB1)" in first_text
    assert "300. (RB300)" in second_text
    assert "MOV" in first_text
    assert "+2" in first_text
    assert "-3" in first_text
    assert "MOV: + up / - down vs 7-source anchor" in first_text
    player_word = next(word for word in first_words if word["text"] == "Player")
    movement_word = next(word for word in first_words if word["text"] == "+2")
    context_word = next(word for word in first_words if word["text"] == "RB1")
    assert float(player_word["size"]) > PLAYER_NAME_FONT_SIZE
    assert float(movement_word["size"]) >= 5.8
    assert float(context_word["size"]) >= 5.8


def test_template_column_lanes_use_all_available_inner_width() -> None:
    geometry = _template_column_geometry(x=12.0, width=291.0)

    assert geometry.rank_width == pytest.approx(40.0)
    assert geometry.player_left == pytest.approx(54.0)
    assert geometry.movement_width == pytest.approx(24.0)
    assert geometry.context_width == pytest.approx(139.0)
    assert geometry.player_width == pytest.approx(84.0)
    assert (
        geometry.rank_width
        + geometry.player_width
        + geometry.movement_width
        + geometry.context_width
    ) == pytest.approx(geometry.inner_right - geometry.inner_left)
    assert _movement_label(3) == "+3"
    assert _movement_label(-2) == "-2"
    assert _movement_label(0) == "0"


def _row_words(
    words: list[dict[str, object]],
    row: RankRow,
    inspection: PageInspection,
) -> list[dict[str, object]]:
    column = inspection.columns[row.column]
    center = (row.top + row.bottom) / 2
    return sorted(
        (
            word
            for word in words
            if column.x_start <= float(word["x0"]) <= column.x_end
            and abs(((float(word["top"]) + float(word["bottom"])) / 2) - center) <= 1.5
        ),
        key=lambda word: float(word["x0"]),
    )


def _make_ranked_fixture(path: Path) -> None:
    canvas = Canvas(str(path), pagesize=letter)
    canvas.setFont("Helvetica", 8)
    for column, first_rank in enumerate((1, 13)):
        x = 50 + (column * 260)
        for offset in range(12):
            rank = first_rank + offset
            y = 730 - (offset * 14)
            canvas.drawString(x, y, f"{rank}.")
            canvas.drawString(x + 25, y, f"Player {rank}")
            canvas.drawString(x + 175, y, f"${25 - rank}")
            canvas.drawString(x + 210, y, "7")
    # A page number can look like a ranking token and align with a real column.
    canvas.drawString(310, 25, "1.")
    canvas.save()
