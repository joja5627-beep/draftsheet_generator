"""Build an automated, publisher-family RB handcuff consensus."""

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


@dataclass(frozen=True, slots=True)
class HandcuffCandidate:
    player: str
    team: str
    starter: str
    depth_chart_label: str
    depth_chart_order: int
    consensus_score: float
    tier: str
    source_family_count: int
    source_families: tuple[str, ...]
    market_consensus_rank: float | None
    fftoday_adp: float | None
    offense_rank: int | None
    projected_points: float | None
    starter_projected_points: float | None
    top_two_projected_points_share: float | None
    injury_weeks: str
    starter_injury_weeks: str
    highlighted: bool
    flags: tuple[str, ...]
    draft_action: str


class HandcuffConsensusBuilder(ConsensusBuilderSupport):
    """Cross-check publisher mentions against live RB depth and health context."""

    def __init__(
        self,
        *,
        source_catalog_path: Path,
        market_path: Path,
        depth_path: Path,
        injury_path: Path,
        projections_path: Path,
        client: CachedArticleClient,
    ) -> None:
        self.source_catalog_path = source_catalog_path
        self.market_path = market_path
        self.depth_path = depth_path
        self.injury_path = injury_path
        self.projections_path = projections_path
        self.client = client

    def build(self, *, json_path: Path, markdown_path: Path) -> dict[str, Any]:
        catalog = self._load(self.source_catalog_path)
        market = self._load(self.market_path)
        depth = self._load(self.depth_path)
        injury = self._load(self.injury_path)
        projections = self._load(self.projections_path)
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
                resolved_names = tuple(
                    resolved
                    for player in found
                    if (resolved := self._resolve_name(player, canonical))
                )
                for name in resolved_names:
                    votes.setdefault(name, set()).add(source.family)
                observations.append(
                    SourceObservation(
                        source_id=source.source_id,
                        family=source.family,
                        url=source.url,
                        retrieved_at=retrieved_at,
                        from_cache=from_cache,
                        players=resolved_names,
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
                "Handcuff consensus has only "
                f"{available_sources} available source pages; requires {minimum_sources}."
            )

        market_by_name = self._name_index(market_players)
        depth_by_name = self._name_index(depth["players"])
        injury_by_name = self._name_index(injury["players"])
        projections_by_name = self._name_index(projections["players"])
        minimum_families = int(catalog.get("minimum_families_to_highlight", 2))
        maximum_committee_share = float(catalog.get("maximum_top_two_projected_points_share", 0.30))
        starters = self._team_starters(market_players, depth_by_name)
        candidates = [
            candidate
            for name, families in votes.items()
            if (
                candidate := self._candidate(
                    name=name,
                    families=families,
                    market=market_by_name.get(name, {}),
                    depth=depth_by_name.get(name, {}),
                    injury=injury_by_name.get(name, {}),
                    projection=projections_by_name.get(name, {}),
                    starter=starters.get(str(market_by_name.get(name, {}).get("team") or "")),
                    injury_by_name=injury_by_name,
                    projections_by_name=projections_by_name,
                    minimum_families=minimum_families,
                    maximum_committee_share=maximum_committee_share,
                )
            )
            is not None
        ]
        candidates.sort(key=self._sort_key)
        generated_at = datetime.now(UTC).isoformat(timespec="seconds")
        metadata = {
            "schema_version": "1.1.0",
            "generated_at": generated_at,
            "method": (
                "Publisher families are deduplicated; a player must be a current ranked RB2/RB3. "
                "Highlighting requires RB2 status, candidate health, the configured minimum "
                "number of independent publisher families, and no more than the configured share "
                "of the starter-plus-candidate projected fantasy points. This last gate removes "
                "committee backs with meaningful standalone workloads."
            ),
            "source_pages": len(observations),
            "source_pages_ok": available_sources,
            "source_pages_with_errors": sum(item.status != "ok" for item in observations),
            "minimum_available_sources": minimum_sources,
            "minimum_families_to_highlight": minimum_families,
            "maximum_top_two_projected_points_share": maximum_committee_share,
            "inputs": {
                "catalog": str(self.source_catalog_path),
                "market": str(self.market_path),
                "depth": str(self.depth_path),
                "injury": str(self.injury_path),
                "projections": str(self.projections_path),
            },
        }
        document = {
            "metadata": metadata,
            "source_observations": [asdict(item) for item in observations],
            "candidates": [asdict(item) for item in candidates],
        }
        write_json(json_path, document)
        write_text(markdown_path, self.render_markdown(metadata, candidates))
        return {
            "candidate_count": len(candidates),
            "highlighted_count": sum(candidate.highlighted for candidate in candidates),
            "source_pages_ok": available_sources,
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
        projection: dict[str, Any],
        starter: tuple[str, dict[str, Any]] | None,
        injury_by_name: dict[str, dict[str, Any]],
        projections_by_name: dict[str, dict[str, Any]],
        minimum_families: int,
        maximum_committee_share: float,
    ) -> HandcuffCandidate | None:
        if str(market.get("position") or "") != "RB":
            return None
        depth_order = self._optional_int(depth.get("depth_chart_order"))
        if depth_order is None:
            depth_order = self._optional_int(depth.get("espn_depth_chart_order"))
        if depth_order not in {2, 3}:
            return None
        starter_name = starter[0] if starter else "Unresolved"
        starter_injury = injury_by_name.get(normalize_name(starter_name), {})
        starter_projection = projections_by_name.get(normalize_name(starter_name), {})
        injury_label = str(injury.get("pdf_weeks_label") or "--")
        starter_injury_label = str(starter_injury.get("pdf_weeks_label") or "--")
        injury_max = self._injury_max(injury_label)
        family_count = len(families)
        offense_rank = self._optional_int(depth.get("offense_rank"))
        consensus_rank = self._optional_float(market.get("consensus_rank"))
        adp = self._optional_float(market.get("fftoday_adp"))
        projected_points = self._optional_float(projection.get("custom_projected_points"))
        starter_projected_points = self._optional_float(
            starter_projection.get("custom_projected_points")
        )
        projection_total = (projected_points or 0.0) + (starter_projected_points or 0.0)
        top_two_projection_share = (
            projected_points / projection_total
            if projected_points is not None
            and starter_projected_points is not None
            and projection_total > 0
            else None
        )
        flags: list[str] = []
        if depth_order == 3:
            flags.append("third-in-depth-order")
        if str(depth.get("depth_source_agreement") or "") == "disagreement":
            flags.append("depth-disagreement")
        if injury_max >= 3:
            flags.append("health-blocked")
        if starter is None:
            flags.append("starter-unresolved")
        if top_two_projection_share is None:
            flags.append("committee-role-unresolved")
        elif top_two_projection_share > maximum_committee_share:
            flags.append("committee-profile")
        highlighted = (
            family_count >= minimum_families
            and depth_order == 2
            and injury_max < 3
            and starter is not None
            and top_two_projection_share is not None
            and top_two_projection_share <= maximum_committee_share
        )
        role_points = 18.0 if depth_order == 2 else 8.0
        if offense_rank and offense_rank <= 10:
            offense_points = 8.0
        elif offense_rank and offense_rank <= 22:
            offense_points = 4.0
        else:
            offense_points = 0.0
        price = adp or consensus_rank or 0.0
        price_points = 5.0 if price >= 120 else 2.0 if price >= 72 else 0.0
        health_penalty = 20.0 if injury_max >= 3 else 0.0
        committee_penalty = (
            20.0
            if top_two_projection_share is None
            or top_two_projection_share > maximum_committee_share
            else 0.0
        )
        score = max(
            0.0,
            min(
                100.0,
                min(family_count, 4) * 18.0
                + role_points
                + offense_points
                + price_points
                - health_penalty
                - committee_penalty,
            ),
        )
        tier = "A" if highlighted and family_count >= 3 else "B" if highlighted else "C"
        if highlighted:
            draft_action = self._draft_action(price, starter_name)
        elif "committee-profile" in flags:
            draft_action = "Watchlist only; projected workload indicates a committee role."
        elif "committee-role-unresolved" in flags:
            draft_action = "Watchlist only; projected workload split is unresolved."
        else:
            draft_action = "Watchlist only; needs stronger consensus, direct RB2 status, or health."
        return HandcuffCandidate(
            player=str(market["name"]),
            team=str(market["team"]),
            starter=starter_name,
            depth_chart_label=str(depth.get("pdf_label") or f"RB{depth_order}"),
            depth_chart_order=depth_order,
            consensus_score=round(score, 1),
            tier=tier,
            source_family_count=family_count,
            source_families=tuple(sorted(families)),
            market_consensus_rank=consensus_rank,
            fftoday_adp=adp,
            offense_rank=offense_rank,
            projected_points=projected_points,
            starter_projected_points=starter_projected_points,
            top_two_projected_points_share=(
                round(top_two_projection_share, 3) if top_two_projection_share is not None else None
            ),
            injury_weeks=injury_label,
            starter_injury_weeks=starter_injury_label,
            highlighted=highlighted,
            flags=tuple(flags),
            draft_action=draft_action,
        )

    @staticmethod
    def render_markdown(metadata: dict[str, Any], candidates: list[HandcuffCandidate]) -> str:
        lines = [
            "# Generated running back handcuff consensus",
            "",
            f"**Generated:** `{metadata['generated_at']}`",
            f"**Source pages available:** {metadata['source_pages_ok']}/{metadata['source_pages']}",
            "",
            metadata["method"],
            "",
            "| Rank | Player | Team | Backs up | Tier | Score | Families | DC | OFF | "
            "Top-2 share | INJ | Starter INJ | Highlight | Action |",
            "|---:|---|---|---|---|---:|---:|---|---:|---:|---|---|---|---|",
        ]
        for rank, candidate in enumerate(candidates, start=1):
            share_label = (
                f"{candidate.top_two_projected_points_share:.0%}"
                if candidate.top_two_projected_points_share is not None
                else "--"
            )
            lines.append(
                f"| {rank} | {candidate.player} | {candidate.team} | {candidate.starter} | "
                f"{candidate.tier} | {candidate.consensus_score:.1f} | "
                f"{candidate.source_family_count} | {candidate.depth_chart_label} | "
                f"{candidate.offense_rank or '--'} | {share_label} | "
                f"{candidate.injury_weeks} | "
                f"{candidate.starter_injury_weeks} | "
                f"{'yes' if candidate.highlighted else 'no'} | {candidate.draft_action} |"
            )
        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _team_starters(
        market_players: list[dict[str, Any]],
        depth_by_name: dict[str, dict[str, Any]],
    ) -> dict[str, tuple[str, dict[str, Any]]]:
        starters: dict[str, tuple[str, dict[str, Any]]] = {}
        for player in market_players:
            if str(player.get("position") or "") != "RB":
                continue
            name = normalize_name(player.get("name"))
            depth = depth_by_name.get(name, {})
            order = HandcuffConsensusBuilder._optional_int(depth.get("depth_chart_order"))
            if order is None:
                order = HandcuffConsensusBuilder._optional_int(depth.get("espn_depth_chart_order"))
            if order == 1:
                starters[str(player.get("team") or "")] = (str(player["name"]), depth)
        return starters

    @staticmethod
    def _draft_action(price: float, starter: str) -> str:
        if not price:
            return f"Final-round watch behind {starter}; confirm a live market price."
        round_number = max(1, int((price - 1) // 12) + 1)
        starter_label = starter.rstrip(".")
        return f"Handcuff target in Round {round_number} or later behind {starter_label}."

    @staticmethod
    def _sort_key(candidate: HandcuffCandidate) -> tuple[int, float, int, str]:
        return (
            0 if candidate.highlighted else 1,
            -candidate.consensus_score,
            candidate.depth_chart_order,
            candidate.player,
        )

    @staticmethod
    def _sources(catalog: dict[str, Any]) -> tuple[ConsensusSource, ...]:
        return ConsensusBuilderSupport._sources(
            catalog,
            default_mode="explicit",
            include_players=False,
            catalog_name="handcuff",
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build automated RB handcuff consensus.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--refresh", action="store_true")
    mode.add_argument("--offline", action="store_true")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    builder = HandcuffConsensusBuilder(
        source_catalog_path=Path(DirectoryName.CONTEXT, ContextFile.HANDCUFF_SOURCES_JSON),
        market_path=Path(DirectoryName.CONTEXT, ContextFile.MARKET_JSON),
        depth_path=Path(DirectoryName.CONTEXT, ContextFile.PLAYER_DEPTH_JSON),
        injury_path=Path(DirectoryName.CONTEXT, ContextFile.INJURIES_JSON),
        projections_path=Path(DirectoryName.CONTEXT, ContextFile.PROJECTIONS_JSON),
        client=CachedArticleClient(
            cache_dir=Path(
                DirectoryName.CONTEXT,
                DirectoryName.CACHE,
                CacheName.HANDCUFF_SOURCES,
            ),
            refresh=args.refresh,
            offline=args.offline,
            timeout=args.timeout,
        ),
    )
    result = builder.build(
        json_path=Path(DirectoryName.CONTEXT, ContextFile.HANDCUFF_CONSENSUS_JSON),
        markdown_path=Path(DirectoryName.CONTEXT, ContextFile.HANDCUFF_CONSENSUS_MARKDOWN),
    )
    print(f"Handcuff candidates: {result['candidate_count']}")
    print(f"Highlighted handcuffs: {result['highlighted_count']}")
    print(f"Source pages available: {result['source_pages_ok']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
