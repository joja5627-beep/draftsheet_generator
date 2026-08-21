"""Build position-specific 2026 fantasy strength-of-schedule context."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fantasy_football_2026.injury_context import InjuryContextError, _write_json, _write_text

SOURCE_URL = "https://draftcall.io/strength-of-schedule/"
CROSS_CHECK_URL = "https://www.rankfantasy.com/strength-of-schedule"
CROSS_CHECK_URLS = [
    CROSS_CHECK_URL,
    "https://www.fantasypros.com/nfl/strength-of-schedule.php",
    "https://www.fftoolbox.com/football/strength_of_schedule.cfm",
]
POSITION_HEADINGS = {
    "quarterback sos": "QB",
    "running back sos": "RB",
    "wide receiver sos": "WR",
    "tight end sos": "TE",
    "kicker sos": "K",
    "defense sos": "DEF",
}
TEAM_ABBREVIATIONS = {
    "Arizona Cardinals": "ARI",
    "Atlanta Falcons": "ATL",
    "Baltimore Ravens": "BAL",
    "Buffalo Bills": "BUF",
    "Carolina Panthers": "CAR",
    "Chicago Bears": "CHI",
    "Cincinnati Bengals": "CIN",
    "Cleveland Browns": "CLE",
    "Dallas Cowboys": "DAL",
    "Denver Broncos": "DEN",
    "Detroit Lions": "DET",
    "Green Bay Packers": "GB",
    "Houston Texans": "HOU",
    "Indianapolis Colts": "IND",
    "Jacksonville Jaguars": "JAC",
    "Kansas City Chiefs": "KC",
    "Las Vegas Raiders": "LV",
    "Los Angeles Chargers": "LAC",
    "Los Angeles Rams": "LAR",
    "Miami Dolphins": "MIA",
    "Minnesota Vikings": "MIN",
    "New England Patriots": "NE",
    "New Orleans Saints": "NO",
    "New York Giants": "NYG",
    "New York Jets": "NYJ",
    "Philadelphia Eagles": "PHI",
    "Pittsburgh Steelers": "PIT",
    "San Francisco 49ers": "SF",
    "Seattle Seahawks": "SEA",
    "Tampa Bay Buccaneers": "TB",
    "Tennessee Titans": "TEN",
    "Washington Commanders": "WAS",
}


@dataclass(frozen=True, slots=True)
class ScheduleMetric:
    season_average: float
    season_rank: int
    playoff_average: float
    playoff_rank: int


class _ScheduleTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.current_position: str | None = None
        self._in_heading = False
        self._heading_parts: list[str] = []
        self._in_cell = False
        self._cell_parts: list[str] = []
        self._row: list[str] | None = None
        self.rows: list[tuple[str, list[str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag == "h2":
            self._in_heading = True
            self._heading_parts = []
        elif tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._in_cell = True
            self._cell_parts = []

    def handle_data(self, data: str) -> None:
        if self._in_heading:
            self._heading_parts.append(data)
        if self._in_cell:
            self._cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "h2":
            heading = " ".join("".join(self._heading_parts).split()).lower()
            self.current_position = POSITION_HEADINGS.get(heading)
            self._in_heading = False
        elif tag in {"td", "th"} and self._in_cell and self._row is not None:
            self._row.append(" ".join("".join(self._cell_parts).split()))
            self._in_cell = False
        elif tag == "tr" and self._row is not None:
            if self.current_position and len(self._row) == 6 and self._row[0].isdigit():
                self.rows.append((self.current_position, self._row))
            self._row = None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build position-specific 2026 fantasy strength-of-schedule context."
    )
    parser.add_argument(
        "--output", type=Path, default=Path("context/strength_of_schedule.md")
    )
    parser.add_argument(
        "--json-output", type=Path, default=Path("context/strength_of_schedule.json")
    )
    parser.add_argument(
        "--cache", type=Path, default=Path("context/cache/draftcall_strength_of_schedule.html")
    )
    parser.add_argument("--refresh", action="store_true", help="refresh the source page")
    parser.add_argument("--offline", action="store_true", help="require cached source data")
    parser.add_argument("--timeout", type=float, default=45.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = update_schedule_context(
            markdown_path=args.output,
            json_path=args.json_output,
            cache_path=args.cache,
            refresh=args.refresh,
            offline=args.offline,
            timeout=args.timeout,
        )
    except (InjuryContextError, OSError, ValueError) as error:
        raise SystemExit(f"error: {error}") from error
    print(f"Team-position metrics: {result['metric_count']}")
    print(f"Markdown: {Path(result['markdown_path']).resolve()}")
    print(f"JSON: {Path(result['json_path']).resolve()}")
    return 0


def update_schedule_context(
    *,
    markdown_path: Path,
    json_path: Path,
    cache_path: Path,
    refresh: bool,
    offline: bool,
    timeout: float,
) -> dict[str, Any]:
    html, from_cache, retrieved_at = _fetch_html(
        cache_path=cache_path,
        refresh=refresh,
        offline=offline,
        timeout=timeout,
    )
    schedules = parse_schedule_html(html)
    now = datetime.now(UTC)
    source_label = _source_refresh_label(html)
    metadata = {
        "generated_at": now.isoformat(timespec="seconds"),
        "effective_date": now.date().isoformat(),
        "source": "DraftCall 2026 Strength of Schedule",
        "source_url": SOURCE_URL,
        "source_page_label": source_label,
        "source_retrieved_at": retrieved_at,
        "source_from_cache": from_cache,
        "cross_checks": CROSS_CHECK_URLS,
        "column_validation": "context/column_validation.json",
        "method": (
            "For each team and fantasy position, average the fantasy points per game "
            "allowed by its 2026 opponents in 2025. Season rank 1 is easiest and 32 hardest."
        ),
        "positions": ["QB", "RB", "WR", "TE", "K", "DEF"],
        "scope": "Full 2026 regular season; playoff fields cover Weeks 14-17.",
        "caveat": (
            "This is a prior-season, position-specific opponent measure. Defensive personnel "
            "and schemes can change, so use it as a modest tiebreaker rather than a projection."
        ),
    }
    payload = {
        "metadata": metadata,
        "teams": {
            team: {position: asdict(metric) for position, metric in positions.items()}
            for team, positions in sorted(schedules.items())
        },
    }
    _write_json(json_path, payload)
    _write_text(markdown_path, render_markdown(metadata, schedules))
    return {
        "metric_count": sum(len(positions) for positions in schedules.values()),
        "markdown_path": str(markdown_path),
        "json_path": str(json_path),
    }


def parse_schedule_html(html: str) -> dict[str, dict[str, ScheduleMetric]]:
    parser = _ScheduleTableParser()
    parser.feed(html)
    schedules: dict[str, dict[str, ScheduleMetric]] = {}
    for position, row in parser.rows:
        _, team_name, season_average, season_rank, playoff_average, playoff_rank = row
        team = TEAM_ABBREVIATIONS.get(team_name)
        if team is None:
            raise InjuryContextError(
                f"Unknown NFL team in strength-of-schedule source: {team_name}"
            )
        schedules.setdefault(team, {})[position] = ScheduleMetric(
            season_average=float(season_average),
            season_rank=int(season_rank),
            playoff_average=float(playoff_average),
            playoff_rank=int(playoff_rank),
        )
    expected_positions = set(POSITION_HEADINGS.values())
    if len(schedules) != 32:
        raise InjuryContextError(
            f"Expected strength-of-schedule data for 32 teams, found {len(schedules)}."
        )
    for team, positions in schedules.items():
        if set(positions) != expected_positions:
            missing = ", ".join(sorted(expected_positions - set(positions)))
            raise InjuryContextError(f"Missing {missing or 'unknown'} schedule data for {team}.")
    for position in expected_positions:
        ranks = {positions[position].season_rank for positions in schedules.values()}
        if ranks != set(range(1, 33)):
            raise InjuryContextError(f"Invalid or duplicate full-season {position} SOS ranks.")
    return schedules


def load_schedule_ranks(path: Path) -> dict[str, dict[str, int]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        schedules = {
            str(team): {
                str(position): int(metric["season_rank"])
                for position, metric in positions.items()
            }
            for team, positions in payload["teams"].items()
        }
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise InjuryContextError(
            f"Could not load strength-of-schedule context {path}: {error}"
        ) from error
    if len(schedules) != 32 or any(len(positions) != 6 for positions in schedules.values()):
        raise InjuryContextError(f"Expected six position ranks for 32 NFL teams in {path}.")
    return schedules


def render_markdown(
    metadata: dict[str, Any], schedules: dict[str, dict[str, ScheduleMetric]]
) -> str:
    positions = ("QB", "RB", "WR", "TE", "K", "DEF")
    lines = [
        "# 2026 position-specific fantasy strength of schedule",
        "",
        f"Generated: `{metadata['generated_at']}`",
        f"Source retrieved: `{metadata['source_retrieved_at']}`",
        f"Source: [DraftCall 2026 Strength of Schedule]({metadata['source_url']})",
        (
            "Independent cross-checks: "
            f"[RankFantasy]({metadata['cross_checks'][0]}), "
            f"[FantasyPros]({metadata['cross_checks'][1]}), and "
            f"[FFToolbox]({metadata['cross_checks'][2]})"
        ),
        "Cross-source audit: [Column validation](./column_validation.md)",
        "",
        f"**Interpretation:** {metadata['method']}",
        "",
        f"> {metadata['caveat']}",
        "",
        "The PDF uses each player's team and fantasy position to select the `SOS` rank. "
        "D/ST uses `DEF`. The raw full-season averages and Weeks 14-17 playoff values remain "
        "available in `strength_of_schedule.json` for later reweighting.",
        "",
        "| Team | " + " | ".join(positions) + " |",
        "| :---: | " + " | ".join("---:" for _ in positions) + " |",
    ]
    for team, metrics in sorted(schedules.items()):
        ranks = " | ".join(str(metrics[position].season_rank) for position in positions)
        lines.append(f"| {team} | {ranks} |")
    lines.extend(
        [
            "",
            "## Method and limitations",
            "",
            (
                "DraftCall describes its full-season score as the average fantasy PPG allowed "
                "in 2025 by the defenses on each team's 2026 schedule; higher raw averages are "
                "easier. RankFantasy independently publishes the same 1-easiest to 32-hardest "
                "position-specific convention for QB, RB, WR, and TE and explicitly excludes "
                "bye weeks from its average. Small rank differences should not be over-weighted."
            ),
            "",
            (
                "Kicker and defense ranks are retained from DraftCall because the cross-check "
                "does not publish those two tables. The source page says it may update as games "
                "are played; rerun the updater before later draft or in-season use."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def _fetch_html(
    *, cache_path: Path, refresh: bool, offline: bool, timeout: float
) -> tuple[str, bool, str]:
    if offline:
        if not cache_path.is_file():
            raise InjuryContextError(f"Offline schedule cache does not exist: {cache_path}")
        retrieved_at = datetime.fromtimestamp(cache_path.stat().st_mtime, UTC).isoformat(
            timespec="seconds"
        )
        return cache_path.read_text(encoding="utf-8"), True, retrieved_at
    if cache_path.is_file() and not refresh:
        retrieved_at = datetime.fromtimestamp(cache_path.stat().st_mtime, UTC).isoformat(
            timespec="seconds"
        )
        return cache_path.read_text(encoding="utf-8"), True, retrieved_at

    request = Request(
        SOURCE_URL,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": "fantasy-football-2026-context/0.1",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310
            html = response.read().decode("utf-8")
    except (HTTPError, URLError, TimeoutError, UnicodeDecodeError) as error:
        raise InjuryContextError(
            f"Could not refresh strength-of-schedule source: {error}"
        ) from error
    _write_text(cache_path, html)
    return html, False, datetime.now(UTC).isoformat(timespec="seconds")


def _source_refresh_label(html: str) -> str | None:
    match = re.search(r"Refreshed\s+([A-Z][a-z]+\s+\d{1,2},\s+2026)", html)
    return match.group(1) if match else None


if __name__ == "__main__":
    raise SystemExit(main())
