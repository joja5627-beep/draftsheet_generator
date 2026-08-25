"""Build the single normalized player context consumed by draft-sheet outputs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fantasy_football_2026.domain.normalization import normalize_name, normalize_team
from fantasy_football_2026.errors import InjuryContextError, StorageError
from fantasy_football_2026.infrastructure.storage import load_json_object, write_json, write_text


@dataclass(frozen=True, slots=True)
class DraftContextInputs:
    market: Path
    depth: Path
    injury: Path
    sleepers: Path


@dataclass(frozen=True, slots=True)
class MarketSignals:
    espn_rank: int | None
    fantasypros_rank: int | None
    fftoday_adp: float | None
    consensus_rank: float | None
    source_count: int | None
    match_quality: str | None

    @classmethod
    def from_source(cls, player: dict[str, Any]) -> MarketSignals:
        return cls(
            espn_rank=player.get("espn_rank"),
            fantasypros_rank=player.get("fantasypros_rank"),
            fftoday_adp=player.get("fftoday_adp"),
            consensus_rank=player.get("consensus_rank"),
            source_count=player.get("source_count"),
            match_quality=player.get("match_quality"),
        )


@dataclass(frozen=True, slots=True)
class OpportunitySignals:
    depth_chart_slot: str | None
    depth_chart_order: int | None
    depth_source_count: int | None
    depth_agreement: str | None

    @classmethod
    def from_source(cls, player: dict[str, Any]) -> OpportunitySignals:
        return cls(
            depth_chart_slot=player.get("depth_chart_position"),
            depth_chart_order=player.get("depth_chart_order"),
            depth_source_count=player.get("depth_source_count"),
            depth_agreement=player.get("depth_source_agreement"),
        )


@dataclass(frozen=True, slots=True)
class InjurySignals:
    tier: str | None
    weeks: str | None
    confidence: str | None
    sources_checked: tuple[str, ...]
    evidence_summary: Any

    @classmethod
    def from_source(cls, player: dict[str, Any]) -> InjurySignals:
        return cls(
            tier=player.get("tier"),
            weeks=player.get("pdf_weeks_label"),
            confidence=player.get("confidence"),
            sources_checked=tuple(player.get("sources_checked", [])),
            evidence_summary=player.get("current_signals") or player.get("rationale"),
        )


@dataclass(frozen=True, slots=True)
class DraftPlayerContext:
    """Stable player-level contract shared by renderers and ranking tools."""

    rank: int
    name: str
    team: str
    position: str
    position_rank: str
    bye_week: int | None
    pdf_label: str
    offense_rank: int | None
    offensive_line_rank: int | None
    strength_of_schedule_rank: int | None
    projected_injury_weeks: str
    market: MarketSignals
    opportunity: OpportunitySignals
    injury: InjurySignals
    sleeper_consensus: dict[str, Any] | None

    @classmethod
    def from_sources(
        cls,
        *,
        rank: int,
        market: dict[str, Any],
        depth: dict[str, Any],
        injury: dict[str, Any],
        sleeper: dict[str, Any] | None,
    ) -> DraftPlayerContext:
        cls._validate_identity(rank, market, depth, injury)
        return cls(
            rank=rank,
            name=market["name"],
            team=market["team"],
            position=market["position"],
            position_rank=market["position_rank"],
            bye_week=market.get("bye_week"),
            pdf_label=depth.get("pdf_label") or "--",
            offense_rank=depth.get("offense_rank"),
            offensive_line_rank=depth.get("offensive_line_rank"),
            strength_of_schedule_rank=depth.get("strength_of_schedule_rank"),
            projected_injury_weeks=injury.get("pdf_weeks_label") or "--",
            market=MarketSignals.from_source(market),
            opportunity=OpportunitySignals.from_source(depth),
            injury=InjurySignals.from_source(injury),
            sleeper_consensus=sleeper,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def _validate_identity(
        rank: int,
        market: dict[str, Any],
        depth: dict[str, Any],
        injury: dict[str, Any],
    ) -> None:
        expected_name = normalize_name(market.get("name"))
        expected_team = normalize_team(market.get("team"))
        for label, player in (("depth", depth), ("injury", injury)):
            if normalize_name(player.get("name")) != expected_name:
                raise InjuryContextError(
                    f"Rank {rank} name mismatch: market={market.get('name')!r}, "
                    f"{label}={player.get('name')!r}."
                )
            if normalize_team(player.get("team")) != expected_team:
                raise InjuryContextError(
                    f"Rank {rank} team mismatch: market={market.get('team')!r}, "
                    f"{label}={player.get('team')!r}."
                )


@dataclass(frozen=True, slots=True)
class DraftContextDocument:
    metadata: dict[str, Any]
    players: tuple[DraftPlayerContext, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "metadata": self.metadata,
            "players": [player.to_dict() for player in self.players],
        }

    def render_markdown(self) -> str:
        lines = [
            "# Unified 2026 draft context",
            "",
            f"**Generated:** `{self.metadata['generated_at']}`  ",
            f"**Schema:** `{self.metadata['schema_version']}`  ",
            f"**Players:** {self.metadata['player_count']}  ",
            "",
            self.metadata["contract"],
            "",
            "| Rank | Player | Pos-Team | DC | OFF | OL | SOS | INJ | Consensus | "
            "Sources | Sleeper |",
            "|---:|---|---|---|---:|---:|---:|---|---:|---:|---|",
        ]
        for player in self.players:
            sleeper = player.sleeper_consensus or {}
            lines.append(
                f"| {player.rank} | {player.name} | {player.position}-{player.team} | "
                f"{player.pdf_label} | {player.offense_rank or '--'} | "
                f"{player.offensive_line_rank or '--'} | "
                f"{player.strength_of_schedule_rank or '--'} | "
                f"{player.projected_injury_weeks} | "
                f"{player.market.consensus_rank or '--'} | "
                f"{player.market.source_count or 0} | {sleeper.get('tier') or '--'} |"
            )
        lines.append("")
        return "\n".join(lines)


class DraftContextBuilder:
    """Join every player-level input behind one validated, stable schema."""

    def __init__(self, inputs: DraftContextInputs) -> None:
        self.inputs = inputs

    def build(self, *, json_path: Path, markdown_path: Path) -> dict[str, Any]:
        market = self._load(self.inputs.market)
        depth = self._load(self.inputs.depth)
        injury = self._load(self.inputs.injury)
        sleepers = self._load(self.inputs.sleepers)

        market_players = self._rank_index(market, "source_rank")
        depth_players = self._rank_index(depth, "rank")
        injury_players = self._rank_index(injury, "rank")
        sleeper_players = {
            normalize_name(player["player"]): player
            for group in ("sleepers", "rookie_breakout_candidates")
            for player in sleepers.get(group, [])
        }
        expected = set(range(1, 301))
        for name, values in (
            ("market", market_players),
            ("depth", depth_players),
            ("injury", injury_players),
        ):
            if set(values) != expected:
                missing = sorted(expected - set(values))
                raise InjuryContextError(
                    f"{name} context must contain ranks 1-300; missing {missing[:10]}."
                )

        players: list[DraftPlayerContext] = []
        for rank in range(1, 301):
            market_player = market_players[rank]
            depth_player = depth_players[rank]
            injury_player = injury_players[rank]
            sleeper = sleeper_players.get(normalize_name(market_player["name"]))
            players.append(
                DraftPlayerContext.from_sources(
                    rank=rank,
                    market=market_player,
                    depth=depth_player,
                    injury=injury_player,
                    sleeper=sleeper,
                )
            )

        generated_at = datetime.now(UTC).isoformat(timespec="seconds")
        metadata = {
            "schema_version": "1.0.0",
            "generated_at": generated_at,
            "player_count": len(players),
            "inputs": {
                "market": str(self.inputs.market),
                "depth": str(self.inputs.depth),
                "injury": str(self.inputs.injury),
                "sleepers": str(self.inputs.sleepers),
            },
            "input_generated_at": {
                "market": market.get("metadata", {}).get("generated_at"),
                "depth": depth.get("metadata", {}).get("generated_at"),
                "injury": injury.get("metadata", {}).get("generated_at"),
                "sleepers": sleepers.get("metadata", {}).get("generated_at")
                or sleepers.get("metadata", {}).get("research_date"),
            },
            "contract": (
                "This is the normalized player-level input for PDF rendering. The flat PDF "
                "fields remain stable; detailed source values are preserved in nested objects."
            ),
        }
        document = DraftContextDocument(metadata=metadata, players=tuple(players))
        write_json(json_path, document.to_dict())
        write_text(markdown_path, document.render_markdown())
        return {
            "player_count": len(players),
            "json_path": str(json_path),
            "markdown_path": str(markdown_path),
        }

    @staticmethod
    def _load(path: Path) -> dict[str, Any]:
        try:
            return load_json_object(path)
        except StorageError as error:
            raise InjuryContextError(f"Could not read context {path}: {error}") from error

    @staticmethod
    def _rank_index(document: dict[str, Any], rank_key: str) -> dict[int, dict[str, Any]]:
        try:
            return {int(player[rank_key]): player for player in document["players"]}
        except (KeyError, TypeError, ValueError) as error:
            raise InjuryContextError(f"Invalid player context schema: {error}") from error
