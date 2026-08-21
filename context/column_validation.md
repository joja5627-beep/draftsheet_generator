# Draft-sheet column cross-reference validation

**Effective date:** August 21, 2026

This audit verifies the five data families displayed on the PDF. The named primary
source supplies the displayed value; independent sources validate direction and tier.
Values from incompatible methods are not averaged into a false-precision consensus.
Machine-readable results are in [`column_validation.json`](./column_validation.json).

## Color index

The three colors share one muted, contrast-safe palette:

| Bucket | Color | Rank columns (`OFF`, `OL`, `SOS`) | Depth chart (`DC`) | Injury (`INJ`) |
| --- | :---: | --- | --- | --- |
| Favorable | `#34785B` green | 1-10 | Order 1 or D/ST | 0 weeks or D/ST N/A |
| Middle | `#956B1D` amber-yellow | 11-22 | Order 2 | 1-2 weeks |
| Caution | `#A84F52` red | 23-32 or unavailable | Order 3+ or unavailable | 3+ weeks or unresolved |

The colors summarize the displayed primary value. They do not claim that every source
agrees, and they do not change the underlying rank.

## Cross-reference results

### DC - depth chart

- **Primary:** [Sleeper NFL player API](https://api.sleeper.app/v1/players/nfl?active=true),
  retrieved August 21.
- **Checks:** [ESPN fantasy depth chart](https://g.espncdn.com/s/ffldraftkit/26/NFL26_CS_Depth.pdf?adddata=2026CS_Depth)
  and [ESPN all-team NFL depth charts](https://www.espn.com/nfl/story/_/id/29098001/nfl-depth-charts-all-32-teams),
  both dated August 19.
- **Result:** 227 of 260 eligible QB/RB/WR/TE rows have the same order, 31 differ, and
  two ranked players are absent from ESPN's one-page chart. ESPN explicitly says its
  chart orders players by fantasy value and may not match an NFL team's depth-chart
  slot. Sleeper remains primary because it preserves roster alignment such as `LWR`,
  `RWR`, and `SWR`; every disagreement is listed in the JSON audit.

### OFF - projected offense

- **Primary:** [First Down Studio's August 20 Vegas implied totals](https://www.firstdown.studio/implied-totals/season).
- **Check:** [Mike Clay's August 19 projection guide](https://g.espncdn.com/s/ffldraftkit/26/NFLDK2026_CS_ClayProjections2026.pdf).
- **Result:** rank correlation is **0.924**, and 24 of 32 teams land in the same color
  bucket. Eight boundary disagreements are retained. The market-implied rank remains
  primary because `OFF` is defined as expected scoring environment.

### OL - projected offensive line

- **Primary:** [Sharp Football Analysis](https://www.sharpfootballanalysis.com/analysis/best-nfl-offensive-line-rankings/),
  dated June 30, combining staff film, statistics, and projections.
- **Checks:** [4for4's June 22 expected-personnel/PFF model](https://www.4for4.com/2026/preseason/2026-projected-offensive-line-rankings)
  and ESPN's August 19 OL unit grades/projected starters in Mike Clay's guide.
- **Result:** Sharp shares the same tier with 4for4 for 18 of 32 teams and with ESPN for
  21 of 32. The disagreement is real and method-driven, so the Sharp rank stays labeled
  as a projection rather than being averaged with unlike models.

### SOS - opposing-defense schedule

- **Primary:** [DraftCall](https://draftcall.io/strength-of-schedule/), which averages
  2025 position-specific fantasy points allowed across each team's 2026 opponents.
- **Checks:** [RankFantasy](https://www.rankfantasy.com/strength-of-schedule),
  [FantasyPros](https://www.fantasypros.com/nfl/strength-of-schedule.php), and
  [FFToolbox](https://www.fftoolbox.com/football/strength_of_schedule.cfm).
- **Result:** DraftCall and FFToolbox place 145 of 192 team-position pairs in the same
  bucket: QB 30/32, RB 26/32, WR 30/32, TE 28/32, K 20/32, and D/ST 11/32. Skill-position
  direction is well corroborated. Kicker and D/ST are scoring-sensitive and remain
  low-confidence tiebreakers because the sources disagree materially.

### INJ - projected regular-season fantasy weeks missed

- **Primary feeds:** [Sleeper's NFL player feed](https://api.sleeper.app/v1/players/nfl?active=true)
  and [ESPN's injury report](https://www.espn.com/nfl/injuries), refreshed August 21.
- **Checks:** dated team and specialist reporting for single-feed cases, plus the
  [NFL's 2026 reporting calendar](https://www.nfl.com/news/2026-27-national-football-league-important-dates)
  for preseason-versus-regular-season status limits.
- **Result:** all **51/51** current injury signals are supported by at least two named
  providers. Fifty appear in both Sleeper and ESPN. Jordan James appears in Sleeper and
  is independently corroborated by the [49ers' August 18 practice report](https://www.49ers.com/news/day-14-of-2026-training-camp-kaelon-black-returns-for-joint-practice-with-chargers)
  and [FantasyPros](https://www.fantasypros.com/nfl/players/jordan-james.php). The only
  current red bucket is Jordyn Tyson at 5-6 fantasy weeks; independent reporting describes
  a roughly two-month absence and a possible October return.
- **Display:** ranges preserve schedule and return-date uncertainty. Green is 0 missed
  fantasy weeks, yellow is 1-2 at the upper end, and red is 3+ or unresolved. Formal NFL
  game-status reports begin in kickoff week, so preseason status-only estimates remain
  lower confidence.

## Limitations

- Depth charts can change after one practice, transaction, or injury report.
- `OFF` and `OL` are projections created with different inputs, not observed outcomes.
- Preseason SOS is based heavily on last season's defensive results; personnel and scheme
  changes make it directional rather than deterministic.
- Injury estimates can change after any practice, roster move, or updated return timeline;
  zero means no regular-season missed week is currently projected, not guaranteed health.
- Bucket boundaries deliberately emphasize the top and bottom 10 ranks. A team at rank
  10 is not meaningfully different from rank 11 solely because its color changes.
