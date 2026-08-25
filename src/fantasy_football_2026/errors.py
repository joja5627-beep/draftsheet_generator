"""Application exception hierarchy."""


class FantasyFootballError(RuntimeError):
    """Base class for recoverable application failures."""


class ContextError(FantasyFootballError):
    """Raised when a context source cannot be read, refreshed, or validated safely."""


class InjuryContextError(ContextError):
    """Backward-compatible context-build error used by pipeline feature modules."""


class StorageError(FantasyFootballError):
    """Raised when a persisted artifact cannot be decoded or written safely."""


class PipelineError(FantasyFootballError):
    """Raised when pipeline structure or output invariants are invalid."""


class DraftSheetError(FantasyFootballError, ValueError):
    """Raised when a draft-sheet PDF cannot be parsed or rendered safely."""
