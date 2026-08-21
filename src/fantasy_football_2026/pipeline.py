"""Fantasy-football stages composed with the reusable build framework."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fantasy_football_2026.build_core import (
    ContextPipeline,
    PipelineConfig,
    PipelineContext,
    PipelineError,
    PipelineStage,
    ProjectPaths,
    StageResult,
)
from fantasy_football_2026.depth_chart_context import (
    load_draft_sheet_context,
    update_depth_chart_context,
)
from fantasy_football_2026.draft_context import DraftContextBuilder, DraftContextInputs
from fantasy_football_2026.injury_context import update_injury_context
from fantasy_football_2026.market_context import update_market_context
from fantasy_football_2026.pdf_rounds import highlight_draft_rounds, reflow_draft_sheet
from fantasy_football_2026.ranking_model import update_reweighted_rankings
from fantasy_football_2026.schedule_context import update_schedule_context
from fantasy_football_2026.sleeper_consensus import (
    CachedArticleClient,
    SleeperConsensusBuilder,
)


class ScheduleStage(PipelineStage):
    name = "schedule"

    def run(self, context: PipelineContext) -> StageResult:
        paths = context.paths
        result = update_schedule_context(
            markdown_path=paths.context_file("strength_of_schedule.md"),
            json_path=paths.context_file("strength_of_schedule.json"),
            cache_path=paths.cache / "draftcall_strength_of_schedule.html",
            refresh=context.config.refresh,
            offline=context.config.offline,
            timeout=context.config.timeout,
        )
        return StageResult(
            (
                paths.context_file("strength_of_schedule.json"),
                paths.context_file("strength_of_schedule.md"),
            ),
            result,
        )


class InjuryStage(PipelineStage):
    name = "injuries"

    def run(self, context: PipelineContext) -> StageResult:
        paths = context.paths
        result = update_injury_context(
            pdf_path=paths.source_pdf,
            markdown_path=paths.context_file("player_injuries.md"),
            json_path=paths.context_file("player_injuries.json"),
            overrides_path=paths.context_file("injury_overrides.json"),
            cache_dir=paths.cache,
            refresh=context.config.refresh,
            offline=context.config.offline,
            timeout=context.config.timeout,
            reweighting_context_path=paths.context_file("gemini_research.md"),
        )
        return StageResult(
            (
                paths.context_file("player_injuries.json"),
                paths.context_file("player_injuries.md"),
            ),
            result,
        )


class MarketStage(PipelineStage):
    name = "market"

    def run(self, context: PipelineContext) -> StageResult:
        paths = context.paths
        result = update_market_context(
            pdf_path=paths.source_pdf,
            markdown_path=paths.context_file("market_context.md"),
            json_path=paths.context_file("market_context.json"),
            cache_dir=paths.cache,
            refresh=context.config.refresh,
            offline=context.config.offline,
            timeout=context.config.timeout,
        )
        return StageResult(
            (
                paths.context_file("market_context.json"),
                paths.context_file("market_context.md"),
            ),
            result,
        )


class DepthChartStage(PipelineStage):
    name = "depth-charts"
    dependencies = ("schedule", "injuries")

    def run(self, context: PipelineContext) -> StageResult:
        paths = context.paths
        result = update_depth_chart_context(
            pdf_path=paths.source_pdf,
            markdown_path=paths.context_file("player_depth_charts.md"),
            json_path=paths.context_file("player_depth_charts.json"),
            cache_dir=paths.cache,
            team_projections_path=paths.context_file("team_projections.json"),
            strength_of_schedule_path=paths.context_file("strength_of_schedule.json"),
            injury_context_path=paths.context_file("player_injuries.json"),
            refresh=context.config.refresh,
            offline=context.config.offline,
            timeout=context.config.timeout,
        )
        return StageResult(
            (
                paths.context_file("player_depth_charts.json"),
                paths.context_file("player_depth_charts.md"),
                paths.context_file("column_validation.json"),
                paths.context_file("column_validation.md"),
            ),
            result,
        )


class SleeperConsensusStage(PipelineStage):
    name = "sleeper-consensus"
    dependencies = ("market", "depth-charts", "injuries")

    def run(self, context: PipelineContext) -> StageResult:
        paths = context.paths
        builder = SleeperConsensusBuilder(
            source_catalog_path=paths.context_file("sleeper_sources.json"),
            seed_path=paths.context_file("sleepers_2026.json"),
            market_path=paths.context_file("market_context.json"),
            depth_path=paths.context_file("player_depth_charts.json"),
            injury_path=paths.context_file("player_injuries.json"),
            sleeper_players_path=paths.cache / "sleeper_players.json",
            client=CachedArticleClient(
                cache_dir=paths.cache / "sleeper_sources",
                refresh=context.config.refresh,
                offline=context.config.offline,
                timeout=context.config.timeout,
            ),
        )
        json_path = paths.context_file("sleeper_consensus.json")
        markdown_path = paths.context_file("sleeper_consensus.md")
        result = builder.build(json_path=json_path, markdown_path=markdown_path)
        return StageResult((json_path, markdown_path), result)


class UnifiedContextStage(PipelineStage):
    name = "unified-context"
    dependencies = ("market", "depth-charts", "injuries", "sleeper-consensus")

    def run(self, context: PipelineContext) -> StageResult:
        paths = context.paths
        builder = DraftContextBuilder(
            DraftContextInputs(
                market=paths.context_file("market_context.json"),
                depth=paths.context_file("player_depth_charts.json"),
                injury=paths.context_file("player_injuries.json"),
                sleepers=paths.context_file("sleeper_consensus.json"),
            )
        )
        json_path = paths.context_file("draft_context.json")
        markdown_path = paths.context_file("draft_context.md")
        result = builder.build(json_path=json_path, markdown_path=markdown_path)
        return StageResult((json_path, markdown_path), result)


class SourceOrderPdfStage(PipelineStage):
    name = "source-order-pdf"
    dependencies = ("unified-context",)

    def run(self, context: PipelineContext) -> StageResult:
        paths = context.paths
        paths.temporary.mkdir(parents=True, exist_ok=True)
        temporary = paths.temporary / f".{paths.source_pdf.stem}-expanded-layout.pdf"
        output = (
            paths.output
            / "pdf"
            / f"{paths.source_pdf.stem}-{context.config.teams}-team-rounds.pdf"
        )
        try:
            reflow_draft_sheet(paths.source_pdf, temporary, teams=context.config.teams)
            result = highlight_draft_rounds(
                temporary,
                output,
                teams=context.config.teams,
                draft_context_labels=load_draft_sheet_context(
                    paths.context_file("draft_context.json")
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
    name = "rankings"
    dependencies = ("market", "depth-charts", "injuries", "unified-context")

    def run(self, context: PipelineContext) -> StageResult:
        paths = context.paths
        pdf_path = paths.output / "pdf" / "fantasy-football-2026-reweighted-cheat-sheet.pdf"
        result = update_reweighted_rankings(
            market_path=paths.context_file("market_context.json"),
            depth_path=paths.context_file("player_depth_charts.json"),
            injury_path=paths.context_file("player_injuries.json"),
            model_path=paths.context_file("ranking_model.json"),
            overrides_path=paths.context_file("player_signal_overrides.json"),
            sleeper_context_path=paths.context_file("sleeper_consensus.json"),
            json_path=paths.context_file("reweighted_cheat_sheet.json"),
            markdown_path=paths.context_file("reweighted_cheat_sheet.md"),
            audit_json_path=paths.context_file("source_audit.json"),
            audit_markdown_path=paths.context_file("source_audit.md"),
            csv_path=paths.output / "cheat_sheet" / "reweighted_cheat_sheet.csv",
            pdf_path=pdf_path,
            teams=context.config.teams,
        )
        return StageResult(
            (
                paths.context_file("reweighted_cheat_sheet.json"),
                paths.context_file("reweighted_cheat_sheet.md"),
                paths.context_file("source_audit.json"),
                paths.context_file("source_audit.md"),
                paths.output / "cheat_sheet" / "reweighted_cheat_sheet.csv",
                pdf_path,
            ),
            result,
        )


class ValidationStage(PipelineStage):
    name = "validation"
    dependencies = ("unified-context", "rankings")

    def run(self, context: PipelineContext) -> StageResult:
        paths = context.paths
        unified = self._load(paths.context_file("draft_context.json"))
        rankings = self._load(paths.context_file("reweighted_cheat_sheet.json"))
        unified_players = unified.get("players", [])
        ranked_players = rankings.get("players", [])
        checks = {
            "unified_player_count": len(unified_players) == 300,
            "unified_ranks_contiguous": [player.get("rank") for player in unified_players]
            == list(range(1, 301)),
            "ranking_player_count": len(ranked_players) == 300,
            "ranking_ranks_contiguous": [player.get("final_rank") for player in ranked_players]
            == list(range(1, 301)),
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
        output = paths.context_file("context_validation.json")
        payload = {
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "status": "passed",
            "checks": checks,
        }
        self._write_json(output, payload)
        return StageResult((output,), {"checks": len(checks)})

    @staticmethod
    def _load(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(path)


class FantasyPipelineFactory:
    """Composition root for the default fantasy-football build object graph."""

    def __init__(self, *, root: Path, source_pdf: Path) -> None:
        self.paths = ProjectPaths.create(root=root, source_pdf=source_pdf)

    def create(self, config: PipelineConfig) -> ContextPipeline:
        context = PipelineContext(config=config, paths=self.paths)
        return ContextPipeline(
            context=context,
            stages=self.create_stages(config),
            manifest_path=self.paths.context_file("build_manifest.json"),
        )

    def create_stages(self, config: PipelineConfig) -> tuple[PipelineStage, ...]:
        stages: list[PipelineStage] = [
            ScheduleStage(),
            InjuryStage(),
            MarketStage(),
            DepthChartStage(),
            SleeperConsensusStage(),
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
