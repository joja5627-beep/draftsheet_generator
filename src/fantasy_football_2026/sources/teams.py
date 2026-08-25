"""Refresh automated team offense and offensive-line rankings."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from fantasy_football_2026.constants import (
    DEFAULT_TIMEOUT_SECONDS,
    TEAM_NAMES,
    ContextFile,
    DirectoryName,
    SourceUrl,
)
from fantasy_football_2026.errors import FantasyFootballError, InjuryContextError
from fantasy_football_2026.infrastructure.storage import write_json, write_text
from fantasy_football_2026.infrastructure.web import CachedWebClient, CachePolicy

FIRST_DOWN_URL = SourceUrl.FIRST_DOWN_TOTALS
SHARP_URL = SourceUrl.SHARP_OFFENSIVE_LINE
SHARP_READER_URL = SourceUrl.JINA_HTTP_READER.format(host_path=SHARP_URL.removeprefix("https://"))


@dataclass(frozen=True, slots=True)
class TextFetch:
    text: str
    retrieved_at: str
    from_cache: bool
    fetch_url: str


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self.rows: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._cell is not None:
            assert self._row is not None
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Refresh automated NFL team projections.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(DirectoryName.CONTEXT, ContextFile.TEAM_PROJECTIONS_MARKDOWN),
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=Path(DirectoryName.CONTEXT, ContextFile.TEAM_PROJECTIONS_JSON),
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path(DirectoryName.CONTEXT, DirectoryName.CACHE),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--refresh", action="store_true")
    mode.add_argument("--offline", action="store_true")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = update_team_context(
        markdown_path=args.output,
        json_path=args.json_output,
        cache_dir=args.cache_dir,
        refresh=args.refresh,
        offline=args.offline,
        timeout=args.timeout,
    )
    print(f"NFL teams: {result['team_count']}")
    print(f"JSON: {Path(result['json_path']).resolve()}")
    return 0


def update_team_context(
    *,
    markdown_path: Path,
    json_path: Path,
    cache_dir: Path,
    refresh: bool,
    offline: bool,
    timeout: float,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    offense_fetch = _fetch_text(
        name="firstdown_implied_totals",
        url=FIRST_DOWN_URL,
        cache_path=cache_dir / "firstdown_implied_totals.html",
        refresh=refresh,
        offline=offline,
        timeout=timeout,
        now=now,
    )
    line_fetch = _fetch_text(
        name="sharp_offensive_line",
        url=SHARP_READER_URL,
        cache_path=cache_dir / "sharp_offensive_line.md",
        refresh=refresh,
        offline=offline,
        timeout=timeout,
        now=now,
    )
    offenses = parse_first_down_totals(offense_fetch.text)
    lines = parse_sharp_offensive_lines(line_fetch.text)
    if set(offenses) != set(TEAM_NAMES) or set(lines) != set(TEAM_NAMES):
        missing_offense = sorted(set(TEAM_NAMES) - set(offenses))
        missing_line = sorted(set(TEAM_NAMES) - set(lines))
        raise InjuryContextError(
            "Automated team sources did not cover all 32 teams: "
            f"offense missing={missing_offense}, line missing={missing_line}."
        )

    effective_date = _first_down_effective_date(offense_fetch.text, now.year)
    metadata = {
        "generated_at": now.isoformat(timespec="seconds"),
        "effective_date": effective_date,
        "automation_policy": (
            "Ranks are parsed on every live refresh; no hand-entered team ranks are used."
        ),
        "offense_method": "Rank by season-long average implied points from Vegas lines.",
        "offense_source": FIRST_DOWN_URL,
        "offensive_line_method": "Sharp Football forward-looking staff ranking.",
        "offensive_line_source": SHARP_URL,
        "source_retrieval": {
            "offense": {
                "retrieved_at": offense_fetch.retrieved_at,
                "from_cache": offense_fetch.from_cache,
                "fetch_url": offense_fetch.fetch_url,
            },
            "offensive_line": {
                "retrieved_at": line_fetch.retrieved_at,
                "from_cache": line_fetch.from_cache,
                "fetch_url": line_fetch.fetch_url,
                "canonical_url": SHARP_URL,
            },
        },
    }
    teams = {
        team: {
            "offense_rank": offenses[team][0],
            "offense_average_points": offenses[team][1],
            "offensive_line_rank": lines[team][0],
            "offensive_line_score": lines[team][1],
        }
        for team in sorted(TEAM_NAMES)
    }
    write_json(json_path, {"metadata": metadata, "teams": teams})
    write_text(markdown_path, render_markdown(metadata, teams))
    return {
        "team_count": len(teams),
        "offense_from_cache": offense_fetch.from_cache,
        "offensive_line_from_cache": line_fetch.from_cache,
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
    }


def parse_first_down_totals(html: str) -> dict[str, tuple[int, float]]:
    parser = _TableParser()
    parser.feed(html)
    results: dict[str, tuple[int, float]] = {}
    for row in parser.rows:
        if len(row) < 3 or not row[0].isdigit():
            continue
        team = _team_code(row[1])
        if team is None:
            continue
        results[team] = (int(row[0]), float(row[2]))
    if len(results) != 32:
        raise InjuryContextError(f"Expected 32 First Down teams, parsed {len(results)}.")
    return results


def parse_sharp_offensive_lines(text: str) -> dict[str, tuple[int, int]]:
    results: dict[str, tuple[int, int]] = {}
    pattern = re.compile(r"^\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*(\d+)\s*\|\s*$", re.M)
    for rank, name, score in pattern.findall(text):
        team = _team_code(name)
        if team is not None:
            results[team] = (int(rank), int(score))
    if len(results) != 32:
        raise InjuryContextError(f"Expected 32 Sharp teams, parsed {len(results)}.")
    return results


def render_markdown(metadata: dict[str, Any], teams: dict[str, dict[str, Any]]) -> str:
    lines = [
        "# Automated 2026 team projections",
        "",
        f"**Generated:** `{metadata['generated_at']}`",
        f"**Effective date:** `{metadata['effective_date']}`",
        "",
        metadata["automation_policy"],
        "",
        f"OFF: [{metadata['offense_method']}]({metadata['offense_source']})",
        f"OL: [{metadata['offensive_line_method']}]({metadata['offensive_line_source']})",
        "",
        "| Team | OFF rank | Avg pts | OL rank | OL score |",
        "|---|---:|---:|---:|---:|",
    ]
    for team, values in sorted(teams.items(), key=lambda item: item[1]["offense_rank"]):
        lines.append(
            f"| {team} | {values['offense_rank']} | "
            f"{values['offense_average_points']:.1f} | "
            f"{values['offensive_line_rank']} | {values['offensive_line_score']} |"
        )
    lines.append("")
    return "\n".join(lines)


def _fetch_text(
    *,
    name: str,
    url: str,
    cache_path: Path,
    refresh: bool,
    offline: bool,
    timeout: float,
    now: datetime,
) -> TextFetch:
    try:
        result = CachedWebClient(
            CachePolicy(
                refresh=refresh,
                offline=offline,
                timeout=timeout,
                stale_if_error=True,
            ),
            now=lambda: now,
        ).fetch_text(
            name=name,
            url=url,
            cache_path=cache_path,
            accept="text/html,text/markdown;q=0.9,*/*;q=0.8",
        )
    except FantasyFootballError as error:
        raise InjuryContextError(str(error)) from error
    return TextFetch(result.payload, result.retrieved_at, result.from_cache, result.url)


def _team_code(value: str) -> str | None:
    normalized = re.sub(r"[^a-z0-9]+", "", value.lower())
    aliases = sorted(
        (
            (re.sub(r"[^a-z0-9]+", "", alias.lower()), team)
            for team, names in TEAM_NAMES.items()
            for alias in names
        ),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    return next((team for alias, team in aliases if normalized.endswith(alias)), None)


def _first_down_effective_date(text: str, year: int) -> str:
    match = re.search(r"Updated:\s*(\d{1,2})/(\d{1,2})", text)
    if not match:
        return datetime.now(UTC).date().isoformat()
    month, day = (int(value) for value in match.groups())
    return f"{year:04d}-{month:02d}-{day:02d}"


if __name__ == "__main__":
    raise SystemExit(main())
