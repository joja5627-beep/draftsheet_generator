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
    TOTAL_RANKED_PLAYERS,
    CacheName,
    ContextFile,
    OutputFile,
    StageName,
)
from fantasy_football_2026.domain.draft import DraftContextBuilder, DraftContextInputs
from fantasy_football_2026.domain.rankings import update_reweighted_rankings
from fantasy_football_2026.infrastructure.storage import DEFAULT_STORE, ArtifactStore
from fantasy_football_2026.presentation.pdf import highlight_draft_rounds, reflow_draft_sheet
from fantasy_football_2026.sources.depth_charts import (
    load_draft_sheet_context,
    update_depth_chart_context,
)
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
    dependencies = (StageName.MARKET, StageName.DEPTH_CHARTS, StageName.INJURIES)

    def run(self, context: PipelineContext) -> StageResult:
        paths = context.paths
        builder = HandcuffConsensusBuilder(
            source_catalog_path=paths.context_file(ContextFile.HANDCUFF_SOURCES_JSON),
            market_path=paths.context_file(ContextFile.MARKET_JSON),
            depth_path=paths.context_file(ContextFile.PLAYER_DEPTH_JSON),
            injury_path=paths.context_file(ContextFile.INJURIES_JSON),
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
    dependencies = (StageName.UNIFIED_CONTEXT,)

    def run(self, context: PipelineContext) -> StageResult:
        paths = context.paths
        paths.temporary.mkdir(parents=True, exist_ok=True)
        temporary = paths.temporary / f".{paths.source_pdf.stem}-expanded-layout.pdf"
        output = paths.output_pdf(f"{paths.source_pdf.stem}-{context.config.teams}-team-rounds.pdf")
        try:
            reflow_draft_sheet(paths.source_pdf, temporary, teams=context.config.teams)
            result = highlight_draft_rounds(
                temporary,
                output,
                teams=context.config.teams,
                draft_context_labels=load_draft_sheet_context(
                    paths.context_file(ContextFile.DRAFT_CONTEXT_JSON)
                ),
            )
        finally:
            temporary.unlink(missing_ok=True)
        return StageResult(
            (output,),
            {
                "ranks": len(result.ranks_found),
                "rounds": len(result.rounds_found),
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
        pdf_path = paths.output_pdf(OutputFile.REWEIGHTED_PDF)
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
            pdf_path=pdf_path,
            teams=context.config.teams,
        )
        return StageResult(
            (
                paths.context_file(ContextFile.REWEIGHTED_JSON),
                paths.context_file(ContextFile.REWEIGHTED_MARKDOWN),
                paths.context_file(ContextFile.SOURCE_AUDIT_JSON),
                paths.context_file(ContextFile.SOURCE_AUDIT_MARKDOWN),
                paths.output_cheat_sheet(OutputFile.REWEIGHTED_CSV),
                pdf_path,
            ),
            result,
        )


class ValidationStage(PipelineStage):
    name = StageName.VALIDATION
    dependencies = (StageName.UNIFIED_CONTEXT, StageName.RANKINGS)

    def __init__(self, *, store: ArtifactStore = DEFAULT_STORE) -> None:
        self.store = store

    def run(self, context: PipelineContext) -> StageResult:
        paths = context.paths
        unified = self.store.load_object(paths.context_file(ContextFile.DRAFT_CONTEXT_JSON))
        rankings = self.store.load_object(paths.context_file(ContextFile.REWEIGHTED_JSON))
        unified_players = unified.get("players", [])
        ranked_players = rankings.get("players", [])
        checks = {
            "unified_player_count": len(unified_players) == TOTAL_RANKED_PLAYERS,
            "unified_ranks_contiguous": [player.get("rank") for player in unified_players]
            == list(range(1, TOTAL_RANKED_PLAYERS + 1)),
            "ranking_player_count": len(ranked_players) == TOTAL_RANKED_PLAYERS,
            "ranking_ranks_contiguous": [player.get("final_rank") for player in ranked_players]
            == list(range(1, TOTAL_RANKED_PLAYERS + 1)),
            "ranking_movement_bounded": all(
                abs(int(player["rank_delta"])) <= int(player["movement_cap"])
                for player in ranked_players
            ),
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
        ]
        if config.build_legacy_pdf:
            stages.append(SourceOrderPdfStage())
        stages.extend((RankingStage(), ValidationStage()))
        return tuple(stages)


def default_pipeline(
    *,
    root: Path,
    source_pdf: Path,
    config: PipelineConfig,
) -> ContextPipeline:
    """Compatibility facade around the object-oriented composition root."""

    return FantasyPipelineFactory(root=root, source_pdf=source_pdf).create(config)
