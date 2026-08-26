"""Stable application identifiers, artifact names, source URLs, and domain constants."""

from __future__ import annotations

from typing import Final

APPLICATION_NAME: Final = "fantasy-football-2026"
DEFAULT_TIMEOUT_SECONDS: Final = 45.0
DEFAULT_LEAGUE_TEAMS: Final = 12
TOTAL_RANKED_PLAYERS: Final = 300
NFL_TEAM_COUNT: Final = 32
DEFAULT_SOURCE_PDF: Final = "NFL26_CS_PPR300.pdf"
HTTP_USER_AGENT: Final = "Mozilla/5.0 fantasy-football-2026-context/0.3"
JSON_USER_AGENT: Final = "curl/8.7.1 fantasy-football-2026-context/0.3"


class DirectoryName:
    """Project-relative directory names used by the build graph."""

    CONTEXT: Final = "context"
    CACHE: Final = "cache"
    OUTPUT: Final = "output"
    PDF: Final = "pdf"
    CHEAT_SHEET: Final = "cheat_sheet"
    TEMPORARY: Final = "tmp"


class ContextFile:
    """Canonical context artifact filenames."""

    BUILD_MANIFEST_JSON: Final = "build_manifest.json"
    COLUMN_VALIDATION_JSON: Final = "column_validation.json"
    COLUMN_VALIDATION_MARKDOWN: Final = "column_validation.md"
    CONTEXT_VALIDATION_JSON: Final = "context_validation.json"
    DRAFT_CONTEXT_JSON: Final = "draft_context.json"
    DRAFT_CONTEXT_MARKDOWN: Final = "draft_context.md"
    GEMINI_RESEARCH_MARKDOWN: Final = "gemini_research.md"
    HANDCUFF_CONSENSUS_JSON: Final = "handcuff_consensus.json"
    HANDCUFF_CONSENSUS_MARKDOWN: Final = "handcuff_consensus.md"
    HANDCUFF_SOURCES_JSON: Final = "handcuff_sources.json"
    INJURIES_JSON: Final = "player_injuries.json"
    INJURIES_MARKDOWN: Final = "player_injuries.md"
    LEAGUE_SCORING: Final = "broncon24_league_scoring.txt"
    MARKET_JSON: Final = "market_context.json"
    MARKET_MARKDOWN: Final = "market_context.md"
    MODEL_JSON: Final = "ranking_model.json"
    PLAYER_DEPTH_JSON: Final = "player_depth_charts.json"
    PLAYER_DEPTH_MARKDOWN: Final = "player_depth_charts.md"
    PROJECTIONS_JSON: Final = "projection_context.json"
    PROJECTIONS_MARKDOWN: Final = "projection_context.md"
    REWEIGHTED_JSON: Final = "reweighted_cheat_sheet.json"
    REWEIGHTED_MARKDOWN: Final = "reweighted_cheat_sheet.md"
    SCHEDULE_JSON: Final = "strength_of_schedule.json"
    SCHEDULE_MARKDOWN: Final = "strength_of_schedule.md"
    SLEEPER_CONSENSUS_JSON: Final = "sleeper_consensus.json"
    SLEEPER_CONSENSUS_MARKDOWN: Final = "sleeper_consensus.md"
    SLEEPER_SOURCES_JSON: Final = "sleeper_sources.json"
    SOURCE_AUDIT_JSON: Final = "source_audit.json"
    SOURCE_AUDIT_MARKDOWN: Final = "source_audit.md"
    TEAM_PROJECTIONS_JSON: Final = "team_projections.json"
    TEAM_PROJECTIONS_MARKDOWN: Final = "team_projections.md"


class OutputFile:
    """Stable names for user-facing generated artifacts."""

    REWEIGHTED_CSV: Final = "reweighted_cheat_sheet.csv"
    REWEIGHTED_PDF: Final = "fantasy-football-2026-reweighted-cheat-sheet.pdf"


class CacheName:
    """Cache keys and subdirectory names."""

    HANDCUFF_SOURCES: Final = "handcuff_sources"
    PROJECTIONS: Final = "projections"
    SLEEPER_PLAYERS_JSON: Final = "sleeper_players.json"
    SLEEPER_SOURCES: Final = "sleeper_sources"
    SCHEDULE_HTML: Final = "draftcall_strength_of_schedule.html"


class StageName:
    """Stable pipeline stage identifiers."""

    TEAM_PROJECTIONS: Final = "team-projections"
    SCHEDULE: Final = "schedule"
    INJURIES: Final = "injuries"
    MARKET: Final = "market"
    PROJECTIONS: Final = "projections"
    DEPTH_CHARTS: Final = "depth-charts"
    SLEEPER_CONSENSUS: Final = "sleeper-consensus"
    HANDCUFF_CONSENSUS: Final = "handcuff-consensus"
    UNIFIED_CONTEXT: Final = "unified-context"
    SOURCE_ORDER_PDF: Final = "source-order-pdf"
    RANKINGS: Final = "rankings"
    VALIDATION: Final = "validation"


class SourceUrl:
    """Machine-readable data endpoints and human-readable source pages."""

    SLEEPER_PLAYERS: Final = "https://api.sleeper.app/v1/players/nfl?active=true"
    SLEEPER_STATE: Final = "https://api.sleeper.app/v1/state/nfl"
    ESPN_INJURIES: Final = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries"
    ESPN_INJURY_PAGE: Final = "https://www.espn.com/nfl/injuries"
    ESPN_SCOREBOARD: Final = (
        "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
        "?dates={year}&limit=1000"
    )
    ESPN_DEPTH_CHART: Final = (
        "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{team}/depthcharts"
    )
    ESPN_TOP_300: Final = (
        "https://g.espncdn.com/s/ffldraftkit/26/NFL26_CS_PPR300.pdf?adddata=2026CS_PPR300"
    )
    ESPN_CLAY_PROJECTIONS: Final = (
        "https://g.espncdn.com/s/ffldraftkit/26/NFLDK2026_CS_ClayProjections2026.pdf"
    )
    FANTASYPROS_HALF_PPR: Final = (
        "https://www.fantasypros.com/nfl/rankings/half-point-ppr-cheatsheets.php"
    )
    FFTODAY_HALF_PPR: Final = "https://www.fftoday.com/rankings/26-adp-half-ppr.html"
    FANTASY_FOOTBALL_CALCULATOR_HALF_PPR: Final = (
        "https://fantasyfootballcalculator.com/rankings/half-ppr"
    )
    LINEUPBEAT_HALF_PPR: Final = "https://lineupbeat.com/nfl/rankings/"
    PRO_FOOTBALL_MANIA_HALF_PPR: Final = "https://profootballmania.com/fantasy-football-rankings/"
    ROTOBALLER_HALF_PPR: Final = (
        "https://www.rotoballer.com/fantasy-football-draft-rankings-august-updates-2026/1905031"
    )
    FFTODAY_PROJECTIONS: Final = (
        "https://www.fftoday.com/rankings/playerproj.php?Season=2026&PosID={position_id}&LeagueID=1"
    )
    FIRST_DOWN_TOTALS: Final = "https://www.firstdown.studio/implied-totals/season"
    SHARP_OFFENSIVE_LINE: Final = (
        "https://www.sharpfootballanalysis.com/analysis/best-nfl-offensive-line-rankings/"
    )
    JINA_HTTP_READER: Final = "https://r.jina.ai/http://{host_path}"
    DRAFTCALL_SCHEDULE: Final = "https://draftcall.io/strength-of-schedule/"
    RANKFANTASY_SCHEDULE: Final = "https://www.rankfantasy.com/strength-of-schedule"
    FANTASYPROS_SCHEDULE: Final = "https://www.fantasypros.com/nfl/strength-of-schedule.php"
    FFTOOLBOX_SCHEDULE: Final = "https://www.fftoolbox.com/football/strength_of_schedule.cfm"


SKILL_POSITIONS: Final = ("QB", "RB", "WR", "TE")
FLEX_POSITIONS: Final = ("RB", "WR", "TE")
FFTODAY_POSITION_IDS: Final = {"QB": 10, "RB": 20, "WR": 30, "TE": 40}

PLAYER_NAME_ALIASES: Final = {
    "chig okonkwo": "chigoziem okonkwo",
    "kenny gainwell": "kenneth gainwell",
}

TEAM_CODE_ALIASES: Final = {
    "ARZ": "ARI",
    "JAX": "JAC",
    "WSH": "WAS",
    "LA": "LAR",
    "STL": "LAR",
    "SD": "LAC",
    "OAK": "LV",
}

PLAYER_SUFFIXES: Final = frozenset({"jr", "sr", "ii", "iii", "iv", "v"})
RESERVE_STATUSES: Final = frozenset({"ir", "injured reserve", "reserve/injured", "pup", "nfi"})
INJURY_REWEIGHTING_START: Final = "<!-- BEGIN GENERATED INJURY REWEIGHTING -->"
INJURY_REWEIGHTING_END: Final = "<!-- END GENERATED INJURY REWEIGHTING -->"

INJURY_SOURCE_LINKS: Final = {
    "Sleeper player API": "https://docs.sleeper.com/#players",
    "Sleeper status behavior": (
        "https://support.sleeper.com/en/articles/3570017-injury-statuses-and-ir-eligibility"
    ),
    "ESPN injury report": "https://www.espn.com/nfl/injuries",
    "Official NFL injury report": "https://www.nfl.com/injuries/",
    "NFL reporting calendar": (
        "https://www.nfl.com/news/2026-27-national-football-league-important-dates"
    ),
    "NFL reserve-list explanation": (
        "https://www.nfl.com/news/"
        "nfl-training-camp-roster-faqs-defining-injured-reserve-pup-list-nfi-and-more"
    ),
    "Draft Sharks model pattern": "https://www.draftsharks.com/injury-predictor/about",
    "Sports Info Solutions model pattern": (
        "https://www.sportsinfosolutions.com/2025/09/10/"
        "introducing-our-multi-year-injury-risk-model/"
    ),
}

TEAM_NAMES: Final = {
    "ARI": ("Arizona Cardinals", "Cardinals"),
    "ATL": ("Atlanta Falcons", "Falcons"),
    "BAL": ("Baltimore Ravens", "Ravens"),
    "BUF": ("Buffalo Bills", "Bills"),
    "CAR": ("Carolina Panthers", "Panthers"),
    "CHI": ("Chicago Bears", "Bears"),
    "CIN": ("Cincinnati Bengals", "Bengals"),
    "CLE": ("Cleveland Browns", "Browns"),
    "DAL": ("Dallas Cowboys", "Cowboys"),
    "DEN": ("Denver Broncos", "Broncos"),
    "DET": ("Detroit Lions", "Lions"),
    "GB": ("Green Bay Packers", "Packers"),
    "HOU": ("Houston Texans", "Texans"),
    "IND": ("Indianapolis Colts", "Colts"),
    "JAC": ("Jacksonville Jaguars", "Jaguars"),
    "KC": ("Kansas City Chiefs", "Chiefs"),
    "LAC": ("Los Angeles Chargers", "Chargers"),
    "LAR": ("Los Angeles Rams", "Rams"),
    "LV": ("Las Vegas Raiders", "Raiders"),
    "MIA": ("Miami Dolphins", "Dolphins"),
    "MIN": ("Minnesota Vikings", "Vikings"),
    "NE": ("New England Patriots", "Patriots"),
    "NO": ("New Orleans Saints", "Saints"),
    "NYG": ("New York Giants", "Giants"),
    "NYJ": ("New York Jets", "Jets"),
    "PHI": ("Philadelphia Eagles", "Eagles"),
    "PIT": ("Pittsburgh Steelers", "Steelers"),
    "SEA": ("Seattle Seahawks", "Seahawks"),
    "SF": ("San Francisco 49ers", "49ers"),
    "TB": ("Tampa Bay Buccaneers", "Buccaneers"),
    "TEN": ("Tennessee Titans", "Titans"),
    "WAS": ("Washington Commanders", "Commanders"),
}

TEAM_ABBREVIATIONS: Final = {names[0]: team for team, names in TEAM_NAMES.items()}

SLEEPER_HIGHLIGHT_COLOR: Final = "#FFF1A8"
HANDCUFF_HIGHLIGHT_COLOR: Final = "#E5D8F5"
ROUND_LINE_COLOR: Final = "#75AADB"
