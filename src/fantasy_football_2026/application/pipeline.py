"""Fantasy-football stages composed with the reusable build framework."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fantasy_football_2026.application.core import (
    ContextPipeline,
    PipelineConfig,
    PipelineContext,
    PipelineError,
    PipelineStage,
    ProjectPaths,
    StageResult,
)
from fantasy_football_2026.consensus.common import CachedArticleClient
from fantasy_football_2026.consensus.handcuffs import HandcuffConsensusBuilder
from fantasy_football_2026.consensus.sleepers import SleeperConsensusBuilder
from fantasy_football_2026.constants import (
    HANDCUFF_HIGHLIGHT_COLOR,
    SLEEPER_HIGHLIGHT_COLOR,
    TOTAL_RANKED_PLAYERS,
    CacheName,
    ContextFile,
    OutputFile,
    StageName,
)
from fantasy_football_2026.domain.draft import DraftContextBuilder, DraftContextInputs
from fantasy_football_2026.domain.normalization import normalize_name
from fantasy_football_2026.domain.rankings import update_reweighted_rankings
from fantasy_football_2026.infrastructure.storage import DEFAULT_STORE, ArtifactStore
from fantasy_football_2026.presentation.pdf import render_reweighted_template_pdf
from fantasy_football_2026.sources.depth_charts import update_depth_chart_context
from fantasy_football_2026.sources.injuries import update_injury_context
from fantasy_football_2026.sources.market import update_market_context
from fantasy_football_2026.sources.projections import ProjectionContextBuilder
from fantasy_football_2026.sources.schedule import update_schedule_context
from fantasy_football_2026.sources.teams import update_team_context


class TeamProjectionStage(PipelineStage):
    name = StageName.TEAM_PROJECTIONS

    def run(self, context: PipelineContext) -> StageResult:
        paths = context.paths
        result = update_team_context(
            markdown_path=paths.context_file(ContextFile.TEAM_PROJECTIONS_MARKDOWN),
            json_path=paths.context_file(ContextFile.TEAM_PROJECTIONS_JSON),
            cache_dir=paths.cache,
            refresh=context.config.refresh,
            offline=context.config.offline,
            timeout=context.config.timeout,
        )
        return StageResult(
            (
                paths.context_file(ContextFile.TEAM_PROJECTIONS_JSON),
                paths.context_file(ContextFile.TEAM_PROJECTIONS_MARKDOWN),
            ),
            result,
        )


class ScheduleStage(PipelineStage):
    name = StageName.SCHEDULE

    def run(self, context: PipelineContext) -> StageResult:
        paths = context.paths
        result = update_schedule_context(
            markdown_path=paths.context_file(ContextFile.SCHEDULE_MARKDOWN),
            json_path=paths.context_file(ContextFile.SCHEDULE_JSON),
            cache_path=paths.cache_file(CacheName.SCHEDULE_HTML),
            refresh=context.config.refresh,
            offline=context.config.offline,
            timeout=context.config.timeout,
        )
        return StageResult(
            (
                paths.context_file(ContextFile.SCHEDULE_JSON),
                paths.context_file(ContextFile.SCHEDULE_MARKDOWN),
            ),
            result,
        )


class InjuryStage(PipelineStage):
    name = StageName.INJURIES

    def run(self, context: PipelineContext) -> StageResult:
        paths = context.paths
        result = update_injury_context(
            pdf_path=paths.source_pdf,
            markdown_path=paths.context_file(ContextFile.INJURIES_MARKDOWN),
            json_path=paths.context_file(ContextFile.INJURIES_JSON),
            overrides_path=None,
            cache_dir=paths.cache,
            refresh=context.config.refresh,
            offline=context.config.offline,
            timeout=context.config.timeout,
            reweighting_context_path=paths.context_file(ContextFile.GEMINI_RESEARCH_MARKDOWN),
        )
        return StageResult(
            (
                paths.context_file(ContextFile.INJURIES_JSON),
                paths.context_file(ContextFile.INJURIES_MARKDOWN),
            ),
            result,
        )


class MarketStage(PipelineStage):
    name = StageName.MARKET

    def run(self, context: PipelineContext) -> StageResult:
        paths = context.paths
        result = update_market_context(
            pdf_path=paths.source_pdf,
            markdown_path=paths.context_file(ContextFile.MARKET_MARKDOWN),
            json_path=paths.context_file(ContextFile.MARKET_JSON),
            cache_dir=paths.cache,
            refresh=context.config.refresh,
            offline=context.config.offline,
            timeout=context.config.timeout,
        )
        return StageResult(
            (
                paths.context_file(ContextFile.MARKET_JSON),
                paths.context_file(ContextFile.MARKET_MARKDOWN),
            ),
            result,
        )


class ProjectionStage(PipelineStage):
    name = StageName.PROJECTIONS
    dependencies = (StageName.MARKET,)

    def run(self, context: PipelineContext) -> StageResult:
        paths = context.paths
        builder = ProjectionContextBuilder(
            scoring_path=paths.context_file(ContextFile.LEAGUE_SCORING),
            market_path=paths.context_file(ContextFile.MARKET_JSON),
            model_path=paths.context_file(ContextFile.MODEL_JSON),
            cache_dir=paths.cache / CacheName.PROJECTIONS,
            refresh=context.config.refresh,
            offline=context.config.offline,
            timeout=context.config.timeout,
            teams=context.config.teams,
        )
        json_path = paths.context_file(ContextFile.PROJECTIONS_JSON)
        markdown_path = paths.context_file(ContextFile.PROJECTIONS_MARKDOWN)
        result = builder.build(json_path=json_path, markdown_path=markdown_path)
        return StageResult((json_path, markdown_path), result)


class DepthChartStage(PipelineStage):
    name = StageName.DEPTH_CHARTS
    dependencies = (StageName.TEAM_PROJECTIONS, StageName.SCHEDULE, StageName.INJURIES)

    def run(self, context: PipelineContext) -> StageResult:
        paths = context.paths
        result = update_depth_chart_context(
            pdf_path=paths.source_pdf,
            markdown_path=paths.context_file(ContextFile.PLAYER_DEPTH_MARKDOWN),
            json_path=paths.context_file(ContextFile.PLAYER_DEPTH_JSON),
            cache_dir=paths.cache,
            team_projections_path=paths.context_file(ContextFile.TEAM_PROJECTIONS_JSON),
            strength_of_schedule_path=paths.context_file(ContextFile.SCHEDULE_JSON),
            injury_context_path=paths.context_file(ContextFile.INJURIES_JSON),
            refresh=context.config.refresh,
            offline=context.config.offline,
            timeout=context.config.timeout,
        )
        return StageResult(
            (
                paths.context_file(ContextFile.PLAYER_DEPTH_JSON),
                paths.context_file(ContextFile.PLAYER_DEPTH_MARKDOWN),
                paths.context_file(ContextFile.COLUMN_VALIDATION_JSON),
                paths.context_file(ContextFile.COLUMN_VALIDATION_MARKDOWN),
            ),
            result,
        )


class SleeperConsensusStage(PipelineStage):
    name = StageName.SLEEPER_CONSENSUS
    dependencies = (StageName.MARKET, StageName.DEPTH_CHARTS, StageName.INJURIES)

    def run(self, context: PipelineContext) -> StageResult:
        paths = context.paths
        builder = SleeperConsensusBuilder(
            source_catalog_path=paths.context_file(ContextFile.SLEEPER_SOURCES_JSON),
            market_path=paths.context_file(ContextFile.MARKET_JSON),
            depth_path=paths.context_file(ContextFile.PLAYER_DEPTH_JSON),
            injury_path=paths.context_file(ContextFile.INJURIES_JSON),
            sleeper_players_path=paths.cache_file(CacheName.SLEEPER_PLAYERS_JSON),
            client=CachedArticleClient(
                cache_dir=paths.cache / CacheName.SLEEPER_SOURCES,
                refresh=context.config.refresh,
                offline=context.config.offline,
                timeout=context.config.timeout,
            ),
        )
        json_path = paths.context_file(ContextFile.SLEEPER_CONSENSUS_JSON)
        markdown_path = paths.context_file(ContextFile.SLEEPER_CONSENSUS_MARKDOWN)
        result = builder.build(json_path=json_path, markdown_path=markdown_path)
        return StageResult((json_path, markdown_path), result)


class HandcuffConsensusStage(PipelineStage):
    name = StageName.HANDCUFF_CONSENSUS
    dependencies = (
        StageName.MARKET,
        StageName.DEPTH_CHARTS,
        StageName.INJURIES,
        StageName.PROJECTIONS,
    )

    def run(self, context: PipelineContext) -> StageResult:
        paths = context.paths
        builder = HandcuffConsensusBuilder(
            source_catalog_path=paths.context_file(ContextFile.HANDCUFF_SOURCES_JSON),
            market_path=paths.context_file(ContextFile.MARKET_JSON),
            depth_path=paths.context_file(ContextFile.PLAYER_DEPTH_JSON),
            injury_path=paths.context_file(ContextFile.INJURIES_JSON),
            projections_path=paths.context_file(ContextFile.PROJECTIONS_JSON),
            client=CachedArticleClient(
                cache_dir=paths.cache / CacheName.HANDCUFF_SOURCES,
                refresh=context.config.refresh,
                offline=context.config.offline,
                timeout=context.config.timeout,
            ),
        )
        json_path = paths.context_file(ContextFile.HANDCUFF_CONSENSUS_JSON)
        markdown_path = paths.context_file(ContextFile.HANDCUFF_CONSENSUS_MARKDOWN)
        result = builder.build(json_path=json_path, markdown_path=markdown_path)
        return StageResult((json_path, markdown_path), result)


class UnifiedContextStage(PipelineStage):
    name = StageName.UNIFIED_CONTEXT
    dependencies = (
        StageName.MARKET,
        StageName.DEPTH_CHARTS,
        StageName.INJURIES,
        StageName.SLEEPER_CONSENSUS,
    )

    def run(self, context: PipelineContext) -> StageResult:
        paths = context.paths
        builder = DraftContextBuilder(
            DraftContextInputs(
                market=paths.context_file(ContextFile.MARKET_JSON),
                depth=paths.context_file(ContextFile.PLAYER_DEPTH_JSON),
                injury=paths.context_file(ContextFile.INJURIES_JSON),
                sleepers=paths.context_file(ContextFile.SLEEPER_CONSENSUS_JSON),
            )
        )
        json_path = paths.context_file(ContextFile.DRAFT_CONTEXT_JSON)
        markdown_path = paths.context_file(ContextFile.DRAFT_CONTEXT_MARKDOWN)
        result = builder.build(json_path=json_path, markdown_path=markdown_path)
        return StageResult((json_path, markdown_path), result)


class SourceOrderPdfStage(PipelineStage):
    name = StageName.SOURCE_ORDER_PDF
    dependencies = (StageName.RANKINGS,)

    def run(self, context: PipelineContext) -> StageResult:
        paths = context.paths
        output = paths.output_pdf(OutputFile.REWEIGHTED_PDF)
        legacy_output = paths.output_pdf(
            f"{paths.source_pdf.stem}-{context.config.teams}-team-rounds.pdf"
        )
        rankings = DEFAULT_STORE.load_object(paths.context_file(ContextFile.REWEIGHTED_JSON))
        rank_mapping, _, _, highlight_colors = _template_pdf_contract(
            rankings=rankings,
            sleepers=DEFAULT_STORE.load_object(
                paths.context_file(ContextFile.SLEEPER_CONSENSUS_JSON)
            ),
            handcuffs=DEFAULT_STORE.load_object(
                paths.context_file(ContextFile.HANDCUFF_CONSENSUS_JSON)
            ),
        )
        players = rankings.get("players")
        if not isinstance(players, list):
            raise PipelineError("Template PDF requires reweighted player rows.")
        result = render_reweighted_template_pdf(
            paths.source_pdf,
            output,
            teams=context.config.teams,
            players=players,
            row_highlight_colors=highlight_colors,
        )
        outputs = [output]
        if context.config.build_legacy_pdf:
            DEFAULT_STORE.write_bytes(legacy_output, output.read_bytes())
            outputs.append(legacy_output)
        return StageResult(
            tuple(outputs),
            {
                "ranks": TOTAL_RANKED_PLAYERS,
                "rounds": (TOTAL_RANKED_PLAYERS + context.config.teams - 1) // context.config.teams,
                "pages": result.page_count,
                "reordered_players": sum(source != final for source, final in rank_mapping.items()),
                "target_highlights": len(highlight_colors),
            },
        )


class RankingStage(PipelineStage):
    name = StageName.RANKINGS
    dependencies = (
        StageName.MARKET,
        StageName.DEPTH_CHARTS,
        StageName.INJURIES,
        StageName.PROJECTIONS,
        StageName.UNIFIED_CONTEXT,
        StageName.HANDCUFF_CONSENSUS,
    )

    def run(self, context: PipelineContext) -> StageResult:
        paths = context.paths
        result = update_reweighted_rankings(
            market_path=paths.context_file(ContextFile.MARKET_JSON),
            depth_path=paths.context_file(ContextFile.PLAYER_DEPTH_JSON),
            injury_path=paths.context_file(ContextFile.INJURIES_JSON),
            model_path=paths.context_file(ContextFile.MODEL_JSON),
            projection_context_path=paths.context_file(ContextFile.PROJECTIONS_JSON),
            sleeper_context_path=paths.context_file(ContextFile.SLEEPER_CONSENSUS_JSON),
            handcuff_context_path=paths.context_file(ContextFile.HANDCUFF_CONSENSUS_JSON),
            json_path=paths.context_file(ContextFile.REWEIGHTED_JSON),
            markdown_path=paths.context_file(ContextFile.REWEIGHTED_MARKDOWN),
            audit_json_path=paths.context_file(ContextFile.SOURCE_AUDIT_JSON),
            audit_markdown_path=paths.context_file(ContextFile.SOURCE_AUDIT_MARKDOWN),
            csv_path=paths.output_cheat_sheet(OutputFile.REWEIGHTED_CSV),
            teams=context.config.teams,
        )
        return StageResult(
            (
                paths.context_file(ContextFile.REWEIGHTED_JSON),
                paths.context_file(ContextFile.REWEIGHTED_MARKDOWN),
                paths.context_file(ContextFile.SOURCE_AUDIT_JSON),
                paths.context_file(ContextFile.SOURCE_AUDIT_MARKDOWN),
                paths.output_cheat_sheet(OutputFile.REWEIGHTED_CSV),
            ),
            result,
        )


class ValidationStage(PipelineStage):
    name = StageName.VALIDATION
    dependencies = (
        StageName.UNIFIED_CONTEXT,
        StageName.RANKINGS,
        StageName.SOURCE_ORDER_PDF,
    )

    def __init__(self, *, store: ArtifactStore = DEFAULT_STORE) -> None:
        self.store = store

    def run(self, context: PipelineContext) -> StageResult:
        paths = context.paths
        unified = self.store.load_object(paths.context_file(ContextFile.DRAFT_CONTEXT_JSON))
        rankings = self.store.load_object(paths.context_file(ContextFile.REWEIGHTED_JSON))
        source_audit = self.store.load_object(paths.context_file(ContextFile.SOURCE_AUDIT_JSON))
        unified_players = unified.get("players", [])
        ranked_players = rankings.get("players", [])
        value_policy = rankings.get("metadata", {}).get("round_value_highlight_policy", {})
        picks_per_round = int(value_policy.get("picks_per_round") or 0)
        minimum_value_delta = int(value_policy.get("minimum_unconstrained_value_spots") or 0)
        excluded_positions = set(value_policy.get("excluded_positions") or [])
        eligible_value_counts: dict[int, int] = {}
        selected_value_counts: dict[int, int] = {}
        for player in ranked_players:
            draft_round = int(player.get("draft_round") or 0)
            if (
                player.get("position") not in excluded_positions
                and int(player.get("unconstrained_value_delta") or 0) >= minimum_value_delta
            ):
                eligible_value_counts[draft_round] = eligible_value_counts.get(draft_round, 0) + 1
            if player.get("round_value_pick") is True:
                selected_value_counts[draft_round] = selected_value_counts.get(draft_round, 0) + 1
        checks = {
            "ranking_anomaly_audit": source_audit.get("status") == "PASS"
            and source_audit.get("ranking_anomalies", {}).get("unresolved_count") == 0,
            "unified_player_count": len(unified_players) == TOTAL_RANKED_PLAYERS,
            "unified_ranks_contiguous": [player.get("rank") for player in unified_players]
            == list(range(1, TOTAL_RANKED_PLAYERS + 1)),
            "ranking_player_count": len(ranked_players) == TOTAL_RANKED_PLAYERS,
            "ranking_ranks_contiguous": [player.get("final_rank") for player in ranked_players]
            == list(range(1, TOTAL_RANKED_PLAYERS + 1)),
            "ranking_movement_bounded": all(
                (
                    int(player["rank_delta"])
                    <= int(player["movement_cap"])
                    + int(player.get("injury_displacement_bonus") or 0)
                    if int(player["rank_delta"]) >= 0
                    else abs(int(player["rank_delta"]))
                    <= int(player["movement_cap"]) + int(player.get("injury_movement_bonus") or 0)
                )
                for player in ranked_players
            ),
            "round_value_pick_coverage": bool(eligible_value_counts)
            and all(
                selected_value_counts.get(draft_round, 0) == min(picks_per_round, eligible_count)
                for draft_round, eligible_count in eligible_value_counts.items()
            )
            and not (set(selected_value_counts) - set(eligible_value_counts)),
            "pdf_fields_complete": all(
                all(
                    key in player
                    for key in (
                        "pdf_label",
                        "offense_rank",
                        "offensive_line_rank",
                        "strength_of_schedule_rank",
                        "projected_injury_weeks",
                    )
                )
                for player in unified_players
            ),
        }
        if not all(checks.values()):
            failed = [name for name, passed in checks.items() if not passed]
            raise PipelineError(f"Pipeline validation failed: {', '.join(failed)}")
        output = paths.context_file(ContextFile.CONTEXT_VALIDATION_JSON)
        payload = {
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "status": "passed",
            "checks": checks,
        }
        self.store.write_json(output, payload)
        return StageResult((output,), {"checks": len(checks)})


class FantasyPipelineFactory:
    """Composition root for the default fantasy-football build object graph."""

    def __init__(self, *, root: Path, source_pdf: Path) -> None:
        self.paths = ProjectPaths.create(root=root, source_pdf=source_pdf)

    def create(self, config: PipelineConfig) -> ContextPipeline:
        context = PipelineContext(config=config, paths=self.paths)
        return ContextPipeline(
            context=context,
            stages=self.create_stages(config),
            manifest_path=self.paths.context_file(ContextFile.BUILD_MANIFEST_JSON),
        )

    def create_stages(self, config: PipelineConfig) -> tuple[PipelineStage, ...]:
        stages: list[PipelineStage] = [
            TeamProjectionStage(),
            ScheduleStage(),
            InjuryStage(),
            MarketStage(),
            ProjectionStage(),
            DepthChartStage(),
            SleeperConsensusStage(),
            HandcuffConsensusStage(),
            UnifiedContextStage(),
            RankingStage(),
            SourceOrderPdfStage(),
            ValidationStage(),
        ]
        return tuple(stages)


def _template_pdf_contract(
    *,
    rankings: dict[str, object],
    sleepers: dict[str, object],
    handcuffs: dict[str, object],
) -> tuple[
    dict[int, int],
    dict[int, str],
    dict[int, tuple[str, str, str, str, str]],
    dict[int, str],
]:
    players = rankings.get("players")
    if not isinstance(players, list) or len(players) != TOTAL_RANKED_PLAYERS:
        raise PipelineError("Template PDF requires the complete reweighted Top 300.")

    sleeper_names = {
        normalize_name(str(item.get("player") or ""))
        for key in ("sleepers", "rookie_breakout_candidates")
        for item in sleepers.get(key, [])
        if isinstance(item, dict) and item.get("player")
    }
    handcuff_names = {
        normalize_name(str(item.get("player") or ""))
        for item in handcuffs.get("candidates", [])
        if isinstance(item, dict) and item.get("player") and item.get("highlighted") is True
    }
    rank_mapping: dict[int, int] = {}
    position_labels: dict[int, str] = {}
    context_labels: dict[int, tuple[str, str, str, str, str]] = {}
    highlight_colors: dict[int, str] = {}
    for player in players:
        if not isinstance(player, dict):
            raise PipelineError("Template PDF ranking rows must be objects.")
        source_rank = int(player["source_rank"])
        final_rank = int(player["final_rank"])
        rank_mapping[source_rank] = final_rank
        position_labels[final_rank] = str(player["position_rank"])
        context_labels[final_rank] = (
            str(player.get("depth_chart_label") or "--"),
            str(player.get("offense_rank") or "--"),
            str(player.get("offensive_line_rank") or "--"),
            str(player.get("strength_of_schedule_rank") or "--"),
            str(player.get("injury_weeks") or "--"),
        )
        name = normalize_name(str(player.get("name") or ""))
        if name in handcuff_names:
            highlight_colors[final_rank] = HANDCUFF_HIGHLIGHT_COLOR
        elif name in sleeper_names or player.get("round_value_pick") is True:
            highlight_colors[final_rank] = SLEEPER_HIGHLIGHT_COLOR

    expected = set(range(1, TOTAL_RANKED_PLAYERS + 1))
    if set(rank_mapping) != expected or set(rank_mapping.values()) != expected:
        raise PipelineError("Template PDF ranks must map source ranks 1-300 to final ranks 1-300.")
    if set(position_labels) != expected:
        raise PipelineError("Template PDF positional labels must cover final ranks 1-300.")
    return rank_mapping, position_labels, context_labels, highlight_colors


def default_pipeline(
    *,
    root: Path,
    source_pdf: Path,
    config: PipelineConfig,
) -> ContextPipeline:
    """Compatibility facade around the object-oriented composition root."""

    return FantasyPipelineFactory(root=root, source_pdf=source_pdf).create(config)
