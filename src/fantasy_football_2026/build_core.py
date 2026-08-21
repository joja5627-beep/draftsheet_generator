"""Reusable object model for dependency-aware, auditable build pipelines."""

from __future__ import annotations

import hashlib
import json
import time
from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol


class PipelineError(RuntimeError):
    """Raised when pipeline structure or output invariants are invalid."""


@dataclass(frozen=True, slots=True)
class PipelineConfig:
    refresh: bool = False
    offline: bool = False
    timeout: float = 45.0
    teams: int = 12
    build_legacy_pdf: bool = True

    def __post_init__(self) -> None:
        if self.refresh and self.offline:
            raise ValueError("refresh and offline modes are mutually exclusive")
        if self.timeout <= 0:
            raise ValueError("timeout must be positive")
        if self.teams < 2:
            raise ValueError("teams must be at least 2")


@dataclass(frozen=True, slots=True)
class ProjectPaths:
    root: Path
    source_pdf: Path

    @classmethod
    def create(cls, *, root: Path, source_pdf: Path) -> ProjectPaths:
        resolved_root = root.resolve()
        resolved_pdf = source_pdf if source_pdf.is_absolute() else resolved_root / source_pdf
        return cls(root=resolved_root, source_pdf=resolved_pdf.resolve())

    @property
    def context(self) -> Path:
        return self.root / "context"

    @property
    def cache(self) -> Path:
        return self.context / "cache"

    @property
    def output(self) -> Path:
        return self.root / "output"

    @property
    def temporary(self) -> Path:
        return self.root / "tmp" / "pdfs"

    def context_file(self, name: str) -> Path:
        return self.context / name


@dataclass(frozen=True, slots=True)
class PipelineContext:
    config: PipelineConfig
    paths: ProjectPaths


@dataclass(frozen=True, slots=True)
class StageResult:
    """Outputs and measurements returned by one stage.

    The stage owns its name, so the result intentionally does not duplicate it.
    """

    outputs: tuple[Path, ...]
    metrics: dict[str, Any] = field(default_factory=dict)


class PipelineStage(ABC):
    """A named build unit with explicit dependencies and output files."""

    name: str
    dependencies: tuple[str, ...] = ()

    @abstractmethod
    def run(self, context: PipelineContext) -> StageResult:
        raise NotImplementedError


class StageGraph:
    """Validate stage relationships and expose a stable topological order."""

    def __init__(self, stages: Iterable[PipelineStage]) -> None:
        self._stages = tuple(stages)
        self._stage_by_name = {stage.name: stage for stage in self._stages}
        self._validate()
        self._ordered = self._topological_order()

    @property
    def ordered_stages(self) -> tuple[PipelineStage, ...]:
        return self._ordered

    @property
    def stage_names(self) -> tuple[str, ...]:
        return tuple(stage.name for stage in self._ordered)

    def _validate(self) -> None:
        if len(self._stage_by_name) != len(self._stages):
            raise ValueError("Pipeline stage names must be unique")
        known = set(self._stage_by_name)
        for stage in self._stages:
            missing = set(stage.dependencies) - known
            if missing:
                raise ValueError(
                    f"Stage {stage.name} has unknown dependencies: {sorted(missing)}"
                )

    def _topological_order(self) -> tuple[PipelineStage, ...]:
        completed: set[str] = set()
        ordered: list[PipelineStage] = []
        remaining = list(self._stages)
        while remaining:
            ready = [stage for stage in remaining if set(stage.dependencies) <= completed]
            if not ready:
                unresolved = {stage.name: stage.dependencies for stage in remaining}
                raise ValueError(f"Pipeline contains a dependency cycle: {unresolved}")
            for stage in ready:
                ordered.append(stage)
                completed.add(stage.name)
                remaining.remove(stage)
        return tuple(ordered)


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    path: str
    exists: bool
    size: int | None
    sha256: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ArtifactInspector:
    """Describe and hash build artifacts relative to one project root."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def inspect(self, path: Path) -> ArtifactRecord:
        resolved = path.resolve()
        try:
            display = str(resolved.relative_to(self.root))
        except ValueError:
            display = str(resolved)
        if not resolved.is_file():
            return ArtifactRecord(display, False, None, None)
        digest = hashlib.sha256()
        with resolved.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return ArtifactRecord(
            path=display,
            exists=True,
            size=resolved.stat().st_size,
            sha256=digest.hexdigest(),
        )


class ArtifactInspection(Protocol):
    """Port used by the executor to inspect generated files."""

    def inspect(self, path: Path) -> ArtifactRecord: ...


@dataclass(frozen=True, slots=True)
class StageRecord:
    name: str
    dependencies: tuple[str, ...]
    status: str
    duration_seconds: float
    metrics: dict[str, Any]
    outputs: tuple[ArtifactRecord, ...]
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if self.error is None:
            payload.pop("error")
        return payload


class ManifestRepository:
    """Persist the latest build result atomically."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def save(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)


class ManifestSink(Protocol):
    """Persistence port used by the executor for its final manifest."""

    def save(self, payload: dict[str, Any]) -> None: ...


class ContextPipeline:
    """Coordinate a validated graph while delegating storage and inspection."""

    def __init__(
        self,
        *,
        context: PipelineContext,
        stages: Iterable[PipelineStage],
        manifest_path: Path | None = None,
        artifact_inspector: ArtifactInspection | None = None,
        manifest_repository: ManifestSink | None = None,
    ) -> None:
        self.context = context
        self.graph = StageGraph(stages)
        self.artifacts = artifact_inspector or ArtifactInspector(context.paths.root)
        if manifest_repository is None and manifest_path is None:
            raise ValueError("manifest_path is required when no manifest repository is injected")
        if manifest_repository is not None:
            self.manifests = manifest_repository
        else:
            assert manifest_path is not None
            self.manifests = ManifestRepository(manifest_path)

    def plan(self) -> tuple[str, ...]:
        return self.graph.stage_names

    def run(self) -> dict[str, Any]:
        if not self.context.paths.source_pdf.is_file():
            raise PipelineError(f"Source PDF does not exist: {self.context.paths.source_pdf}")

        records: list[StageRecord] = []
        started_at = datetime.now(UTC).isoformat(timespec="seconds")
        status = "passed"
        error_message: str | None = None
        active_stage: PipelineStage | None = None
        active_started = 0.0
        try:
            for stage in self.graph.ordered_stages:
                active_stage = stage
                active_started = time.monotonic()
                result = stage.run(self.context)
                missing = [str(path) for path in result.outputs if not path.is_file()]
                if missing:
                    raise PipelineError(
                        f"Stage {stage.name} did not create expected outputs: "
                        f"{', '.join(missing)}"
                    )
                records.append(
                    StageRecord(
                        name=stage.name,
                        dependencies=stage.dependencies,
                        status="passed",
                        duration_seconds=round(time.monotonic() - active_started, 3),
                        metrics=result.metrics,
                        outputs=tuple(self.artifacts.inspect(path) for path in result.outputs),
                    )
                )
                active_stage = None
        except Exception as error:
            status = "failed"
            error_message = f"{type(error).__name__}: {error}"
            if active_stage is not None:
                records.append(
                    StageRecord(
                        name=active_stage.name,
                        dependencies=active_stage.dependencies,
                        status="failed",
                        duration_seconds=round(time.monotonic() - active_started, 3),
                        metrics={},
                        outputs=(),
                        error=error_message,
                    )
                )
            raise
        finally:
            manifest = {
                "schema_version": "1.0.0",
                "started_at": started_at,
                "finished_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "status": status,
                "error": error_message,
                "source_pdf": self.artifacts.inspect(
                    self.context.paths.source_pdf
                ).to_dict(),
                "config": asdict(self.context.config),
                "planned_stages": list(self.plan()),
                "stages": [record.to_dict() for record in records],
            }
            self.manifests.save(manifest)
        return manifest
