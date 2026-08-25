"""Tools for preparing fantasy-football draft PDFs."""

from importlib.metadata import PackageNotFoundError, version

from fantasy_football_2026.presentation.pdf import HighlightResult, highlight_draft_rounds

__all__ = ["HighlightResult", "highlight_draft_rounds"]

try:
    __version__ = version("fantasy-football-2026")
except PackageNotFoundError:  # pragma: no cover - only an unpackaged source tree
    __version__ = "0+unknown"
