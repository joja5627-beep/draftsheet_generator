# Fantasy Football 2026 PDF Tools

This Poetry project builds a reproducible, league-adjusted fantasy-football cheat sheet
and retains the original source-order PDF annotation tool.
For a 12-team draft, overall ranks 1-12 are round 1, ranks 13-24 are round 2, and so
on through ranks 289-300 in round 25.

The default style uses clean light-blue (`#75AADB`) boundary lines and small round
labels placed in the removed salary slots. It does not shade the player rows, so names
and team depth-chart slots stay clear. Salary-cap dollar values are removed by default,
and the neighboring bye-week area is replaced by five compact columns: current Sleeper
depth-chart slot (`DC`), projected team offense rank (`OFF`), and projected offensive-
line rank (`OL`), plus position-specific fantasy strength of schedule (`SOS`, where 1 is
easiest and 32 hardest), and projected regular-season fantasy weeks missed (`INJ`). Each
value uses one coordinated, muted palette: green (`#34785B`)
for favorable ranks 1-10 or a first-string depth-chart slot, amber-yellow (`#956B1D`) for
ranks 11-22 or second string, and red (`#A84F52`) for ranks 23-32, third string or deeper,
and unavailable data. For `INJ`, green is 0 weeks, yellow is 1-2 weeks, and red is 3+
weeks or an unresolved active injury. A color index is printed above the rankings. Player
names are compacted to 4.5 pt, while the fixed five-column metric grid uses 4.1 pt condensed
bold values (3.9 pt for longer injury ranges) so all lanes remain aligned and separated.
The default output removes the source footer
and redistributes its space into larger
row gaps, with extra room around every round divider.
The source PDF remains untouched: `pdfplumber` detects the ranking rows, `reportlab`
draws the line overlay, and `pypdf` merges that overlay into a new file.

## Repository policy

The repository tracks source code, tests, the ranking model, hand-maintained overrides,
source catalogs, and research notes. It intentionally does not track third-party source
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
write the source audit and CSV, and regenerate both PDFs:

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

`rebuild_context.py` remains as a stable root-level wrapper, so
`poetry run python rebuild_context.py --refresh` is equivalent.

The rebuild order is fixed and fail-closed:

```text
schedule -> injuries -> Sleeper + ESPN depth charts -> ESPN/FantasyPros/FFToday market
         -> sleeper/rookie consensus -> unified player context
         -> source-order annotated PDF + weighted ranking model -> validation/manifest
```

Primary outputs:

- `context/draft_context.json` and `.md` - the validated, unified 300-player contract
  used by the PDF renderer; market, opportunity, offense, line, schedule, injury, and
  sleeper evidence are kept together under a stable schema
- `context/sleeper_consensus.json` and `.md` - publisher-family-deduplicated sleeper and
  rookie consensus, dynamically adjusted for current price, depth order, and injury state
- `context/reweighted_cheat_sheet.json` - complete score, component grades, evidence
  counts, rank deltas, and movement caps for all 300 rows
- `context/reweighted_cheat_sheet.md` - readable version of the complete calculation
- `context/source_audit.json` and `.md` - coverage, freshness, and unsupported-signal audit
- `output/cheat_sheet/reweighted_cheat_sheet.csv` - sortable draft-day data
- `output/pdf/fantasy-football-2026-reweighted-cheat-sheet.pdf` - the actual reordered board
  with labeled `R2`-`R25` divider lanes for a 12-team league
- `output/pdf/NFL26_CS_PPR300-12-team-rounds.pdf` - the ESPN-order annotated reference
- `context/context_validation.json` - machine-readable invariant checks for both 300-player
  datasets and every required PDF field
- `context/build_manifest.json` - stage timing, status, metrics, and SHA-256 hashes for every
  generated artifact; failed runs record the exact stage and error

The reweighted PDF highlights every current sleeper or rookie target from
`context/sleeper_consensus.json` in palette-matched yellow and includes a key on every
page. Because the PDF reads the generated consensus instead of a hard-coded name list,
the highlights update automatically on the next rebuild.

### Ranking contract

The versioned weights and movement rules live in `context/ranking_model.json`. The model
uses every normalized signal in the score:

```text
58% multi-source baseline consensus
15% replacement-distance VORP proxy
10% opportunity
 6% team offense
 4% position-adjusted offensive line
 3% coaching and continuity
 2% custom-scoring fit
 2% position-specific strength of schedule
- capped 0-5 injury and role risk
```

The order changes only when the adjusted-score difference reaches two points. Ordinary
movement is capped at 2 spots for ranks 1-24, 4 for 25-72, 8 for 73-144, and 12 after
rank 144. This keeps context from turning a modest edge into a multi-tier leap.

The current VORP input is intentionally labeled a proxy: it measures positional-rank
distance from configured replacement levels. It should be replaced with true projected
custom-scoring points only after two structured projection feeds are available.

### Source and freshness policy

- Baseline: ESPN PPR Top 300, FantasyPros half-PPR expert consensus, and FFToday's
  Underdog/Yahoo half-PPR ADP blend
- Opportunity: Sleeper depth order plus ESPN's independent team depth charts
- Injuries: Sleeper and ESPN for every player, plus dated reviewed overrides where needed
- OFF, OL, and SOS: a named calculation source plus independent tier/method cross-checks
- Player-specific role, coaching, bonus-fit, and extra-risk grades:
  `context/player_signal_overrides.json`

A player-specific manual grade is ignored unless at least two independent named sources
support that exact signal. The audit also warns after the configured 14-day freshness
window. Neutral `50` means the model has no adequately supported individualized evidence;
it is not fabricated data.

The rebuild also validates that every automated evidence group retains at least two
distinct named providers and URLs. Removing that redundancy makes the rebuild fail instead
of quietly producing a single-source ranking.

### Pipeline architecture

The reusable framework in `src/fantasy_football_2026/build_core.py` separates graph
planning, artifact inspection, manifest persistence, and execution into focused objects.
The fantasy-specific classes in `pipeline.py` implement `PipelineStage`, while
`FantasyPipelineFactory` is the composition root that assembles them. Each stage declares
an explicit name, dependencies, outputs, and metrics. The executor runs the graph in
topological order and records a manifest even when a stage fails. Its artifact and manifest
collaborators are injected through small protocols, so tests or future storage backends can
be substituted without modifying the executor.

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

To add another signal or provider, update the source adapter, register the provider in
`context/ranking_model.json`, add a test fixture, and expose its source count in the
reweighted JSON. Do not add an undocumented number directly to the PDF.

## Inspect the source sheet

```bash
poetry run fantasy-pdf inspect NFL26_CS_PPR300.pdf
```

This verifies that the tool detects ranks 1-300 and the four printed ranking columns
before it changes anything.

## Create only the source-order highlighted sheet

```bash
poetry run fantasy-rebuild --refresh
poetry run fantasy-pdf highlight-rounds NFL26_CS_PPR300.pdf
```

This also writes `context/player_depth_charts.md` and
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

## Refresh draft market and sleeper context

```bash
poetry run fantasy-market --refresh
poetry run fantasy-sleepers --refresh
```

This cross-references ESPN PPR rank, FantasyPros half-PPR expert consensus, and
FFToday's half-PPR ADP in `context/market_context.md` and
`context/market_context.json`. `context/sleeper_sources.json` is the maintainable source
catalog; article pages are cached under `context/cache/sleeper_sources/`. The generated
boards live in `context/sleeper_consensus.md` and `.json`. Their consensus counts each
publisher family once, then applies current price, depth-chart, injury, rookie status,
and league-scoring adjustments. Individual source failures are recorded, while the build
fails closed if fewer than the configured minimum number of pages are available.

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
poetry run python update_injury_context.py --refresh
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
poetry run python update_injury_context.py --offline
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

### Human-reviewed overrides

Use `context/injury_overrides.json` when a trusted report is newer or more specific than
the feeds:

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

Overrides require a games range and a written reason so manual judgment stays auditable.
Add a `sources` list with `provider`, `url`, `updated_at`, and `note` when the override
corroborates or replaces a live-feed estimate.
# draftsheet_generator
# draftsheet_generator
