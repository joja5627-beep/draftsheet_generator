"""CLI facade for the object-oriented context and PDF build pipeline."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from fantasy_football_2026.build_core import PipelineError
from fantasy_football_2026.injury_context import InjuryContextError
from fantasy_football_2026.pipeline import PipelineConfig, default_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Refresh every context source and rebuild both fantasy cheat-sheet PDFs."
    )
    parser.add_argument("--pdf", type=Path, default=Path("NFL26_CS_PPR300.pdf"))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--refresh", action="store_true", help="force live source refresh")
    mode.add_argument("--offline", action="store_true", help="require cached web inputs")
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--teams", type=int, default=12)
    parser.add_argument(
        "--skip-legacy-pdf",
        action="store_true",
        help="skip rebuilding the source-order annotated PDF",
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        help="print the dependency-ordered stages without changing files",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    pipeline = default_pipeline(
        root=Path.cwd(),
        source_pdf=args.pdf,
        config=PipelineConfig(
            refresh=args.refresh,
            offline=args.offline,
            timeout=args.timeout,
            teams=args.teams,
            build_legacy_pdf=not args.skip_legacy_pdf,
        ),
    )
    if args.plan:
        print(" -> ".join(pipeline.plan()))
        return 0
    try:
        manifest = pipeline.run()
    except (InjuryContextError, PipelineError, OSError, ValueError) as error:
        raise SystemExit(f"error: {error}") from error
    print("Rebuild complete")
    print(f"Pipeline stages: {', '.join(stage['name'] for stage in manifest['stages'])}")
    print(f"Unified context: {(Path.cwd() / 'context/draft_context.json').resolve()}")
    print(
        "Reweighted PDF: "
        f"{(Path.cwd() / 'output/pdf/fantasy-football-2026-reweighted-cheat-sheet.pdf').resolve()}"
    )
    if not args.skip_legacy_pdf:
        legacy_name = f"{args.pdf.stem}-{args.teams}-team-rounds.pdf"
        print(
            "Source-order PDF: "
            f"{(Path.cwd() / 'output/pdf' / legacy_name).resolve()}"
        )
    print(f"Build manifest: {(Path.cwd() / 'context/build_manifest.json').resolve()}")
    return 0


def rebuild_all(
    *,
    source_pdf: Path,
    refresh: bool,
    offline: bool,
    timeout: float,
    teams: int,
    build_legacy_pdf: bool,
) -> dict[str, Any]:
    pipeline = default_pipeline(
        root=Path.cwd(),
        source_pdf=source_pdf,
        config=PipelineConfig(
            refresh=refresh,
            offline=offline,
            timeout=timeout,
            teams=teams,
            build_legacy_pdf=build_legacy_pdf,
        ),
    )
    manifest = pipeline.run()
    legacy_pdf = (
        Path("output/pdf") / f"{source_pdf.stem}-{teams}-team-rounds.pdf"
        if build_legacy_pdf
        else None
    )
    return {
        "stages": [stage["name"] for stage in manifest["stages"]],
        "legacy_pdf": str(legacy_pdf) if legacy_pdf is not None else None,
        "reweighted_pdf": "output/pdf/fantasy-football-2026-reweighted-cheat-sheet.pdf",
        "source_audit": "context/source_audit.json",
        "manifest": "context/build_manifest.json",
    }


if __name__ == "__main__":
    raise SystemExit(main())
