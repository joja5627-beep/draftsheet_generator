"""Refresh a publisher-family sleeper and rookie-breakout consensus."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fantasy_football_2026.consensus.common import (
    ArticleCandidateExtractor,
    CachedArticleClient,
    ConsensusBuilderSupport,
    ConsensusSource,
    SourceObservation,
)
from fantasy_football_2026.constants import (
    DEFAULT_TIMEOUT_SECONDS,
    CacheName,
    ContextFile,
    DirectoryName,
)
from fantasy_football_2026.domain.normalization import normalize_name
from fantasy_football_2026.errors import InjuryContextError
from fantasy_football_2026.infrastructure.storage import write_json, write_text

SleeperSource = ConsensusSource


@dataclass(frozen=True, slots=True)
class ConsensusCandidate:
    player: str
    position_team: str
    rookie: bool
    tier: str
    consensus_score: float
    source_family_count: int
    source_families: tuple[str, ...]
    fftoday_adp: float | None
    market_consensus_rank: float | None
    depth_chart_label: str
    depth_chart_order: int | None
    injury_weeks: str
    draft_action: str
    flags: tuple[str, ...]


class SleeperConsensusBuilder(ConsensusBuilderSupport):
    """Combine source-family votes with live market, role, and injury constraints."""

    def __init__(
        self,
        *,
        source_catalog_path: Path,
        market_path: Path,
        depth_path: Path,
        injury_path: Path,
        sleeper_players_path: Path,
        client: CachedArticleClient,
    ) -> None:
        self.source_catalog_path = source_catalog_path
        self.market_path = market_path
        self.depth_path = depth_path
        self.injury_path = injury_path
        self.sleeper_players_path = sleeper_players_path
        self.client = client

    def build(self, *, json_path: Path, markdown_path: Path) -> dict[str, Any]:
        catalog = self._load(self.source_catalog_path)
        market = self._load(self.market_path)
        depth = self._load(self.depth_path)
        injury = self._load(self.injury_path)
        sleeper_players = self._load(self.sleeper_players_path)
        market_players = market["players"]
        names = tuple(str(player["name"]) for player in market_players)
        canonical = {normalize_name(name): name for name in names}
        extractor = ArticleCandidateExtractor(names)

        votes: dict[str, set[str]] = {}
        observations: list[SourceObservation] = []
        for source in self._sources(catalog):
            try:
                html, retrieved_at, from_cache = self.client.fetch(source)
                found = extractor.extract(source, html)
                for player in found:
                    resolved = self._resolve_name(player, canonical)
                    if resolved:
                        votes.setdefault(resolved, set()).add(source.family)
                observations.append(
                    SourceObservation(
                        source_id=source.source_id,
                        family=source.family,
                        url=source.url,
                        retrieved_at=retrieved_at,
                        from_cache=from_cache,
                        players=tuple(
                            resolved
                            for player in found
                            if (resolved := self._resolve_name(player, canonical))
                        ),
                        status="ok",
                        error=None,
                    )
                )
            except InjuryContextError as error:
                observations.append(
                    SourceObservation(
                        source_id=source.source_id,
                        family=source.family,
                        url=source.url,
                        retrieved_at=None,
                        from_cache=False,
                        players=(),
                        status="error" if source.required else "optional-error",
                        error=str(error),
                    )
                )
                if source.required:
                    raise

        available_sources = sum(item.status == "ok" for item in observations)
        minimum_sources = int(catalog.get("minimum_available_sources", 1))
        if available_sources < minimum_sources:
            raise InjuryContextError(
                "Sleeper consensus has only "
                f"{available_sources} available source pages; requires {minimum_sources}."
            )

        depth_by_name = self._name_index(depth["players"])
        injury_by_name = self._name_index(injury["players"])
        market_by_name = self._name_index(market_players)
        rookie_names = {
            normalize_name(player.get("full_name"))
            for player in sleeper_players.values()
            if player.get("years_exp") == 0 or player.get("metadata", {}).get("rookie_year") == 2026
        }
        candidates = [
            self._candidate(
                name=name,
                families=families,
                market=market_by_name[name],
                depth=depth_by_name.get(name, {}),
                injury=injury_by_name.get(name, {}),
                rookie=name in rookie_names,
            )
            for name, families in votes.items()
            if name in market_by_name
        ]
        sleepers = sorted(
            (candidate for candidate in candidates if not candidate.rookie),
            key=self._sort_key,
        )
        rookies = sorted(
            (candidate for candidate in candidates if candidate.rookie),
            key=self._sort_key,
        )
        generated_at = datetime.now(UTC).isoformat(timespec="seconds")
        metadata = {
            "schema_version": "1.0.0",
            "generated_at": generated_at,
            "method": (
                "Publisher families are deduplicated, then current ADP, depth order, "
                "injury weeks, and one-QB format fit determine score and action flags."
            ),
            "source_pages": len(observations),
            "source_pages_ok": available_sources,
            "source_pages_with_errors": sum(item.status != "ok" for item in observations),
            "minimum_available_sources": minimum_sources,
            "inputs": {
                "catalog": str(self.source_catalog_path),
                "market": str(self.market_path),
                "depth": str(self.depth_path),
                "injury": str(self.injury_path),
            },
        }
        document = {
            "metadata": metadata,
            "source_observations": [asdict(item) for item in observations],
            "sleepers": [asdict(item) for item in sleepers],
            "rookie_breakout_candidates": [asdict(item) for item in rookies],
        }
        write_json(json_path, document)
        write_text(markdown_path, self.render_markdown(metadata, sleepers, rookies))
        return {
            "sleeper_count": len(sleepers),
            "rookie_count": len(rookies),
            "source_pages_ok": metadata["source_pages_ok"],
            "json_path": str(json_path),
            "markdown_path": str(markdown_path),
        }

    def _candidate(
        self,
        *,
        name: str,
        families: set[str],
        market: dict[str, Any],
        depth: dict[str, Any],
        injury: dict[str, Any],
        rookie: bool,
    ) -> ConsensusCandidate:
        family_count = len(families)
        depth_order = self._optional_int(depth.get("depth_chart_order"))
        injury_label = str(injury.get("pdf_weeks_label") or "--")
        injury_max = self._injury_max(injury_label)
        adp = self._optional_float(market.get("fftoday_adp"))
        consensus_rank = self._optional_float(market.get("consensus_rank"))
        role_points = {1: 10.0, 2: 7.0, 3: 4.0}.get(depth_order, 0.0)
        health_points = 10.0 if injury_max == 0 else 6.0 if injury_max <= 2 else 0.0
        price_reference = adp or consensus_rank or 0.0
        price_points = 5.0 if price_reference >= 100 else 2.0 if price_reference >= 72 else 0.0
        position = str(market.get("position") or "")
        format_adjustment = -5.0 if position == "QB" else 0.0
        score = max(
            0.0,
            min(
                100.0,
                (min(family_count, 5) * 15.0)
                + role_points
                + health_points
                + price_points
                + format_adjustment,
            ),
        )
        flags: list[str] = []
        if injury_max >= 3:
            flags.append("health-blocked")
        if depth_order is None or depth_order >= 4:
            flags.append("role-blocked")
        if price_reference and price_reference < 84:
            flags.append("value-not-deep-sleeper")
        if position == "QB":
            flags.append("one-qb-format-downgrade")
        tier = "A" if family_count >= 3 else "B" if family_count == 2 else "C"
        if "health-blocked" in flags or "role-blocked" in flags:
            tier = "C"
        if "value-not-deep-sleeper" in flags and tier != "C":
            tier = f"{tier}-value"
        action = self._automatic_action(price_reference, flags)
        return ConsensusCandidate(
            player=str(market["name"]),
            position_team=f"{position}-{market['team']}",
            rookie=rookie,
            tier=tier,
            consensus_score=round(score, 1),
            source_family_count=family_count,
            source_families=tuple(sorted(families)),
            fftoday_adp=adp,
            market_consensus_rank=consensus_rank,
            depth_chart_label=str(depth.get("pdf_label") or "--"),
            depth_chart_order=depth_order,
            injury_weeks=injury_label,
            draft_action=action,
            flags=tuple(flags),
        )

    @staticmethod
    def render_markdown(
        metadata: dict[str, Any],
        sleepers: list[ConsensusCandidate],
        rookies: list[ConsensusCandidate],
    ) -> str:
        lines = [
            "# Generated sleeper and rookie consensus",
            "",
            f"**Generated:** `{metadata['generated_at']}`  ",
            "**Source pages available:** "
            f"{metadata['source_pages_ok']}/{metadata['source_pages']}  ",
            "",
            metadata["method"],
            "",
        ]
        for title, candidates in (("Sleepers", sleepers), ("Rookie breakout candidates", rookies)):
            lines.extend(
                [
                    f"## {title}",
                    "",
                    "| Rank | Player | Tier | Score | Families | ADP | DC | INJ | Action |",
                    "|---:|---|---|---:|---:|---:|---|---|---|",
                ]
            )
            for rank, candidate in enumerate(candidates, start=1):
                lines.append(
                    f"| {rank} | {candidate.player} ({candidate.position_team}) | "
                    f"{candidate.tier} | {candidate.consensus_score:.1f} | "
                    f"{candidate.source_family_count} | {candidate.fftoday_adp or '--'} | "
                    f"{candidate.depth_chart_label} | {candidate.injury_weeks} | "
                    f"{candidate.draft_action} |"
                )
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _sources(catalog: dict[str, Any]) -> tuple[SleeperSource, ...]:
        return ConsensusBuilderSupport._sources(
            catalog,
            default_mode="headings",
            include_players=True,
            catalog_name="sleeper",
        )

    @staticmethod
    def _sort_key(candidate: ConsensusCandidate) -> tuple[float, int, float, str]:
        return (
            -candidate.consensus_score,
            -candidate.source_family_count,
            -(candidate.fftoday_adp or 0.0),
            candidate.player,
        )

    @staticmethod
    def _automatic_action(price_reference: float, flags: list[str]) -> str:
        if "health-blocked" in flags or "role-blocked" in flags:
            return "Watchlist until the blocking health or depth-chart signal clears."
        if not price_reference:
            return "Final-round watch; confirm a live market price."
        round_number = max(1, int((price_reference - 1) // 12) + 1)
        if "value-not-deep-sleeper" in flags:
            return f"Evaluate as a Round {round_number} value, not as a deep sleeper."
        return f"Target at market in Round {round_number} or later; do not chase above ADP."


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build publisher-family sleeper and rookie-breakout consensus."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--refresh", action="store_true", help="refresh article caches")
    mode.add_argument("--offline", action="store_true", help="use caches only")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    builder = SleeperConsensusBuilder(
        source_catalog_path=Path(DirectoryName.CONTEXT, ContextFile.SLEEPER_SOURCES_JSON),
        market_path=Path(DirectoryName.CONTEXT, ContextFile.MARKET_JSON),
        depth_path=Path(DirectoryName.CONTEXT, ContextFile.PLAYER_DEPTH_JSON),
        injury_path=Path(DirectoryName.CONTEXT, ContextFile.INJURIES_JSON),
        sleeper_players_path=Path(
            DirectoryName.CONTEXT,
            DirectoryName.CACHE,
            CacheName.SLEEPER_PLAYERS_JSON,
        ),
        client=CachedArticleClient(
            cache_dir=Path(
                DirectoryName.CONTEXT,
                DirectoryName.CACHE,
                CacheName.SLEEPER_SOURCES,
            ),
            refresh=args.refresh,
            offline=args.offline,
            timeout=args.timeout,
        ),
    )
    result = builder.build(
        json_path=Path(DirectoryName.CONTEXT, ContextFile.SLEEPER_CONSENSUS_JSON),
        markdown_path=Path(DirectoryName.CONTEXT, ContextFile.SLEEPER_CONSENSUS_MARKDOWN),
    )
    print(f"Sleeper candidates: {result['sleeper_count']}")
    print(f"Rookie candidates: {result['rookie_count']}")
    print(f"Source pages available: {result['source_pages_ok']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
