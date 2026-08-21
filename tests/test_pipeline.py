import json
from pathlib import Path
from typing import Any

import pytest

from fantasy_football_2026.draft_context import DraftContextBuilder, DraftContextInputs
from fantasy_football_2026.pipeline import (
    ContextPipeline,
    PipelineConfig,
    PipelineContext,
    PipelineStage,
    ProjectPaths,
    StageResult,
)
from fantasy_football_2026.sleeper_consensus import (
    ArticleCandidateExtractor,
    SleeperSource,
)

GENERATED_CONTEXT = (
    Path("context/market_context.json"),
    Path("context/player_depth_charts.json"),
    Path("context/player_injuries.json"),
)
requires_generated_context = pytest.mark.skipif(
    not all(path.is_file() for path in GENERATED_CONTEXT),
    reason="requires generated draft context",
)


class _FileStage(PipelineStage):
    def __init__(self, name: str, output: Path, dependencies: tuple[str, ...] = ()) -> None:
        self.name = name
        self.output = output
        self.dependencies = dependencies

    def run(self, context: PipelineContext) -> StageResult:
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.output.write_text(self.name, encoding="utf-8")
        return StageResult((self.output,), {"written": 1})


class _FailingStage(PipelineStage):
    name = "failing"

    def run(self, context: PipelineContext) -> StageResult:
        raise RuntimeError("fixture failure")


class _CapturingManifest:
    def __init__(self) -> None:
        self.payload: dict[str, Any] | None = None

    def save(self, payload: dict[str, Any]) -> None:
        self.payload = payload


def test_pipeline_orders_dependencies_and_hashes_outputs(tmp_path: Path) -> None:
    source_pdf = tmp_path / "source.pdf"
    source_pdf.write_bytes(b"source")
    paths = ProjectPaths.create(root=tmp_path, source_pdf=source_pdf)
    first = _FileStage("first", tmp_path / "first.json")
    second = _FileStage("second", tmp_path / "second.json", ("first",))
    pipeline = ContextPipeline(
        context=PipelineContext(PipelineConfig(), paths),
        stages=(second, first),
        manifest_path=tmp_path / "manifest.json",
    )

    assert pipeline.plan() == ("first", "second")
    manifest = pipeline.run()

    assert manifest["status"] == "passed"
    assert [stage["name"] for stage in manifest["stages"]] == ["first", "second"]
    assert all(stage["outputs"][0]["sha256"] for stage in manifest["stages"])
    assert json.loads((tmp_path / "manifest.json").read_text())["status"] == "passed"


def test_pipeline_rejects_unknown_dependency(tmp_path: Path) -> None:
    source_pdf = tmp_path / "source.pdf"
    source_pdf.write_bytes(b"source")
    paths = ProjectPaths.create(root=tmp_path, source_pdf=source_pdf)

    with pytest.raises(ValueError, match="unknown dependencies"):
        ContextPipeline(
            context=PipelineContext(PipelineConfig(), paths),
            stages=(_FileStage("broken", tmp_path / "x", ("missing",)),),
            manifest_path=tmp_path / "manifest.json",
        )


def test_pipeline_rejects_dependency_cycles(tmp_path: Path) -> None:
    source_pdf = tmp_path / "source.pdf"
    source_pdf.write_bytes(b"source")
    paths = ProjectPaths.create(root=tmp_path, source_pdf=source_pdf)

    with pytest.raises(ValueError, match="dependency cycle"):
        ContextPipeline(
            context=PipelineContext(PipelineConfig(), paths),
            stages=(
                _FileStage("first", tmp_path / "first", ("second",)),
                _FileStage("second", tmp_path / "second", ("first",)),
            ),
            manifest_path=tmp_path / "manifest.json",
        )


def test_pipeline_persists_failed_stage_record(tmp_path: Path) -> None:
    source_pdf = tmp_path / "source.pdf"
    source_pdf.write_bytes(b"source")
    paths = ProjectPaths.create(root=tmp_path, source_pdf=source_pdf)
    pipeline = ContextPipeline(
        context=PipelineContext(PipelineConfig(), paths),
        stages=(_FailingStage(),),
        manifest_path=tmp_path / "manifest.json",
    )

    with pytest.raises(RuntimeError, match="fixture failure"):
        pipeline.run()

    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["status"] == "failed"
    assert manifest["stages"] == [
        {
            "dependencies": [],
            "duration_seconds": manifest["stages"][0]["duration_seconds"],
            "error": "RuntimeError: fixture failure",
            "metrics": {},
            "name": "failing",
            "outputs": [],
            "status": "failed",
        }
    ]


def test_pipeline_accepts_injected_manifest_sink(tmp_path: Path) -> None:
    source_pdf = tmp_path / "source.pdf"
    source_pdf.write_bytes(b"source")
    output = tmp_path / "output.json"
    paths = ProjectPaths.create(root=tmp_path, source_pdf=source_pdf)
    sink = _CapturingManifest()
    pipeline = ContextPipeline(
        context=PipelineContext(PipelineConfig(), paths),
        stages=(_FileStage("only", output),),
        manifest_repository=sink,
    )

    manifest = pipeline.run()

    assert sink.payload == manifest
    assert manifest["status"] == "passed"


def test_article_extractor_discovers_player_headings() -> None:
    extractor = ArticleCandidateExtractor(("Denzel Boston", "Jonah Coleman"))
    source = SleeperSource(
        source_id="fixture",
        family="fixture",
        url="https://example.test/article",
        mode="headings",
        players=(),
        required=True,
    )

    found = extractor.extract(
        source,
        "<article><h2>Denzel Boston, Cleveland Browns</h2>"
        "<p>Jonah Coleman is mentioned only in body copy.</p></article>",
    )

    assert found == ("Denzel Boston",)


@requires_generated_context
def test_unified_context_joins_all_real_player_inputs(tmp_path: Path) -> None:
    builder = DraftContextBuilder(
        DraftContextInputs(
            market=Path("context/market_context.json"),
            depth=Path("context/player_depth_charts.json"),
            injury=Path("context/player_injuries.json"),
            sleepers=Path("context/sleepers_2026.json"),
        )
    )

    result = builder.build(
        json_path=tmp_path / "draft_context.json",
        markdown_path=tmp_path / "draft_context.md",
    )
    payload = json.loads((tmp_path / "draft_context.json").read_text())

    assert result["player_count"] == 300
    assert [player["rank"] for player in payload["players"]] == list(range(1, 301))
    assert all("market" in player and "injury" in player for player in payload["players"])
