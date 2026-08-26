# Fantasy Football 2026 PDF Tools

This Poetry project builds a reproducible, league-adjusted fantasy-football cheat sheet by
reusing the original ESPN Top 300 design. The source PDF stays untouched; the generated
two-page, double-sided copy reorders its player rows using the custom model and adds live
context. Each side uses two wider 75-player columns for draft-day readability.
Overall and parenthesized positional ranks are both recalculated from that final order.
For a 12-team draft, overall ranks 1-12 are round 1, ranks 13-24 are round 2, and so
on through ranks 289-300 in round 25.

The default style uses clean light-blue (`#75AADB`) boundary lines and small round
labels placed in the removed salary slots. It does not shade entire draft rounds; only
automated target rows receive the pale yellow or lavender fills. Salary-cap dollar values are
removed by default, and every ranking column is divided into contiguous lanes that use its
full printable width. The compact rank lane shifts player names left, while the expanded and
larger-type context lanes remove the unused gap before the added data. A signed movement
column (`MOV`) shows each player's change from the
seven-source consensus anchor (`+` means promoted, `-` means demoted, and `0` means unchanged).
It is followed by five compact context columns: current Sleeper depth-chart slot (`DC`),
projected team offense rank (`OFF`), and projected offensive-line rank (`OL`), plus
position-specific fantasy strength of schedule (`SOS`, where 1 is easiest and 32 hardest),
and projected regular-season fantasy weeks missed (`INJ`). Each
value uses one coordinated, muted palette: green (`#34785B`)
for favorable ranks 1-10 or a first-string depth-chart slot, amber-yellow (`#956B1D`) for
ranks 11-22 or second string, and red (`#A84F52`) for ranks 23-32, third string or deeper,
and unavailable data. For `INJ`, green is 0 weeks, yellow is 1-2 weeks, and red is 3+
weeks or an unresolved active injury. A color index is printed above the rankings. Player
names are compacted to 4.5 pt, while the fixed context metric grid uses 4.1 pt condensed
bold values (3.9 pt for longer injury ranges) so all lanes remain aligned and separated.
The default output removes the source footer
and redistributes its space into larger
row gaps, with extra room around every round divider.
The source PDF remains untouched: `pdfplumber` detects the ranking rows, `reportlab`
redraws them in custom-rank order and adds the context/highlight overlays, and `pypdf`
merges those layers into a new file that retains the ESPN template.

## Repository policy

The repository tracks source code, tests, the ranking model, source catalogs, and research
notes. Historical override and seed files are retained for provenance but are inactive in
the default automated rebuild. It intentionally does not track third-party source
PDFs, downloaded caches, or generated context/output artifacts. This keeps clones small,
avoids publishing third-party draft-kit material, and prevents generated metadata from
capturing machine-specific paths.

The test suite uses synthetic PDF fixtures by default. Tests that validate the real ESPN
sheet or generated context skip automatically when those local artifacts are absent.

## Setup

```bash
git clone <repository-url>
cd fantasy_football_2026
poetry install
```

Download the 2026 ESPN PPR Top 300 into the repository root before running the complete
pipeline. Review and comply with the publisher's terms before downloading or using it.

```bash
curl --fail --location \
  'https://g.espncdn.com/s/ffldraftkit/26/NFL26_CS_PPR300.pdf?adddata=2026CS_PPR300' \
  --output NFL26_CS_PPR300.pdf
```

Validate a source checkout without private caches or generated artifacts:

```bash
poetry run ruff check .
poetry run pytest
poetry build
```

## One-command rebuild

Refresh every automated source, rebuild the normalized context, reweight the Top 300,
write the source audit and CSV, and regenerate the ESPN-template PDF:

```bash
poetry run fantasy-rebuild --refresh
```

After one successful live refresh, the exact same pipeline can be tested from cached
inputs without network access:

```bash
poetry run fantasy-rebuild --offline
```

Preview the dependency-ordered work without changing files:

```bash
poetry run fantasy-rebuild --plan
```

The compatibility wrapper lives with the other maintenance utilities, so
`poetry run python scripts/rebuild_context.py --refresh` is equivalent.

The rebuild order is fixed and fail-closed:

```text
team offense/OL -> schedule -> injuries -> Sleeper + ESPN depth charts
         -> seven-source expert/market consensus
         -> ESPN Mike Clay + FFToday raw-stat projection ensemble
         -> sleeper/rookie consensus + RB handcuff consensus -> unified player context
         -> weighted ranking model -> reordered ESPN-template PDF -> validation/manifest
```

Primary outputs:

- `context/draft_context.json` and `.md` - the validated, unified 300-player contract
  used by the PDF renderer; market, opportunity, offense, line, schedule, injury, and
  sleeper evidence are kept together under a stable schema
- `context/sleeper_consensus.json` and `.md` - publisher-family-deduplicated sleeper and
  rookie consensus, dynamically adjusted for current price, depth order, and injury state
- `context/handcuff_consensus.json` and `.md` - publisher-family-deduplicated RB handcuff
  candidates verified against the refreshed live depth chart and injury context
- `context/projection_context.json` and `.md` - league-scored ESPN/FFToday projection
  ensemble, replacement baselines, source coverage, and player-level projected value
- `context/weighting_strategy_research.md` - evidence review, alternatives, selected
  heuristic, assumptions, and limitations
- `context/reweighted_cheat_sheet.json` - complete score, component grades, evidence
  counts, rank deltas, and movement caps for all 300 rows
- `context/reweighted_cheat_sheet.md` - readable version of the complete calculation
- `context/source_audit.json` and `.md` - coverage, freshness, and unsupported-signal audit
- `output/cheat_sheet/reweighted_cheat_sheet.csv` - sortable draft-day data
- `output/pdf/fantasy-football-2026-reweighted-cheat-sheet.pdf` - the primary two-page,
  double-sided deliverable: the original ESPN design with rows moved into custom-rank order, labeled
  `R2`-`R25` divider lanes, five context columns, and target highlights
- `output/pdf/NFL26_CS_PPR300-12-team-rounds.pdf` - an identical compatibility copy under
  the earlier source-derived filename
- `context/context_validation.json` - machine-readable invariant checks for both 300-player
  datasets and every required PDF field
- `context/build_manifest.json` - stage timing, status, metrics, and SHA-256 hashes for every
  generated artifact; failed runs record the exact stage and error

The reweighted ESPN-template PDF uses palette-matched yellow for every current sleeper or rookie target from
`context/sleeper_consensus.json` and for one automated value pick in each draft round. A round
value is the non-kicker/non-defense player with the largest positive gap between the blended
consensus anchor and the rank supported by the complete adjusted score. The model stores the
score-supported rank, value delta, draft round, and selection flag in the generated JSON and
CSV so every yellow value designation is auditable and refreshes on the next rebuild.

Eligible running back handcuffs from `context/handcuff_consensus.json` remain pale lavender.
Both keys appear in the legend on each side. Handcuffs require current RB2 status, candidate health,
mentions from at least two independent publisher families, and no more than 30% of the
starter-plus-candidate projected fantasy points. That workload gate keeps committee backs,
RB3s, and unresolved roles in the generated watchlist without a highlight. If a player
qualifies for both yellow and handcuff categories, lavender takes precedence so the handcuff
role stays visible. No highlight category depends on a hard-coded player list.

### Ranking contract

The versioned weights and movement rules live in `context/ranking_model.json`. The model
uses every normalized signal in the score:

```text
60% custom-scored ensemble value over baseline
30% multi-source baseline consensus
 5% opportunity
 2% team offense
 2% position-adjusted offensive line
 1% position-specific strength of schedule
- availability-adjusted projections plus capped 0-8 residual injury risk
```

The equal-source mean of ESPN, FantasyPros, FFToday, RotoBaller, Fantasy Football Calculator,
LineupBeat, and Pro Football Mania establishes the baseline order and movement anchor; ESPN
remains only the deterministic tie-breaker and lineage reference. The order
normally changes only when the adjusted-score difference reaches two points.
One deterministic tiebreaker corrects same-team QB, RB, or TE role inversions when the
better depth-chart role has an equal or higher adjusted score. It never forces a starter over a
more valuable backup, and it still respects both players' movement caps. Ordinary movement
is capped at 2 spots for ranks 1-24, 4 for 25-72, 8 for 73-144, and 12 after rank 144. This
keeps context from turning a modest edge into a multi-tier leap.

Round-value highlighting separately sorts the complete board by adjusted score without
movement caps, compares that score-supported rank with the consensus anchor, and selects the
largest positive discount within each 12-player round. It does not change player ordering or
the weighting strategy; it exposes the strongest existing model-versus-market value signal at
each stage of the draft. Kickers and defenses are excluded from this designation.

Injuries use confidence-weighted expected games missed to reduce the projected-value grade
and add a bounded residual penalty. A multi-game absence corroborated by both injury providers
can expand only the player's downside movement cap, at four additional spots per expected game
and no more than 24 ordinary bonus spots. A corroborated absence of at least five projected
games can fall to the rank supported by its availability-adjusted score, including through the
full board for a season-long absence. Players below such an absence receive only the passive
promotion allowance needed to fill that vacancy; it is tracked separately from ordinary model
movement. Single-source signals never receive either cap exception.

The projected-value input averages ESPN Mike Clay and FFToday raw statistics, scores the
result from the supplied league rules, simulates RB/WR starter and flex demand, and applies
the research-backed median-starter correction at QB and TE. The supplied rules do not state
roster slots, so the 12-team 1QB/2RB/2WR/1TE/1FLEX assumption remains explicit and editable.
See `context/weighting_strategy_research.md` for the comparison and evidence boundaries.

### Source and freshness policy

- Baseline: simple mean of every available rank from ESPN, FantasyPros, FFToday, RotoBaller,
  Fantasy Football Calculator, LineupBeat, and Pro Football Mania. The source median and range
  feed an automated unresolved-anomaly validation gate.
- Projected value: simple mean of ESPN Mike Clay and FFToday raw-stat projections,
  rescored from the league export on each rebuild
- Opportunity: Sleeper depth order plus ESPN's independent team depth charts
- Injuries: Sleeper and ESPN for every player; manual overrides are disabled by default
- OFF, OL, and SOS: a named calculation source plus independent tier/method cross-checks
- OFF and OL are fetched and parsed by the `team-projections` stage on every live refresh.
- Player-specific role, coaching, bonus-fit, and extra-risk overrides are not ranking inputs.

The rebuild also validates that every configured evidence group retains at least two
distinct named providers and URLs. Removing that redundancy makes the rebuild fail instead
of quietly producing a single-source ranking.

### Pipeline architecture

The source and test trees mirror the application's architectural boundaries:

```text
src/fantasy_football_2026/
├── application/      # pipeline framework, stage composition, rebuild command
├── consensus/        # shared publisher ingestion, sleepers, RB handcuffs
├── domain/           # normalization, unified draft context, ranking model
├── infrastructure/   # atomic artifact storage and cached HTTP client
├── presentation/     # column buckets and PDF rendering
├── sources/          # injuries, depth charts, market, projections, schedule, teams
├── cli.py            # public PDF command
├── constants.py      # stable configuration values
└── errors.py         # application exception hierarchy
```

`scripts/` contains thin maintenance wrappers, while `context/` contains source inputs and
generated context, `output/` contains build products, and `tests/` mirrors the package
layers. The source PDF remains at the repository root because it is the default build input.

The reusable framework in `application/core.py` separates graph planning, artifact
inspection, manifest persistence, and execution into focused objects. The fantasy-specific
classes in `application/pipeline.py` implement `PipelineStage`, while
`FantasyPipelineFactory` is the composition root that assembles them. Each stage declares an
explicit name, dependencies, outputs, and metrics. The executor runs the graph in topological
order and records a manifest even when a stage fails. Its artifact and manifest collaborators
are injected through small protocols, so tests or future storage backends can be substituted
without modifying the executor.

Stable configuration strings are centralized in the package-root `constants.py`: artifact filenames,
pipeline stage IDs, source URLs, NFL team/name aliases, cache names, and PDF colors. Domain
prose, JSON field names, and parser tokens remain beside the behavior that owns them so the
constants module does not become an untyped dumping ground. `ArtifactStore` provides the
single atomic JSON/text persistence boundary, while `CachedWebClient` provides consistent
refresh, offline, current-day, stale-on-error, and payload-validation behavior. Both are
injectable classes with narrow responsibilities.

Publisher-backed sleeper and handcuff features share the source, article, normalization,
and cache abstractions in `consensus/common.py`; each builder retains only its own scoring and
eligibility rules. Generic name and team normalization lives in `domain/normalization.py`,
and the application exception hierarchy lives in the package-root `errors.py`. This avoids
importing private helpers from a feature module and keeps dependencies pointed toward
reusable infrastructure.

`DraftContextBuilder` owns the player-level join. Its immutable `MarketSignals`,
`OpportunitySignals`, `InjurySignals`, and `DraftPlayerContext` value objects define the
schema in code and reject missing ranks or mismatched player/team identities before either
PDF can consume the data. Serialization is kept at the document boundary.

Adding a future data source normally means implementing one focused stage or adapter,
declaring its dependency, returning its output files in `StageResult`, and registering it
in `FantasyPipelineFactory`. The executor, graph planner, artifact hashing, and manifest
storage remain closed to that change. New normalized fields belong in a typed value object
and are joined by `DraftContextBuilder`. This keeps fetching, normalization, rendering,
and validation separate and independently testable.

The package uses Poetry's PEP 517/PEP 621 configuration with a `src/` layout, a typed-package
marker, a single metadata-derived package version, locked runtime dependencies, and isolated
development dependencies. The standard local quality gate is:

```bash
poetry check
poetry run ruff format --check .
poetry run ruff check .
poetry run pytest
poetry build
```

To add another signal or provider, update the source adapter, register the provider in
`context/ranking_model.json`, add a test fixture, and expose its source count in the
reweighted JSON. Do not add an undocumented number directly to the PDF.

## Inspect the source sheet

```bash
poetry run fantasy-pdf inspect NFL26_CS_PPR300.pdf
```

This verifies that the tool detects ranks 1-300 and the four printed ranking columns
before it changes anything.

## Create a source-order context-only sheet

```bash
poetry run fantasy-rebuild --refresh
poetry run fantasy-pdf highlight-rounds NFL26_CS_PPR300.pdf
```

The standalone `fantasy-pdf` command keeps ESPN order and only adds context. The full
`fantasy-rebuild` pipeline instead moves the same source rows into custom-rank order. The
standalone workflow also refreshes `context/team_projections.json`, then writes
`context/player_depth_charts.md` and
`context/player_depth_charts.json`, merging the dated team rankings in
`context/team_projections.json` and the position-specific schedule ranks in
`context/strength_of_schedule.json`, plus the injury-week labels in
`context/player_injuries.json`. Displayed sources and their cross-checks are documented
in `context/column_validation.md` and machine-readable `context/column_validation.json`;
incompatible methodologies and material disagreements are preserved rather than averaged
into a false consensus. The schedule updater also preserves the raw opponent
fantasy-point averages, playoff ranks, retrieval date, methodology, caveat, and source
links in JSON and `context/strength_of_schedule.md` for later reweighting. Add
`--keep-dollar-column` to restore salary values, or `--keep-bye-week` to preserve the
source bye weeks. Use `--keep-footer-layout` only when you specifically want the original
compact footer layout.

The default output is:

```text
output/pdf/NFL26_CS_PPR300-12-team-rounds.pdf
```

## Refresh draft market, sleeper, and handcuff context

```bash
poetry run fantasy-market --refresh
poetry run fantasy-sleepers --refresh
poetry run fantasy-handcuffs --refresh
```

This cross-references all seven expert and market ranks in `context/market_context.md` and
`context/market_context.json`. `context/sleeper_sources.json` is the maintainable source
catalog; article pages are cached under `context/cache/sleeper_sources/`. The generated
boards live in `context/sleeper_consensus.md` and `.json`. Their consensus counts each
publisher family once, then applies current price, depth-chart, injury, rookie status,
and league-scoring adjustments. Individual source failures are recorded, while the build
fails closed if fewer than the configured minimum number of pages are available.

`context/handcuff_sources.json` maintains the independent handcuff source catalog. Pages
are cached under `context/cache/handcuff_sources/`, and the builder deduplicates publisher
families before checking every mentioned player against the automated RB depth and injury
feeds. It also checks league-scored projections and only promotes backs projected for 30% or
less of the top-two backfield points; larger shares are treated as committee profiles. Its
generated board lives in `context/handcuff_consensus.md` and `.json` and follows the same
fail-closed source-coverage policy.

To adjust the league size or line color:

```bash
poetry run fantasy-pdf highlight-rounds NFL26_CS_PPR300.pdf \
  --teams 10 \
  --color '#79A9D1'
```

## Development checks

```bash
poetry run pytest
poetry run ruff check .
```

## Refresh player injury context

The root-level updater extracts all 300 ranked entities from the source PDF, matches NFL
players against Sleeper and ESPN, maps reported expected-return dates to each player's
regular-season schedule, and writes both readable and machine-readable context:

```bash
poetry run python scripts/update_injury_context.py --refresh
```

Outputs:

- `context/player_injuries.md` - complete ranked table, risk tiers, evidence links, and
  methodology
- `context/player_injuries.json` - structured version for future PDF or draft-board tools
- `context/player_depth_charts.json` - the merged five-column PDF context, including each
  player's `projected_injury_weeks` label and color bucket
- `context/gemini_research.md` - its generated injury-reweighting block is refreshed with
  availability factors, fallback penalties, and the current material watchlist

The reweighting update uses the existing 0-5 total risk cap. If a baseline projection
does not include a reported absence, it applies `(17 - projected games missed) / 17`
before recalculating VORP. If the baseline already includes the absence, it does not apply
the adjustment twice. Use `--skip-reweighting-context` when only the standalone injury
files should be refreshed.

The daily source cache lives under the ignored `context/cache/` directory. To rebuild
without network access after at least one successful refresh:

```bash
poetry run python scripts/update_injury_context.py --offline
```

The risk score describes current reported regular-season availability, not the chance of
a new future injury:

- `0 CLEAR`: no current absence projected
- `1 WATCH`: zero to one game
- `2 SHORT`: two games
- `3 MEDIUM`: three to four games
- `4 HIGH`: five to eight games
- `5 VERY HIGH`: nine to sixteen games
- `6 SEASON`: seventeen games

Preseason Questionable, Out, PUP, and NFI labels intentionally use broader ranges because
final roster designations and Week 1 injury reports may not yet exist.

### Optional manual injury override (not used by `fantasy-rebuild`)

The default rebuild is automated-only. For a one-off diagnostic, `fantasy-injuries` can
explicitly opt into `context/injury_overrides.json` when a trusted report is newer or more
specific than the feeds:

```bash
poetry run fantasy-injuries --overrides context/injury_overrides.json --refresh
```

The optional file format is:

```json
{
  "players": {
    "Example Player": {
      "games_min": 2,
      "games_max": 4,
      "confidence": "high",
      "reason": "Team announced a 2-4 game absence on 2026-08-21."
    }
  }
}
```

Overrides require a games range and a written reason so an opt-in manual run stays auditable.
Add a `sources` list with `provider`, `url`, `updated_at`, and `note` when the override
corroborates or replaces a live-feed estimate.
# draftsheet_generator
# draftsheet_generator
