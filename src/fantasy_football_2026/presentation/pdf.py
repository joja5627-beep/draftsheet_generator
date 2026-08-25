"""Detect overall rankings in a PDF and shade projected draft-round bands."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from io import BytesIO
from pathlib import Path

import pdfplumber
import pymupdf
from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import Color, HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from fantasy_football_2026.errors import DraftSheetError
from fantasy_football_2026.presentation.buckets import BUCKET_COLORS, context_bucket

RANK_TOKEN = re.compile(r"^(?P<rank>\d{1,3})\.$")
SALARY_TOKEN = re.compile(r"^\$\d+(?:\.\d+)?$")
PLAYER_NAME_FONT_SIZE = 4.5
CONTEXT_VALUE_FONT_SIZE = 4.1
CONTEXT_RANGE_FONT_SIZE = 3.9
CONTEXT_HEADER_FONT_SIZE = 2.6
CONTEXT_LANE_LEFT_PADDING = 15.0


@dataclass(frozen=True, slots=True)
class RankRow:
    """Location of one overall-rank token in pdfplumber coordinates."""

    page_index: int
    rank: int
    x0: float
    x1: float
    top: float
    bottom: float
    column: int = -1


@dataclass(frozen=True, slots=True)
class TextRegion:
    """Rectangular text location in pdfplumber coordinates."""

    x0: float
    x1: float
    top: float
    bottom: float


@dataclass(frozen=True, slots=True)
class RankedTextRegion(TextRegion):
    """Text location associated with one overall ranking row."""

    rank: int


@dataclass(frozen=True, slots=True)
class ColumnLayout:
    """Detected rank column and the horizontal area that belongs to it."""

    index: int
    x_start: float
    x_end: float
    rows: tuple[RankRow, ...]


@dataclass(frozen=True, slots=True)
class HighlightStyle:
    """Visual settings for draft-round boundary lines and optional bands."""

    color: str = "#75AADB"
    primary_opacity: float = 0.0
    secondary_opacity: float = 0.0
    divider_opacity: float = 0.72
    label_opacity: float = 0.88

    def validate(self) -> None:
        _hex_color(self.color)
        for name, value in (
            ("primary_opacity", self.primary_opacity),
            ("secondary_opacity", self.secondary_opacity),
            ("divider_opacity", self.divider_opacity),
            ("label_opacity", self.label_opacity),
        ):
            if not 0 <= value <= 1:
                raise DraftSheetError(f"{name} must be between 0 and 1, got {value}.")


@dataclass(frozen=True, slots=True)
class PageInspection:
    """Detected ranking layout for a single PDF page."""

    page_number: int
    width: float
    height: float
    columns: tuple[ColumnLayout, ...]
    salary_values: tuple[TextRegion, ...]
    bye_week_values: tuple[RankedTextRegion, ...]
    bye_week_legend: tuple[TextRegion, ...]

    @property
    def rows(self) -> tuple[RankRow, ...]:
        return tuple(row for column in self.columns for row in column.rows)


@dataclass(frozen=True, slots=True)
class HighlightResult:
    """Summary of a completed highlighting operation."""

    output_path: Path
    ranks_found: tuple[int, ...]
    rounds_found: tuple[int, ...]
    page_count: int
    color: str
    salary_values_removed: int
    bye_week_values_replaced: int


def draft_round_for_rank(rank: int, teams: int = 12) -> int:
    """Return the projected round containing an overall rank."""

    if rank < 1:
        raise DraftSheetError(f"rank must be positive, got {rank}.")
    if teams < 2:
        raise DraftSheetError(f"teams must be at least 2, got {teams}.")
    return ((rank - 1) // teams) + 1


def reflow_draft_sheet(
    input_path: str | Path,
    output_path: str | Path,
    *,
    teams: int = 12,
    bottom_margin: float = 10.0,
) -> Path:
    """Remove footer content and redistribute ranking rows with larger round gaps."""

    source = Path(input_path).expanduser().resolve()
    destination = Path(output_path).expanduser().resolve()
    if source == destination:
        raise DraftSheetError("Reflow output must differ from the source PDF.")
    inspections = inspect_draft_sheet(source)
    if sum(len(inspection.rows) for inspection in inspections) != 300:
        raise DraftSheetError("Expanded layout requires the complete 300-row draft sheet.")

    source_document = pymupdf.open(source)
    header_document = pymupdf.open()
    try:
        for page_index, inspection in enumerate(inspections):
            header_page = header_document.new_page(
                width=inspection.width,
                height=inspection.height,
            )
            header_bottom = min(row.top for row in inspection.rows) - 1.6
            header_clip = pymupdf.Rect(0, 0, inspection.width, header_bottom)
            header_pixmap = source_document[page_index].get_pixmap(
                matrix=pymupdf.Matrix(4, 4),
                clip=header_clip,
                alpha=False,
            )
            header_page.insert_image(header_clip, pixmap=header_pixmap)
        header_bytes = header_document.tobytes(garbage=4, deflate=True)
        source_metadata = source_document.metadata
    finally:
        header_document.close()
        source_document.close()

    writer = PdfWriter(clone_from=BytesIO(header_bytes))
    with pdfplumber.open(source) as document:
        for page_index, page in enumerate(writer.pages):
            source_page = document.pages[page_index]
            words = source_page.extract_words(
                x_tolerance=1.5,
                y_tolerance=2.0,
                keep_blank_chars=False,
                use_text_flow=False,
                extra_attrs=["fontname", "size"],
            )
            overlay = PdfReader(
                _make_reflow_overlay(
                    inspections[page_index],
                    words,
                    teams=teams,
                    bottom_margin=bottom_margin,
                )
            ).pages[0]
            page.merge_page(overlay, over=True)

    metadata = {
        key: value
        for key, value in source_metadata.items()
        if isinstance(key, str) and isinstance(value, str) and value
    }
    metadata["/Subject"] = "Footer-free expanded PPR Top 300 layout"
    metadata["/Producer"] = "fantasy-football-2026 PDF layout reflow"
    writer.add_metadata(
        {
            key if key.startswith("/") else f"/{key.title()}": value
            for key, value in metadata.items()
        }
    )

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    try:
        with temporary.open("wb") as output_file:
            writer.write(output_file)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def _make_reflow_overlay(
    inspection: PageInspection,
    words: list[dict[str, object]],
    *,
    teams: int,
    bottom_margin: float,
) -> BytesIO:
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=(inspection.width, inspection.height), pageCompression=1)
    font_name = _register_table_font()
    for column in inspection.columns:
        destination_centers = _reflowed_row_centers(
            column,
            inspection.height,
            teams=teams,
            bottom_margin=bottom_margin,
        )
        for row in column.rows:
            source_center = (row.top + row.bottom) / 2
            destination_center = destination_centers[row.rank]
            row_words = sorted(
                (
                    word
                    for word in words
                    if column.x_start <= float(word["x0"]) <= column.x_end
                    and abs(((float(word["top"]) + float(word["bottom"])) / 2) - source_center)
                    <= 1.5
                ),
                key=lambda word: float(word["x0"]),
            )
            salary_index = next(
                (
                    index
                    for index, word in enumerate(row_words)
                    if SALARY_TOKEN.fullmatch(str(word["text"]))
                ),
                None,
            )
            if salary_index is None or salary_index < 3:
                raise DraftSheetError(f"Could not reflow ranking row {row.rank}.")

            for index, word in enumerate(row_words):
                if index == 2:
                    name = " ".join(
                        str(name_word["text"]) for name_word in row_words[2:salary_index]
                    )
                    new_bottom = float(word["bottom"]) + (destination_center - source_center)
                    baseline = inspection.height - new_bottom + (PLAYER_NAME_FONT_SIZE * 0.185)
                    canvas.setFillColorRGB(0, 0, 0)
                    canvas.setFont(font_name, PLAYER_NAME_FONT_SIZE)
                    canvas.drawString(float(word["x0"]), baseline, name)
                    continue
                if 2 < index < salary_index:
                    continue
                font_size = float(word.get("size") or 5.4)
                new_bottom = float(word["bottom"]) + (destination_center - source_center)
                baseline = inspection.height - new_bottom + (font_size * 0.185)
                canvas.setFillColorRGB(0, 0, 0)
                canvas.setFont(font_name, font_size)
                canvas.drawString(float(word["x0"]), baseline, str(word["text"]))

    canvas.setFillColorRGB(0.0, 0.0, 0.502)
    canvas.rect(
        inspection.columns[0].x_start,
        3.0,
        (inspection.columns[-1].x_end - 10.0) - inspection.columns[0].x_start,
        4.0,
        stroke=0,
        fill=1,
    )
    canvas.showPage()
    canvas.save()
    buffer.seek(0)
    return buffer


def _reflowed_row_centers(
    column: ColumnLayout,
    page_height: float,
    *,
    teams: int,
    bottom_margin: float,
) -> dict[int, float]:
    rows = sorted(column.rows, key=lambda row: row.top)
    first_center = (rows[0].top + rows[0].bottom) / 2
    row_height = rows[0].bottom - rows[0].top
    base_step = 8.65
    round_boundaries = sum(
        draft_round_for_rank(current.rank, teams) != draft_round_for_rank(previous.rank, teams)
        for previous, current in zip(rows, rows[1:], strict=False)
    )
    round_gap = 3.0
    if len(rows) >= 75 and round_boundaries:
        target_last_center = page_height - bottom_margin - (row_height / 2)
        remaining = target_last_center - first_center - (base_step * (len(rows) - 1))
        round_gap = max(3.0, remaining / round_boundaries)

    centers: dict[int, float] = {}
    destination_center = first_center
    for index, row in enumerate(rows):
        if index:
            destination_center += base_step
            if draft_round_for_rank(row.rank, teams) != draft_round_for_rank(
                rows[index - 1].rank, teams
            ):
                destination_center += round_gap
        centers[row.rank] = destination_center
    return centers


def _register_table_font() -> str:
    font_name = "FantasyDraftArial"
    if font_name in pdfmetrics.getRegisteredFontNames():
        return font_name
    candidates = (
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/Library/Fonts/Arial.ttf"),
    )
    font_path = next((path for path in candidates if path.is_file()), None)
    if font_path is None:
        return "Helvetica"
    pdfmetrics.registerFont(TTFont(font_name, font_path))
    return font_name


def _register_metric_font() -> str:
    font_name = "FantasyDraftArialNarrowBold"
    if font_name in pdfmetrics.getRegisteredFontNames():
        return font_name
    candidates = (
        Path("/System/Library/Fonts/Supplemental/Arial Narrow Bold.ttf"),
        Path("/Library/Fonts/Arial Narrow Bold.ttf"),
    )
    font_path = next((path for path in candidates if path.is_file()), None)
    if font_path is None:
        return "Helvetica-Bold"
    pdfmetrics.registerFont(TTFont(font_name, font_path))
    return font_name


def inspect_draft_sheet(
    input_path: str | Path,
    *,
    minimum_rank: int = 1,
    maximum_rank: int = 300,
) -> tuple[PageInspection, ...]:
    """Locate numbered ranking rows and group them into printed columns."""

    source = Path(input_path).expanduser().resolve()
    if not source.is_file():
        raise DraftSheetError(f"Input PDF does not exist: {source}")
    if source.suffix.lower() != ".pdf":
        raise DraftSheetError(f"Input must be a PDF: {source}")
    if minimum_rank < 1 or maximum_rank < minimum_rank:
        raise DraftSheetError("Rank range must satisfy 1 <= minimum_rank <= maximum_rank.")

    inspections: list[PageInspection] = []
    seen_ranks: set[int] = set()
    with pdfplumber.open(source) as document:
        for page_index, page in enumerate(document.pages):
            detected: list[RankRow] = []
            words = page.extract_words(
                x_tolerance=1.5,
                y_tolerance=2.0,
                keep_blank_chars=False,
                use_text_flow=False,
            )
            for word in words:
                match = RANK_TOKEN.fullmatch(str(word["text"]).strip())
                if not match:
                    continue
                rank = int(match.group("rank"))
                if not minimum_rank <= rank <= maximum_rank:
                    continue
                detected.append(
                    RankRow(
                        page_index=page_index,
                        rank=rank,
                        x0=float(word["x0"]),
                        x1=float(word["x1"]),
                        top=float(word["top"]),
                        bottom=float(word["bottom"]),
                    )
                )

            columns = _build_column_layouts(detected, float(page.width))
            ranked_rows = tuple(row for column in columns for row in column.rows)
            for row in (row for column in columns for row in column.rows):
                if row.rank in seen_ranks:
                    raise DraftSheetError(
                        f"Overall rank {row.rank} appears more than once in ranking columns; "
                        "cannot safely shade rows."
                    )
                seen_ranks.add(row.rank)
            salary_values = _find_salary_values(words, ranked_rows)
            bye_week_values = _find_bye_week_values(words, columns)
            bye_week_legend = _find_bye_week_legend(words, ranked_rows)
            inspections.append(
                PageInspection(
                    page_number=page_index + 1,
                    width=float(page.width),
                    height=float(page.height),
                    columns=columns,
                    salary_values=salary_values,
                    bye_week_values=bye_week_values,
                    bye_week_legend=bye_week_legend,
                )
            )

    return tuple(inspections)


def highlight_draft_rounds(
    input_path: str | Path,
    output_path: str | Path,
    *,
    teams: int = 12,
    minimum_rank: int = 1,
    maximum_rank: int = 300,
    style: HighlightStyle | None = None,
    allow_missing: bool = False,
    remove_dollar_column: bool = True,
    draft_context_labels: Mapping[int, tuple[str, str, str, str, str]] | None = None,
) -> HighlightResult:
    """Add alternating translucent bands for projected draft rounds."""

    if teams < 2:
        raise DraftSheetError(f"teams must be at least 2, got {teams}.")
    chosen_style = style or HighlightStyle()
    chosen_style.validate()

    source = Path(input_path).expanduser().resolve()
    destination = Path(output_path).expanduser().resolve()
    if source == destination:
        raise DraftSheetError("Output must differ from the source PDF.")

    inspections = inspect_draft_sheet(
        source,
        minimum_rank=minimum_rank,
        maximum_rank=maximum_rank,
    )
    rows = tuple(row for inspection in inspections for row in inspection.rows)
    ranks_found = tuple(sorted(row.rank for row in rows))
    if not ranks_found:
        raise DraftSheetError(
            "No overall ranking tokens were found. Expected labels such as '1.' and '2.'."
        )

    expected = set(range(minimum_rank, maximum_rank + 1))
    missing = tuple(sorted(expected.difference(ranks_found)))
    if missing and not allow_missing:
        preview = ", ".join(str(rank) for rank in missing[:12])
        suffix = "..." if len(missing) > 12 else ""
        raise DraftSheetError(
            f"Missing {len(missing)} expected rankings ({preview}{suffix}). "
            "Use --allow-missing only after reviewing the detected layout."
        )

    reader = PdfReader(str(source))
    if len(reader.pages) != len(inspections):
        raise DraftSheetError("PDF page counts differed between extraction and editing passes.")

    writer = PdfWriter(clone_from=str(source))
    for page_index, page in enumerate(writer.pages):
        inspection = inspections[page_index]
        overlay_stream = _make_overlay(
            inspection,
            teams=teams,
            style=chosen_style,
            remove_dollar_column=remove_dollar_column,
            draft_context_labels=draft_context_labels,
        )
        overlay = PdfReader(overlay_stream).pages[0]
        page.merge_page(overlay, over=True)

    metadata = {
        key: value
        for key, value in (reader.metadata or {}).items()
        if isinstance(key, str) and isinstance(value, str)
    }
    metadata["/Producer"] = "fantasy-football-2026 PDF round highlighter"
    subject = f"Projected {teams}-team draft rounds, ranks {minimum_rank}-{maximum_rank}"
    if remove_dollar_column:
        subject += ", salary values hidden"
    if draft_context_labels is not None:
        subject += (
            ", bye weeks replaced by depth chart, offense, line, schedule, and injury context"
        )
    metadata["/Subject"] = subject
    writer.add_metadata(metadata)

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    try:
        with temporary.open("wb") as output_file:
            writer.write(output_file)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)

    rounds_found = tuple(sorted({draft_round_for_rank(rank, teams) for rank in ranks_found}))
    return HighlightResult(
        output_path=destination,
        ranks_found=ranks_found,
        rounds_found=rounds_found,
        page_count=len(inspections),
        color=chosen_style.color.upper(),
        salary_values_removed=(
            sum(len(inspection.salary_values) for inspection in inspections)
            if remove_dollar_column
            else 0
        ),
        bye_week_values_replaced=(
            sum(
                value.rank in draft_context_labels
                for inspection in inspections
                for value in inspection.bye_week_values
            )
            if draft_context_labels is not None
            else 0
        ),
    )


def _build_column_layouts(rows: list[RankRow], page_width: float) -> tuple[ColumnLayout, ...]:
    if not rows:
        return ()

    clusters: list[list[RankRow]] = []
    for row in sorted(rows, key=lambda item: item.x1):
        matching = next(
            (
                cluster
                for cluster in clusters
                if abs(row.x1 - _median(item.x1 for item in cluster)) <= 8.0
            ),
            None,
        )
        if matching is None:
            clusters.append([row])
        else:
            matching.append(row)

    clusters.sort(key=lambda cluster: _median(row.x1 for row in cluster))
    left_edges = [min(row.x0 for row in cluster) - 1.5 for cluster in clusters]
    page_margin = max(5.0, left_edges[0])
    layouts: list[ColumnLayout] = []
    for index, cluster in enumerate(clusters):
        cluster = _longest_consecutive_run(cluster)
        x_start = left_edges[index]
        if index + 1 < len(clusters):
            x_end = left_edges[index + 1] - 5.0
        else:
            x_end = page_width - page_margin
        if x_end <= x_start:
            raise DraftSheetError("Detected ranking columns overlap; refusing to edit the PDF.")
        numbered_rows = tuple(
            sorted(
                (replace(row, column=index) for row in cluster),
                key=lambda item: (item.top, item.rank),
            )
        )
        layouts.append(ColumnLayout(index=index, x_start=x_start, x_end=x_end, rows=numbered_rows))
    return tuple(layouts)


def _longest_consecutive_run(rows: list[RankRow]) -> list[RankRow]:
    """Discard isolated numbered footer/header tokens aligned with a rank column."""

    ordered = sorted(rows, key=lambda item: (item.top, item.rank))
    runs: list[list[RankRow]] = []
    current: list[RankRow] = []
    for row in ordered:
        if current and row.rank != current[-1].rank + 1:
            runs.append(current)
            current = []
        current.append(row)
    if current:
        runs.append(current)
    return max(runs, key=len)


def _find_salary_values(
    words: list[dict[str, object]],
    ranked_rows: tuple[RankRow, ...],
) -> tuple[TextRegion, ...]:
    if not ranked_rows:
        return ()
    table_top = min(row.top for row in ranked_rows) - 1.0
    table_bottom = max(row.bottom for row in ranked_rows) + 1.0
    values: list[TextRegion] = []
    for word in words:
        if not SALARY_TOKEN.fullmatch(str(word["text"]).strip()):
            continue
        top = float(word["top"])
        bottom = float(word["bottom"])
        if top < table_top or bottom > table_bottom:
            continue
        values.append(
            TextRegion(
                x0=float(word["x0"]),
                x1=float(word["x1"]),
                top=top,
                bottom=bottom,
            )
        )
    return tuple(values)


def _find_bye_week_values(
    words: list[dict[str, object]],
    columns: tuple[ColumnLayout, ...],
) -> tuple[RankedTextRegion, ...]:
    """Locate the numeric bye-week value at the right edge of every ranking row."""

    values: list[RankedTextRegion] = []
    for column in columns:
        for row in column.rows:
            row_center = (row.top + row.bottom) / 2
            row_words = sorted(
                (
                    word
                    for word in words
                    if column.x_start <= float(word["x0"]) <= column.x_end
                    and abs(((float(word["top"]) + float(word["bottom"])) / 2) - row_center) <= 1.5
                ),
                key=lambda word: float(word["x0"]),
            )
            salary_index = next(
                (
                    index
                    for index, word in enumerate(row_words)
                    if SALARY_TOKEN.fullmatch(str(word["text"]).strip())
                ),
                None,
            )
            if salary_index is None:
                continue
            candidate = next(
                (
                    word
                    for word in row_words[salary_index + 1 :]
                    if re.fullmatch(r"\d{1,2}", str(word["text"]).strip())
                ),
                None,
            )
            if candidate is None:
                continue
            values.append(
                RankedTextRegion(
                    rank=row.rank,
                    x0=float(candidate["x0"]),
                    x1=float(candidate["x1"]),
                    top=float(candidate["top"]),
                    bottom=float(candidate["bottom"]),
                )
            )
    return tuple(values)


def _find_bye_week_legend(
    words: list[dict[str, object]],
    ranked_rows: tuple[RankRow, ...],
) -> tuple[TextRegion, ...]:
    """Locate the source sheet's footer example and `Bye week` caption."""

    if not ranked_rows:
        return ()
    table_bottom = max(row.bottom for row in ranked_rows)
    bye_word = next(
        (
            word
            for word in words
            if str(word["text"]).strip().lower() == "bye" and float(word["top"]) > table_bottom
        ),
        None,
    )
    if bye_word is None:
        return ()
    bye_center = (float(bye_word["x0"]) + float(bye_word["x1"])) / 2
    candidates = [
        word
        for word in words
        if float(word["top"]) > table_bottom
        and abs(((float(word["x0"]) + float(word["x1"])) / 2) - bye_center) <= 18.0
        and (
            str(word["text"]).strip().lower() in {"bye", "week"}
            or re.fullmatch(r"\d{1,2}", str(word["text"]).strip())
        )
    ]
    return tuple(
        TextRegion(
            x0=float(word["x0"]),
            x1=float(word["x1"]),
            top=float(word["top"]),
            bottom=float(word["bottom"]),
        )
        for word in candidates
    )


def _make_overlay(
    inspection: PageInspection,
    *,
    teams: int,
    style: HighlightStyle,
    remove_dollar_column: bool,
    draft_context_labels: Mapping[int, tuple[str, str, str, str, str]] | None,
) -> BytesIO:
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=(inspection.width, inspection.height), pageCompression=1)
    fill = _hex_color(style.color)
    divider = _darken(fill, 0.72)

    if remove_dollar_column:
        canvas.saveState()
        canvas.setFillColorRGB(1, 1, 1)
        for value in inspection.salary_values:
            padding = 0.7
            canvas.rect(
                value.x0 - padding,
                inspection.height - value.bottom - padding,
                (value.x1 - value.x0) + (padding * 2),
                (value.bottom - value.top) + (padding * 2),
                stroke=0,
                fill=1,
            )
        canvas.restoreState()

    if draft_context_labels is not None:
        _draw_draft_context(canvas, inspection, draft_context_labels)
        _draw_bucket_legend(canvas, inspection)

    for column in inspection.columns:
        by_round: dict[int, list[RankRow]] = defaultdict(list)
        for row in column.rows:
            by_round[draft_round_for_rank(row.rank, teams)].append(row)

        for round_number, round_rows in sorted(by_round.items()):
            top = min(row.top for row in round_rows) - 0.55
            bottom = max(row.bottom for row in round_rows) + 0.55
            y = inspection.height - bottom
            height = bottom - top
            opacity = style.primary_opacity if round_number % 2 else style.secondary_opacity

            if opacity > 0:
                canvas.saveState()
                canvas.setFillColor(fill)
                canvas.setFillAlpha(opacity)
                canvas.rect(
                    column.x_start,
                    y,
                    column.x_end - column.x_start,
                    height,
                    stroke=0,
                    fill=1,
                )
                canvas.restoreState()

            first_rank = ((round_number - 1) * teams) + 1
            if any(row.rank == first_rank for row in round_rows):
                anchor = next(row for row in round_rows if row.rank == first_rank)
                previous_rows = [row for row in column.rows if row.top < anchor.top]
                # A round that starts at the top of a printed column already has
                # the column header as its boundary. Drawing another divider there
                # leaves no inter-row gap and collides with the first player row.
                if not previous_rows:
                    continue
                previous = max(previous_rows, key=lambda row: row.top)
                separator_top = (previous.bottom + anchor.top) / 2
                line_y = inspection.height - separator_top
                label_x = (column.x_start + column.x_end) / 2
                label_gap = 9.0
                canvas.saveState()
                canvas.setStrokeColor(divider)
                canvas.setStrokeAlpha(style.divider_opacity)
                canvas.setLineWidth(0.7)
                canvas.line(
                    column.x_start + 2.0,
                    line_y,
                    label_x - label_gap,
                    line_y,
                )
                canvas.line(
                    label_x + label_gap,
                    line_y,
                    column.x_end - 2.0,
                    line_y,
                )
                canvas.restoreState()

                label = f"R{round_number}"
                label_y = line_y - 0.95
                canvas.saveState()
                canvas.setFillColorRGB(1, 1, 1)
                canvas.rect(
                    label_x - 8.0,
                    label_y - 0.5,
                    16.0,
                    3.2,
                    stroke=0,
                    fill=1,
                )
                canvas.setFillColor(divider)
                canvas.setFillAlpha(style.label_opacity)
                canvas.setFont("Helvetica-Bold", 2.7)
                canvas.drawCentredString(label_x, label_y, label)
                canvas.restoreState()

    canvas.showPage()
    canvas.save()
    buffer.seek(0)
    return buffer


def _draw_draft_context(
    canvas: Canvas,
    inspection: PageInspection,
    labels: Mapping[int, tuple[str, str, str, str, str]],
) -> None:
    """Draw depth chart, team, schedule, and injury context side by side."""

    columns = {column.index: column for column in inspection.columns}
    rows = {row.rank: row for row in inspection.rows}
    metric_font = _register_metric_font()
    canvas.saveState()
    canvas.setFillColorRGB(1, 1, 1)
    for value in inspection.bye_week_values:
        if value.rank not in labels:
            continue
        row = rows[value.rank]
        column = columns[row.column]
        left, right = _context_lane_bounds(inspection, column)
        canvas.rect(
            left,
            inspection.height - value.bottom - 0.7,
            right - left,
            (value.bottom - value.top) + 1.4,
            stroke=0,
            fill=1,
        )
    canvas.restoreState()

    canvas.saveState()
    canvas.setFillAlpha(1.0)
    for value in inspection.bye_week_values:
        context = labels.get(value.rank)
        if context is None:
            continue
        row = rows[value.rank]
        column = columns[row.column]
        left, right = _context_lane_bounds(inspection, column)
        centers = _context_column_centers(left, right)
        label_y = inspection.height - ((value.top + value.bottom) / 2) - 1.25
        for header, label, label_x in zip(
            ("DC", "OFF", "OL", "SOS", "INJ"), context, centers, strict=True
        ):
            normalized = str(label).strip().upper() or "--"
            font_size = (
                CONTEXT_RANGE_FONT_SIZE
                if header == "INJ" and len(normalized) > 2
                else CONTEXT_VALUE_FONT_SIZE
            )
            canvas.setFillColor(HexColor(BUCKET_COLORS[context_bucket(header, normalized)]))
            canvas.setFont(metric_font, font_size)
            canvas.drawCentredString(label_x, label_y, normalized)
    canvas.restoreState()

    first_row = min(inspection.rows, key=lambda row: row.top)
    header_y = inspection.height - first_row.top + 3.35
    canvas.saveState()
    canvas.setFillColorRGB(1, 1, 1)
    canvas.setFont(metric_font, CONTEXT_HEADER_FONT_SIZE)
    for column in inspection.columns:
        left, right = _context_lane_bounds(inspection, column)
        centers = _context_column_centers(left, right)
        for header, header_x in zip(("DC", "OFF", "OL", "SOS", "INJ"), centers, strict=True):
            canvas.drawCentredString(header_x, header_y, header)
    canvas.restoreState()

    if inspection.bye_week_legend:
        left = min(region.x0 for region in inspection.bye_week_legend) - 2.5
        right = max(region.x1 for region in inspection.bye_week_legend) + 2.5
        top = min(region.top for region in inspection.bye_week_legend) - 2.0
        bottom = max(region.bottom for region in inspection.bye_week_legend) + 1.0
        center = (left + right) / 2
        canvas.saveState()
        canvas.setFillColorRGB(1, 1, 1)
        canvas.rect(
            left,
            inspection.height - bottom,
            right - left,
            bottom - top,
            stroke=0,
            fill=1,
        )
        canvas.setFillColorRGB(0, 0, 0)
        canvas.setFont("Helvetica", 4.4)
        canvas.drawCentredString(center, inspection.height - top - 7.4, "RB1 3 14 22 0")
        canvas.drawCentredString(center, inspection.height - bottom + 0.8, "DC OFF OL SOS INJ")
        canvas.restoreState()


def _draw_bucket_legend(canvas: Canvas, inspection: PageInspection) -> None:
    """Draw a compact top-page index for rank and depth-chart color buckets."""

    x = 18.0
    heading_y = inspection.height - 29.0
    canvas.saveState()
    canvas.setFillColorRGB(0.05, 0.05, 0.45)
    canvas.setFont("Helvetica-Bold", 4.0)
    canvas.drawString(x, heading_y, "COLOR INDEX")

    items = (
        ("green", "GREEN 1-10 / DC1 / INJ0"),
        ("yellow", "YELLOW 11-22 / DC2 / INJ1-2"),
        ("red", "RED 23-32 / DC3+ / INJ3+"),
    )
    canvas.setFont("Helvetica-Bold", 3.5)
    for index, (bucket, label) in enumerate(items):
        item_y = heading_y - 6.0 - (index * 6.0)
        color = HexColor(BUCKET_COLORS[bucket])
        canvas.setFillColor(color)
        canvas.circle(x + 1.5, item_y + 1.2, 1.25, stroke=0, fill=1)
        canvas.drawString(x + 4.5, item_y, label)
    canvas.restoreState()


def _context_column_centers(left: float, right: float) -> tuple[float, float, float, float, float]:
    width = right - left
    return (
        left + (width * 0.17),
        left + (width * 0.42),
        left + (width * 0.57),
        left + (width * 0.72),
        left + (width * 0.91),
    )


def _context_lane_bounds(inspection: PageInspection, column: ColumnLayout) -> tuple[float, float]:
    salary_values = [
        value for value in inspection.salary_values if column.x_start <= value.x0 <= column.x_end
    ]
    bye_values = [
        value for value in inspection.bye_week_values if column.x_start <= value.x0 <= column.x_end
    ]
    if not salary_values or not bye_values:
        raise DraftSheetError(f"Could not determine context lane for column {column.index}.")
    return (
        min(value.x0 for value in salary_values) - CONTEXT_LANE_LEFT_PADDING,
        max(value.x1 for value in bye_values) + 1.0,
    )


def _salary_region_for_row(
    inspection: PageInspection,
    column: ColumnLayout,
    row: RankRow,
) -> TextRegion | None:
    row_center = (row.top + row.bottom) / 2
    candidates = [
        value
        for value in inspection.salary_values
        if column.x_start <= value.x0 <= column.x_end
        and abs(((value.top + value.bottom) / 2) - row_center) <= 1.5
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda value: abs(((value.top + value.bottom) / 2) - row_center))


def _hex_color(value: str) -> Color:
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
        raise DraftSheetError(f"Color must use #RRGGBB notation, got {value!r}.")
    return HexColor(value)


def _darken(color: Color, factor: float) -> Color:
    return Color(color.red * factor, color.green * factor, color.blue * factor)


def _median(values: Iterable[float]) -> float:
    ordered = sorted(float(value) for value in values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2
