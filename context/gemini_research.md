# 2026 fantasy football draft-prep guide

**Research date:** August 21, 2026  
**Primary use:** fast draft-day reference for the custom scoring in
[broncon24_league_scoring.txt](./broncon24_league_scoring.txt)  
**Market baseline:** 12-team, one-QB redraft unless noted otherwise

> [!IMPORTANT]
> The scoring file does not include roster slots, draft order, keeper rules, waiver
> rules, playoff weeks, or whether the 40-yard and 50-yard touchdown bonuses stack.
> The repository contains a 12-team round overlay, so this guide uses 12-team round
> prices as a working assumption. Confirm the missing settings in the league host
> before locking the board.

## Quick navigation

- [Draft-day card](#draft-day-card)
- [2026 sleeper research](./sleepers_2026.md)
- [Generated reweighted cheat sheet](./reweighted_cheat_sheet.md)
- [Ranking source audit](./source_audit.md)
- [What this scoring changes](#what-this-scoring-changes)
- [Conservative player-ranking model](#conservative-player-ranking-model)
- [Opponent-defense and schedule adjustment](#opponent-defense-and-schedule-adjustment)
- [Scoring-adjusted player board](#scoring-adjusted-player-board)
- [Current injury and role watchlist](#current-injury-and-role-watchlist)
- [Column cross-reference validation](./column_validation.md)
- [Round-by-round plan](#round-by-round-plan)
- [Targets, values, and price-sensitive fades](#targets-values-and-price-sensitive-fades)
- [Tool stack](#tool-stack)
- [Draft workflow](#draft-workflow)
- [Sources and limitations](#sources-and-limitations)

## Draft-day card

### Default plan

1. Open with elite RB/WR yardage volume; do not chase touchdowns alone.
2. Treat explosive-play bonuses as a tiebreaker inside a tier.
3. Target Josh Allen around Round 3, or wait for the Maye/Burrow/Hurts cluster
   around Round 6. Patrick Mahomes is a later contingency if his health remains
   positive.
4. Pay for Brock Bowers or Trey McBride only at a reasonable tier price; otherwise
   wait through the crowded middle of TE.
5. Use Rounds 7-12 on RB/WR role upside, then fill any remaining QB/TE need.
6. Draft D/ST and kicker in the final two rounds unless league rules create an
   unusual scarcity.

### Ranking adjustment at a glance

| Decision layer | Draft-day rule |
|---|---|
| Custom-scored projection value | **60% of the score**; ESPN Mike Clay + FFToday raw-stat mean above a corrected replacement baseline |
| Baseline consensus | **30% of the score**; ESPN rank + FantasyPros ECR + FFToday market price |
| Opportunity + team offense + line | **9% of the score**; order players with similar projected value and price |
| Opposing defenses | **1% of the score**; position/archetype tiebreaker only in preseason |
| Risk | Use the live injury context plus role/suspension uncertainty; subtract 0-5 total points only for risk not already reflected in projections |
| Movement cap | Never move more than one tier; top 24 move at most two spots ordinarily |

Short version: **talent, league value, and role establish the tier; offense, line,
scheme, and schedule order the tier.**

Current injury inputs come from
[player_injuries.md](./player_injuries.md). If a projection already incorporates a
reported absence, do not reduce it again; use the injury context only for residual
timeline and role uncertainty.

### Tie-break order

When two players are in the same projection tier:

1. Stable snap, route, touch, or target share
2. Yardage concentration and realistic 100-yard-game paths
3. Explosive-play ability
4. Healthy offensive line and quarterback environment
5. Price versus the room's platform ADP
6. Bye week only as a final tiebreaker

### Red flags to check immediately before drafting

- Confirm whether 40+ and 50+ touchdown bonuses stack.
- Refresh injuries and ADP within 24 hours of the draft.
- Do not draft Jordyn Tyson at his pre-injury Round 6 price.
- Do not use Parker Washington's older Round 9 sleeper label; his 12-team half-PPR
  market had already moved to about Round 5 by August 16.
- Do not assume every “free” draft tool supports milestone bonuses or live sync.

## What this scoring changes

### Scoring deltas

| Category | League rule | Common baseline | Draft consequence |
|---|---:|---:|---|
| Passing yards | 0.05 per yard | 0.04 per yard | Passing yardage is worth 25% more. Volume passers and 300-yard-game candidates rise. |
| Passing TD | 4 | 4 | Conventional passing-TD value remains intact. |
| Interception | -2 | -2 | Turnover-prone volume is not free; efficiency still matters. |
| Rushing/receiving yards | 0.10 per yard | 0.10 per yard | Yardage remains the stable foundation for RB/WR/TE value. |
| Reception | 0.5 | 0.5 half-PPR / 1.0 PPR | Use half-PPR—not the local ESPN full-PPR sheet—as the market baseline. |
| Rushing/receiving TD | 5 | Usually 6 | Touchdown-only and goal-line profiles lose relative value. |
| 100-yard rush/receive game | +2 | Often 0 | Concentrated weekly workloads gain ceiling. |
| 200-yard rush/receive game | +4 | Often 0 | Rare ceiling games matter, but should not drive median projections. |
| 300/400 passing game | +2 / +3 | Often 0 | High-volume pocket passers close part of the gap on rushing quarterbacks. |
| 40+/50+ TD bonus | +1 / +2 | Often 0 | Explosive players gain a small ceiling edge, conditional on stacking behavior. |
| Kicker makes | 2 to 3.5 | Commonly 3 to 5+ | Kicker scoring is compressed. |
| Short FG miss | -2 | Often 0 or -1 | Accuracy and job security matter more than raw attempt volume. |

### Correct scoring examples

- **300 passing yards, two passing TDs, no interceptions:**  
  15 passing-yard points + 2-point milestone + 8 TD points = **25 points**.

- **410 passing yards and two 50-yard passing TDs:**  
  20.5 passing-yard points + 8 TD points + 3 for the 400-yard game, plus
  **4 to 6 long-TD bonus points** depending on whether the 40+ and 50+ bonuses
  are exclusive or cumulative. Total: **35.5 to 37.5 points**.

- **Exactly 50-yard receiving TD:**  
  5 yardage points + 0.5 reception + 5 TD points, plus **2 or 3 long-TD bonus
  points**. Total: **12.5 or 13.5 points**.

- **Eight catches for 100 receiving yards:**  
  4 reception points + 10 yardage points + 2 milestone points = **16 points**.

The earlier research treated some passing milestones as cumulative and described
the 50-yard receiving play incorrectly. Use the ranges above until the league host
confirms bonus stacking.

### Strategic interpretation

#### Quarterback

Quarterbacks rise relative to generic half-PPR boards because every 300 passing
yards produces 15 base points instead of the usual 12, before the milestone bonus.
However, this is still assumed to be a one-QB league with a deep replacement pool.
Move the elite tier up roughly one round—not to the first overall tier.

The 5-point rushing-TD rule slightly reduces the conventional advantage of rushing
quarterbacks, while the passing-yard and milestone rules help high-volume passers.
That makes Josh Allen and Lamar Jackson strong, but also improves the relative fit
of Joe Burrow, Drake Maye, and a healthy Patrick Mahomes.

#### Running back

Prioritize backs with:

- Workloads capable of producing 100-yard games
- Breakaway ability
- Receiving work that survives game-script changes
- Clear early-down and goal-line roles

Do not overpay for a touchdown specialist. A rushing TD is worth one point less
than standard scoring, while the yardage milestone requires sustained volume.

#### Wide receiver

This format rewards two different profiles:

- High-volume yardage anchors who can repeatedly approach 100 yards
- Vertical or yards-after-catch threats who can convert a long play into a bonus

The best targets combine both. Pure possession receivers lose some value relative
to full PPR, but stable target earners should not be downgraded multiple tiers.
Explosive-play bonuses are too infrequent to rescue a low-volume receiver.

#### Tight end

Half-PPR and 5-point receiving TDs reduce the payoff from reception-only and
touchdown-only profiles. Pay for true yardage/target separation at the top, or wait.
The August market was pushing several middle-tier tight ends down, which supports
an elite-or-late approach rather than forcing a mid-round selection.

#### D/ST and kicker

- Favor D/ST units with sack pressure and low points-allowed expectations.
- Return-yard scoring is only 0.1 per 25 yards, so it should not drive rankings.
- Stream D/ST by matchup unless the roster rules make the waiver pool unusually thin.
- For kickers, prefer accuracy, job security, and offenses that cross midfield.
- The modest long-field-goal premium does not justify an early kicker.

## Projection-first player-ranking model

The automated model now starts with projected league value rather than an ordinal VORP
proxy. It averages ESPN Mike Clay and FFToday raw statistics, scores the result under the
league export, and derives replacement baselines from assumed starter and flex demand.
Every component is graded from 0 to 100. Subtract a separate total risk penalty of 0-5
points after calculating the weighted score.

```text
Adjusted player score =
  60% custom-scored projection value over baseline
+ 30% multi-source baseline consensus
+  5% player opportunity
+  2% team offense environment
+  2% position-specific offensive-line fit
+  1% projected opponent-defense schedule
-  0-5 point risk penalty
```

The evidence review and limitations for this change are in
[weighting_strategy_research.md](./weighting_strategy_research.md). The exact outer weights
are a conservative implementation choice rather than a claimed league-specific backtest;
the empirically supported pieces are projection averaging and corrected replacement value.

### Component definitions

| Component | What receives a high grade | What should not drive it |
|---|---|---|
| Projected value | Mean ESPN/FFToday raw-stat projection scored under league rules, above the configured position baseline | A provider's default fantasy-point total |
| Baseline consensus | ESPN rank, FantasyPros ECR, and FFToday market price converted to a 0-100 grade | One analyst's unsupported rank |
| Opportunity | Carries, routes, targets, high-value touches, goal-line share, and role durability | Last year's touchdowns by themselves |
| Team offense | Scoring opportunities, plays, pace, scheme fit, supporting cast, and QB quality | Team wins alone |
| Offensive-line fit | The blocking traits that matter to this player's role | Sacks allowed or rushing yards alone |
| Opponent schedule | Projected, position-specific matchup ease with uncertainty applied | Prior-year opponent record or raw fantasy points allowed alone |
| Risk penalty | Current injury tier/games range, suspension, role fragility, age/workload, or major projection uncertainty | Any missed games or uncertainty already incorporated in the baseline projection |

Opportunity should carry more weight than volatile efficiency. Historical
year-over-year work found RB receptions, routes, and rush attempts more stable than
touchdown rates; WR targets, receptions, yards per route run, and first-down rate
also carried more signal than touchdown rate or yards per reception.
[4for4 RB predictability](https://www.4for4.com/2024/preseason/most-predictable-running-back-stats)
[4for4 WR predictability](https://www.4for4.com/2024/preseason/most-predictable-wide-receiver-stats)

### Team offense environment

```text
Team offense grade =
  30% projected points and red-zone trips
+ 25% projected plays and neutral-situation pace
+ 20% scheme fit for this player's role
+ 15% quarterback and supporting-cast quality
+ 10% coaching, QB, and system continuity
```

Apply it differently by position:

| Position/profile | Most important team effects |
|---|---|
| Pocket QB | Pass volume, protection, receiver quality, pace, and red-zone pass tendency |
| Rushing QB | Designed carries, scramble production, goal-line role, and protection adjusted for mobility |
| Early-down RB | Expected leads, rush rate, red-zone trips, and goal-line competition |
| Receiving RB | Routes, target share, checkdown tendency, and negative-script usefulness |
| Deep WR | Pass volume, QB deep accuracy, protection time, and air-yard concentration |
| Slot/possession WR | Routes, first-read targets, catchable volume, and pace |
| TE | Route participation, middle-of-field usage, target competition, and red-zone role |

A bad real-life offense does not automatically make every RB a downgrade. A
receiving back can gain targets in negative game scripts, while a touchdown-only
back is more dependent on a strong offense reaching the goal line.

### Offensive-line fit

Do not assign every teammate the same line grade. Match the line's strengths and
weaknesses to the player's role.

```text
RB line grade =
  35% yards created before contact
+ 25% run-block win rate
+ 20% short-yardage success and inverse stuff rate
+ 20% health, depth, and continuity
```

Yards before contact and block-win measures help separate what the line creates
from what the runner creates after contact.
[NFL.com on RB yards before close](https://www.nfl.com/news/koh-knows-rbs-to-trust-in-the-fantasy-playoffs-0ap3000000892296)
[ESPN run/pass block methodology](https://www.espn.com/nfl/story/_/id/38356170/2023-nfl-pass-rush-run-s)

```text
QB protection grade =
  35% pass-block win rate
+ 25% inverse quick-pressure rate
+ 20% interior protection
+ 10% health and continuity
+ 10% scheme mitigation
```

Scheme mitigation includes quick throws, play action, screens, moving pockets, and
designed QB movement. Sacks allowed should not be the primary input because sacks
and pressures also depend on time to throw, quarterback behavior, coverage, help,
and opponent quality. NFL Next Gen Stats defines a quick pressure as one occurring
within 2.5 seconds and provides pressure-rate-over-expected concepts that account
for the pass-rush opportunity.
[NFL Next Gen Stats pressure methodology](https://www.nfl.com/news/next-gen-stats-introduction-to-pressure-probability)
[Opponent-adjusted line research](https://arxiv.org/abs/2604.01491)

For WRs and TEs, line play should normally contribute only 1-2% indirectly. It
matters most to deep routes that need time to develop and least to quick slot or
screen usage.

### Context adjustment and movement caps

Use the weighted score only after creating player tiers. Require roughly a
two-point adjusted-score difference before changing the order of two players.

| Combined context | Suggested adjustment |
|---|---:|
| Excellent offense, strong/healthy line, aligned scheme | +3 points |
| Two clearly favorable factors | +1.5 points |
| Mixed environment | 0 |
| Poor offense or important line weakness | -1.5 points |
| Poor offense plus major line problems | -3 points |
| Confirmed major QB/line injury not yet reflected in projections | Up to +/-4 points |

Cap the resulting rank movement:

| Baseline rank | Maximum ordinary movement |
|---:|---:|
| 1-24 | 2 spots |
| 25-72 | 4 spots |
| 73-144 | 8 spots |
| 145+ | 12 spots |

Never cross more than one established tier for context alone. An exception is
reasonable only after a confirmed material injury or role change that the baseline
has not yet incorporated.

## Opponent-defense and schedule adjustment

Opponent strength belongs in the model, but preseason schedule rankings have high
uncertainty. A 2003-2025 audit found that schedule difficulty based on opponents'
prior-year records correlated only **0.18** with the schedule actually faced and
explained about 3% of its variance. A separate ten-year fantasy analysis found
roughly a one-point-per-game average QB schedule difference and substantial
year-to-year defensive volatility.
[NFL Analytics 2026 SOS audit](https://www.nflanalytic.com/explainer-2026-schedule-strength.html)
[FantasyPros SOS caution](https://www.fantasypros.com/2018/06/strength-of-schedule-should-not-influence-your-draft-strategy/)

The current board input is the generated
[position-specific schedule context](./strength_of_schedule.md), with the complete
[machine-readable values](./strength_of_schedule.json). It stores DraftCall's
full-season and Weeks 14-17 opponent averages and ranks for QB, RB, WR, TE, K, and
D/ST. Apply each player's team-and-position `season_rank` as the available preseason
SOS tiebreaker: **1 is easiest and 32 hardest**. The player-level mapping is also
persisted in `player_depth_charts.json` so later reweighting does not have to infer
position or team from display text.

For that reason:

- Give projected schedule only **2%** of a preseason player grade.
- Use schedule as a tiebreaker inside a tier, never the reason to draft a weaker
  player multiple rounds earlier.
- Use the opening four games primarily for late-round players who must become
  startable quickly.
- Give playoff matchups little preseason weight; defenses, injuries, and roles can
  change substantially before the league's playoff weeks.
- Increase matchup weight for weekly start/sit decisions after current-season data
  becomes available.

### Build a defensive prior

At draft time, grade each scheduled defense from 0 to 100, where **100 means easiest
for the offensive player**:

```text
Preseason defensive-ease grade =
  50% projected current-season defensive quality
+ 30% regressed, schedule-adjusted prior-season efficiency
+ 20% personnel, coaching, and injury changes
```

This is a recommended heuristic, not a validated universal coefficient set. A
current-season projection should consider returning starters, pass-rush and
secondary changes, defensive coaching/scheme, and known injuries. Regress the
prior-year statistics toward league average instead of carrying the raw rank
forward.

Raw fantasy points allowed can be distorted by the offenses a defense happened to
face. Prefer opponent-adjusted position scoring or play-by-play efficiency. The
open nflverse data supports separate defensive passing and rushing EPA-per-play
calculations, with sacks and scrambles treated as pass plays.
[nflfastR play-by-play examples](https://github.com/nflverse/nflfastR/blob/master/vignettes/nflfastR.Rmd)

### Score the matchup by position and archetype

All inputs below are converted to ease percentiles: 100 is most favorable to the
fantasy player and 0 is least favorable.

#### Quarterback matchup

```text
QB defensive-ease grade =
  30% pass EPA/dropback allowed
+ 25% inverse quick-pressure and pressure-over-expected grade
+ 15% explosive-pass rate allowed
+ 15% pass-volume/funnel opportunity
+ 10% red-zone passing efficiency allowed
+  5% relevant secondary/pass-rush availability
```

- Pocket passers are more sensitive to pressure and interior disruption.
- Mobile QBs receive a smaller line/pass-rush downgrade, but add opponent contain,
  scramble, and QB goal-line defense to their archetype check.
- High pressure can hurt deep passing while creating short targets for an RB, slot
  WR, or TE; do not apply one matchup label to an entire offense.

#### Running back matchup

```text
RB defensive-ease grade =
  30% rush EPA/attempt allowed
+ 25% yards before contact and inverse run-stop grade
+ 20% explosive-run rate allowed
+ 15% short-yardage and goal-line success allowed
+ 10% expected game-script fit
```

- Increase run-front and short-yardage weight for early-down/goal-line backs.
- Increase RB targets allowed, blitz/checkdown tendencies, and expected negative
  script for receiving backs.
- Do not punish a pass-catching RB as heavily as a carry-dependent RB for facing a
  strong run defense.

#### Wide receiver matchup

```text
WR defensive-ease grade =
  30% schedule-adjusted WR production allowed
+ 25% pass EPA and explosive-pass rate allowed
+ 20% target-volume/funnel opportunity
+ 15% alignment/archetype fit
+ 10% secondary and pass-rush availability
```

- For deep/outside receivers, emphasize explosive passes, outside coverage, and
  whether the offensive line can hold up against the pass rush.
- For slot/short-area receivers, emphasize target volume, middle-field coverage,
  and catchable opportunities rather than the opponent's overall WR rank.
- Avoid individual cornerback-matchup overconfidence unless the defense regularly
  uses shadow coverage and the assignment is confirmed.

#### Tight end matchup

```text
TE defensive-ease grade =
  35% schedule-adjusted TE production allowed
+ 25% middle-of-field coverage efficiency
+ 20% target/funnel opportunity
+ 10% red-zone TE production allowed
+ 10% linebacker/safety and pass-rush availability
```

TE matchup samples can be especially small, so regress aggressively toward league
average. Role and route participation remain more important than a green matchup.

### Combine the weekly schedule

Do not merely average defensive rank 1-32. Average the 0-100 position/archetype
grades and preserve uncertainty.

```text
Draft-time schedule grade =
  50% full fantasy regular season
+ 35% Weeks 1-4
+ 15% league-defined fantasy playoffs
```

For late-round breakout candidates, use **30% full season, 55% Weeks 1-4, and 15%
playoffs** because early usability determines whether they survive on the roster.
Exclude Week 18 unless the league actually uses it. Confirm the league's playoff
weeks before calculating the playoff component.

### In-season update cadence

| When | Defensive information mix | Recommended use |
|---|---|---|
| Draft day | 50% current projection / 30% regressed prior efficiency / 20% changes | 2% ranking weight and tiebreaker only |
| After Week 4 | 60% current-season data / 25% preseason prior / 15% injuries | Begin meaningful streaming and close start/sit calls |
| After Week 8 | 75% current-season data / 10% preseason prior / 15% injuries | Rest-of-season and trade-deadline schedule analysis |
| Weekly | Update active defensive personnel, weather, venue, rest, and betting expectation | Start/sit decisions; never replace late news with a stale season rank |

The in-season blends above are practical shrinkage heuristics. Small samples still
matter, so use rolling, opponent-aware data and retain a preseason prior rather than
flipping entirely to a four-game defensive leaderboard.

### Fast draft-day decision rule

When two players are already in the same tier, move one slightly higher only when
at least two of these are true:

1. Better and healthier offensive line for that player's role
2. Better projected offense and red-zone environment
3. Clearer, more stable opportunity
4. Scheme and coaching align with the role
5. Meaningfully easier **position/archetype-adjusted** early schedule

If only the schedule is better, keep the original order. If talent, VORP, and
opportunity all favor one player, schedule should not reverse the decision.

## Scoring-adjusted player board

This is an overlay, not a full projection model. Start with current 12-team half-PPR
ADP, then apply the scoring adjustments below. FFToday's August 16 market combined
Underdog and Yahoo data; ESPN's local August 19 sheet is useful for player/team/bye
updates but is a **10-team full-PPR** board, so its overall ranks are not directly
portable. [FFToday ADP](https://www.fftoday.com/rankings/26-adp-half-ppr.html)
[ESPN PPR Top 300](https://g.espncdn.com/s/ffldraftkit/26/NFL26_CS_PPR300.pdf?adddata=2026CS_PPR300)

### Tier A: first-round anchors

| Player pool | Custom-scoring view |
|---|---|
| Jahmyr Gibbs, Bijan Robinson | Best combination of RB yardage volume and explosive ceiling. Strong 1.01 candidates. |
| Ja'Marr Chase, Puka Nacua | Elite target and yardage concentration; both retain top-tier value despite half-PPR. |
| Christian McCaffrey | Elite all-purpose ceiling, priced with age/workload risk. Do not move above Gibbs/Bijan solely for receptions. |
| Jaxon Smith-Njigba, Amon-Ra St. Brown, CeeDee Lamb | High-volume WR anchors. JSN's and Lamb's yardage ceilings fit especially well; Amon-Ra remains elite even with less reception weight than full PPR. |
| Jonathan Taylor, James Cook | Strong first-round RB alternatives; grade on projected workload and explosive output, not touchdown totals alone. |

The August 16 half-PPR market's first ten were Gibbs, Bijan, Chase, Nacua,
McCaffrey, Smith-Njigba, Amon-Ra, Taylor, Lamb, and Cook.
[FFToday ADP](https://www.fftoday.com/rankings/26-adp-half-ppr.html)

### Tier B: Round 2 and early Round 3

- **De'Von Achane:** an unusually strong rules fit because explosive rushing and
  receiving can create bonuses without relying only on TD volume.
- **Brock Bowers:** acceptable around his market price near pick 20 if you want
  the elite-TE path.
- **Nico Collins / George Pickens / Drake London / A.J. Brown:** prefer the
  player with the clearest yardage concentration at your pick.
- **Trey McBride:** elite target role, but half-PPR makes him more price-sensitive
  than full PPR. Late Round 3 is easier to justify than Round 2.
- **Malik Nabers:** upside remains enormous, but the Round 2 price requires
  accepting ACL/cartilage recovery uncertainty.
- **Jeremiyah Love:** do not pay a mid-Round 2 price for a crowded backfield.
  The August 16 market placed him around pick 25.5; Round 3 is the safer entry.

### Quarterback price ladder

| Player | Aug. 16 half-PPR ADP | 12-team market round | Custom-scoring action |
|---|---:|---:|---|
| Josh Allen | 32.5 | 3 | Primary target in Round 3; late Round 2 only if RB/WR tiers have flattened. |
| Lamar Jackson | 52.5 | 5 | Strong Round 5 target; do not chase into Round 3. |
| Drake Maye | 63.5 | 6 | Passing/rushing blend fits; target Round 6. |
| Joe Burrow | 65.5 | 6 | Passing-volume and milestone fit; target Round 6. |
| Jayden Daniels | 65.5 | 6 | Healthy entering camp; custom 5-point rushing TD slightly trims his normal edge. |
| Jalen Hurts | 68.5 | 6 | Same rushing-TD caveat; take at market, not above the entire Round 5 RB/WR tier. |
| Patrick Mahomes | 104.5 | 9 | Attractive fallback if his positive knee recovery holds through draft day. |

ADP source: [FFToday, 12-team half-PPR, August 16](https://www.fftoday.com/rankings/26-adp-half-ppr.html).

### Tight end price ladder

| Plan | Players | Price discipline |
|---|---|---|
| Pay up | Brock Bowers, Trey McBride | Take only when they do not require passing a stronger RB/WR tier. |
| Selective middle | Colston Loveland, Tyler Warren | Talent is real, but do not ignore Warren's current injury or the position's market compression. |
| Wait | Dalton Kincaid, Jake Ferguson | Kincaid around Round 10-11; Ferguson around Round 11-12 is a useful fallback. |
| Final fallback | Chigoziem Okonkwo, Isaiah Likely | Use if their starting role and health are confirmed close to the draft. |

FantasyPros reported that multiple middle-tier TEs had fallen together during
August as consensus adjusted to uncertain roles, strengthening the case for
elite-or-late roster construction.
[FantasyPros risers/fallers](https://www.fantasypros.com/2026/08/fantasy-football-risers-fallers-2026-nfl-preseason-week-1/)

## Current injury and role watchlist

The generated block below is refreshed by `scripts/update_injury_context.py` and is the
source of truth for injury reweighting. The editorial table that follows is an
August 20 research snapshot for recovery and role context; when it conflicts with
the generated block, use the newer generated evidence.

<!-- BEGIN GENERATED INJURY REWEIGHTING -->
### Live injury reweighting snapshot

**Effective date:** 2026-08-26

**Source:** [generated player injury context](./player_injuries.md)
**Evidence policy:** Sleeper and ESPN are checked for every player; active signals are corroborated with dated team or specialist reports when a feed is incomplete.

Apply injury information through the existing **0-5 total risk penalty**, not as an additional uncapped deduction:

1. If the baseline projection does **not** include the reported absence, multiply its season points by `availability factor = (17 - projected games missed) / 17`, then recalculate VORP. Use the midpoint when the context reports a range.
2. If the baseline already includes the absence, do not apply that factor again. Use only residual role/timeline uncertainty inside the existing risk penalty.
3. If the tool cannot reproject games, use the fallback penalty below. Never apply both the availability factor and the full fallback injury penalty.

| Injury tier | Base fallback penalty | Draft treatment |
|---|---:|---|
| CLEAR | 0 | No injury adjustment |
| WATCH, 0 games projected | 0.25 | Tiebreaker only |
| WATCH, up to 1 game | 0.5 | Small same-tier downgrade |
| SHORT | 1.5 | Meaningful same-tier downgrade |
| MEDIUM | 2.5 | Move toward the bottom of the tier |
| HIGH | 4.0 | Major discount; require roster/IR plan |
| VERY HIGH | 5.0 | Late stash only when format supports it |
| SEASON | Remove | Do not leave on the active redraft board |

Multiply the fallback penalty by confidence: **high 1.0**, **medium 0.85**, **low 0.60**. Injury plus suspension, role, and other uncertainty remains capped at the guide's existing five-point total risk penalty.

Current player tiers: **SEASON 0**, **VERY HIGH 0**, **HIGH 1**, **MEDIUM 0**, **SHORT 0**, **WATCH 55**, **CLEAR 222**.

#### Players with possible regular-season availability impact

| Rank | Player | Tier | Weeks | Availability factor | Fallback penalty | Confidence | Sources | Signal |
|---:|---|---|---:|---:|---:|---|---:|---|
| 152 | Jordyn Tyson | HIGH | 5-6 | 0.68 | 3.4 | medium | 2 | Sleeper Doubtful Strain; ESPN Doubtful Hamstring return 2026-10-18 |
| 15 | Jeremiyah Love | WATCH | 0-1 | 0.97 | 0.4 | medium | 2 | Sleeper Questionable; ESPN Questionable Ankle return 2026-09-13 |
| 53 | Luther Burden III | WATCH | 0-1 | 0.97 | 0.4 | medium | 2 | Sleeper Questionable; ESPN Questionable Groin return 2026-09-13 |
| 80 | Brian Thomas Jr. | WATCH | 0-1 | 0.97 | 0.4 | medium | 2 | Sleeper Questionable; ESPN Questionable Shoulder return 2026-09-13 |
| 100 | Chuba Hubbard | WATCH | 0-1 | 0.97 | 0.4 | medium | 2 | Sleeper Questionable; ESPN Questionable Hamstring return 2026-09-13 |
| 106 | Kyle Monangai | WATCH | 0-1 | 0.97 | 0.4 | medium | 2 | Sleeper Questionable; ESPN Questionable Knee return 2026-09-13 |
| 130 | Tank Dell | WATCH | 0-1 | 0.97 | 0.3 | low | 1 | Sleeper Questionable Surgery |
| 138 | Alvin Kamara | WATCH | 0-1 | 0.97 | 0.4 | medium | 2 | Sleeper Questionable; ESPN Questionable Knee - MCL return 2026-09-13 |
| 155 | Isiah Pacheco | WATCH | 0-1 | 0.97 | 0.4 | medium | 2 | Sleeper Questionable; ESPN Questionable Knee - MCL return 2026-09-13 |
| 165 | Jaylin Noel | WATCH | 0-1 | 0.97 | 0.3 | low | 1 | Sleeper Questionable |
| 225 | Ty Johnson | WATCH | 0-1 | 0.97 | 0.4 | medium | 2 | Sleeper Questionable; ESPN Questionable Lower Leg return 2026-09-13 |

#### Watchlist with no regular-season games currently projected

Ja'Marr Chase (#3), Puka Nacua (#4), Christian McCaffrey (#6), Ashton Jeanty (#13), Kenneth Walker III (#21), Breece Hall (#23), Chris Olave (#26), Malik Nabers (#29), Josh Jacobs (#30), Emeka Egbuka (#42), Tyler Warren (#50), TreVeyon Henderson (#63), Michael Pittman Jr. (#66), DK Metcalf (#68), Alec Pierce (#70), Sam LaPorta (#73), Mike Evans (#76), Jakobi Meyers (#81), Khalil Shakir (#90), Xavier Worthy (#92), Patrick Mahomes (#94), Tucker Kraft (#101), George Kittle (#102), Jacory Croskey-Merritt (#107), Rachaad White (#108), Quentin Johnston (#112), Josh Downs (#113), Kenyon Sadiq (#118), De'Zhaun Stribling (#129), Zach Charbonnet (#137), Jalen McMillan (#145), Keaton Mitchell (#154), Terrance Ferguson (#159), Tre Harris (#204), Jordan James (#212), Ollie Gordon II (#222), Isaiah Davis (#226), Xavier Legette (#227), Keon Coleman (#234), Adam Randall (#243), LeQuint Allen (#245), James Conner (#248), Emanuel Wilson (#265), Tory Horton (#271), Jawhar Jordan (#282)

Treat this snapshot as time-sensitive. The full context includes evidence dates, source links, confidence, and rationale for every ranked player. A CLEAR result means no current designation was found; it is not a forecast of future health.
<!-- END GENERATED INJURY REWEIGHTING -->

### Editorial recovery and role snapshot - August 20

| Player | Current evidence | Draft response |
|---|---|---|
| Patrick Mahomes | Full camp participant after ACL/LCL surgery; reporting pointed toward Week 1 availability. | Keep as a Round 9 fallback, but recheck before drafting. |
| Malik Nabers | Returned to 11-on-11 work; optimism for Week 1, but not yet full speed after ACL/cartilage injury and a later procedure. | Accept only with a healthy early-season WR3/Flex contingency. |
| Alvin Kamara | Reported Grade 2 MCL sprain with at least a month expected; Week 1 in doubt. | Remove from ordinary Round 13-14 consideration until price and timeline update. |
| Jordyn Tyson | Hamstring injury expected to cost roughly two months; short-term IR was possible. | Do not draft at his old Round 6 ADP. Consider only as a late IR stash if rules permit. |
| Tyler Warren | Abductor strain characterized as short term, with a return expected in roughly a week. | Small downgrade, not a panic fade; verify practice status. |
| De'Zhaun Stribling | First-team opportunity rose after 49ers WR injuries; he also experienced hamstring tightness. | Upside target, but do not chase far ahead of Round 11 without a clean health update. |

Injury evidence: [Fantasy Alarm's August 20 report](https://www.fantasyalarm.com/articles/nfl/fantasy-football-draft-guide/2026-offseason-fantasy-football-injury-report/190980) and
[NFL.com's August rookie update](https://www.nfl.com/news/2026-nfl-fantasy-football-15-rookies-worth-a-late-round-draft-pick).

## Round-by-round plan

This plan assumes 12 teams, one QB, two RB, two WR, one TE, one Flex, K, and D/ST.
Adjust immediately if the actual league has Superflex, three WRs, multiple Flex
spots, TE premium, or shallow benches.

| Round | Default objective | Pivot conditions |
|---:|---|---|
| 1 | Elite RB/WR anchor | Do not take QB, TE, D/ST, or K. |
| 2 | Second RB/WR anchor; Bowers is acceptable at fair value | Take Josh Allen only near the 2/3 turn after a severe RB/WR tier break. |
| 3 | Best RB/WR; Josh Allen; McBride at a discount | Avoid reaching for a committee RB solely because the room is running RB. |
| 4 | RB/WR depth and Flex ceiling | Let QB/TE fall unless your preferred tier is ending. |
| 5 | Lamar Jackson or strongest RB/WR tier | Do not buy a player after a two-round ADP surge without role evidence. |
| 6 | Maye/Burrow/Daniels/Hurts or best RB/WR | If QB is filled, attack volume and contingent RB value. |
| 7-8 | Complete starters; Jayden Reed near Round 8; Stefon Diggs near fair price | Avoid the uncertain middle-TE tier if it costs a stronger Flex. |
| 9-10 | Goff fallback; Kincaid or Likely; Chris Rodriguez; high-upside WRs | Leave with QB and TE by the end only if the room is creating scarcity. |
| 11-12 | Shough if waiting at QB; Okonkwo; Denzel Boston; Stribling | Favor players who can gain value before Week 1. |
| 13+ | Jonah Coleman, Ja'Kobi Lane, Caleb Douglas, Tank Dell | Use IR rules strategically; avoid low-ceiling veteran depth. |
| Final 2 | D/ST and kicker | Reverse only if league rules do not require one of these positions. |

## Targets, values, and price-sensitive fades

### Targets at current cost

| Player | Target range | Why the fit works | Main risk |
|---|---:|---|---|
| Josh Allen | Round 3 | Elite weekly floor plus enhanced passing-yard scoring. | Opportunity cost at RB/WR in a one-QB league. |
| Joe Burrow / Drake Maye | Round 6 | Strong path to passing milestones without an early-QB price. | Maye's projection includes more uncertainty; Burrow is more pass-environment dependent. |
| Patrick Mahomes | Round 9 | Custom passing rules create more upside than standard half-PPR ADP reflects. | Major knee recovery requires same-day verification. |
| De'Von Achane | Round 2 | Explosive rushing/receiving profile can access every bonus category. | Workload and durability volatility. |
| Jameson Williams | Round 5 | Explosive scoring fit at approximately pick 53.5. | Low-volume weeks; do not elevate multiple rounds for bonus chasing. |
| Stefon Diggs | Round 8-9 | Current role and efficient 2025 receiving profile offer usable value. | Age, recent team change, and ADP may keep rising. |
| Jayden Reed | Round 8-9 | Three independent source families agree on post-injury value and vacated targets. | At ADP 91 he is a value, not a deep sleeper; Green Bay can still spread targets. |
| Chris Rodriguez Jr. | Round 10 | Similar first-team opportunity to the more expensive Jacksonville back, with efficient rushing evidence. | Committee uncertainty; 5-point rushing TDs reduce a goal-line-only thesis. |
| Dalton Kincaid | Round 10-11 | Athletic efficiency and TE1 ceiling at a reduced price. | Multi-year injury and role volatility. |
| Isaiah Likely | Round 10-11 | FTN, RotoBaller, and Fantasy Life agree on a larger Giants receiving role. | Costs roughly three rounds more than Okonkwo. |
| Tyler Shough | Round 11-12 | Four independent source families support the second-year passing/rushing case. | One-QB replacement value; do not take him early merely because consensus is broad. |
| Chig Okonkwo | Round 12-13 | Broadest late-TE agreement and a clearer receiving role with Jayden Daniels. | Low historical TD and target ceiling. |
| Jonah Coleman | Round 13 | Three-source sleeper consensus, three-down traits, and the projected No. 1 line. | Opens as RB3 in a Sean Payton committee. |
| Jake Ferguson | Round 11-12 | Stable late-TE path after a strong 2025 season. | Half-PPR reduces the benefit of catch volume. |
| Denzel Boston | Round 12 | First-team opportunity, perimeter size, and vertical/red-zone ceiling. | Rookie in an uncertain offense. |
| Ja'Kobi Lane | Final round | Size and red-zone path complement Baltimore's existing WR room. | Role may remain too small for early-season use. |
| Tank Dell | Final round / watchlist | Big-play profile directly fits the bonuses. | Long recovery and crowded Houston target tree. |

Late-round role evidence:
[NFL.com sleepers](https://www.nfl.com/news/2026-nfl-fantasy-football-six-late-round-sleepers-to-target).

### Price-sensitive fades or holds

These are not “never draft” labels; they are stop prices.

| Player | Current issue | Stop price |
|---|---|---|
| Jeremiyah Love | Crowded Arizona RB room and uncertain team efficiency | Do not take in Round 2; reconsider in Round 3. |
| Parker Washington | Older sleeper articles cited Round 9, but Aug. 16 half-PPR ADP was about 59.5 overall | At the new Round 5 price, require WR2-level conviction rather than sleeper logic. |
| Jordyn Tyson | Two-month hamstring timeline versus old Round 6 ADP | Late IR-stash price only, and only if the league provides IR capacity. |
| Alvin Kamara | MCL sprain and uncertain September availability | Late bench/IR price after an updated timeline; otherwise pass. |
| Garrett Wilson | Injury history and new target competition at a premium price | Require a discount from Round 3. |
| Mid-tier TEs as a group | Market has often priced name recognition above role clarity | Do not select merely because a “TE run” starts. |

NFL.com's July value article called Jeremiyah Love and Garrett Wilson overvalued
and highlighted Jake Ferguson as undervalued. Treat those as arguments to compare
with live price—not static ranks.
[NFL.com overvalued/undervalued](https://www.nfl.com/news/2026-nfl-fantasy-football-10-overvalued-undervalued-nfl-players-to-know-before-you-draft).

## Tool stack

The original directory mixed free, premium, unsupported, and dynasty-oriented
products. Use this smaller stack.

### Recommended core

| Tool | Best use | Cost/access finding | Important limitation |
|---|---|---|---|
| [DraftKick](https://app.draftkick.com/football) | Generate a custom Beersheets-style starting board | The 2026 product is live and its [current launch announcement](https://www.reddit.com/r/fantasyfootball/comments/1uxh8pd/draftkick_is_live_for_2026/) describes free custom sheets. | Verify that the milestone and long-TD inputs behave exactly like the league host. |
| [LineupExperts](https://www.lineupexperts.com/) | Import league settings and generate customized static draft analysis | Many synced/custom tools remain free; live draft sync now requires an eligible premium term. | Do not plan on free live sync without checking the account tier. |
| [Footballguys Classic](https://www.footballguys.com/article/footballguys-classic-drafting-apps) | Offline custom scoring and VBD cross-check | Fully functioning June 11 free versions exist for Mac/Linux/Windows. | The latest August 20 projections and live/custom cloud features are paid. |
| [FFToday half-PPR ADP](https://www.fftoday.com/rankings/26-adp-half-ppr.html) | 12-team market price and round discipline | Free web reference; Aug. 16 data combined Underdog and Yahoo. | It does not price this league's milestone bonuses. |
| [FantasyPros 2026 positional SOS](https://www.fantasypros.com/nfl/strength-of-schedule.php) | Current position-specific schedule cross-check | Free page; its methodology uses fantasy points allowed adjusted for strength of schedule. | Use as a 2% preseason tiebreaker, not as an independent player projection. |
| [nflverse play-by-play data](https://github.com/nflverse/nflverse-data/releases/tag/pbp) | Build transparent pass/rush EPA and opponent-adjusted checks | Free open data available as CSV and Parquet. | Requires analysis work and defensive priors; raw small-sample ranks remain noisy. |
| [NFL Fantasy News](https://www.nfl.com/news/series/fantasy-football-news) | Current roles, rookies, and camp context | Free first-party league reporting. | Most analysis assumes full PPR and ESPN ADP. |
| [ESPN PPR Top 300](https://g.espncdn.com/s/ffldraftkit/26/NFL26_CS_PPR300.pdf?adddata=2026CS_PPR300) | Team, bye, and broad ranking sanity check | Free PDF, updated Aug. 19. | It is 10-team full-PPR with conventional scoring, not this league. |

### Useful with caveats

| Tool | Use only when | Caveat |
|---|---|---|
| [FantasyPros Draft Wizard](https://draftwizard.fantasypros.com/football/draft-tools/) | You want consensus tiers, tags, or paid live assistance | FantasyPros says custom yardage bonuses and K/DST scoring are not supported; custom/live features may require a paid tier. |
| [Footballguys current Draft Dominator](https://www.footballguys.com/plans) | You want current projections plus live sync and are willing to pay | Current custom ranking/live features are subscription products; a free preview is not the same thing. |
| [RotoBaller half-PPR rankings](https://www.rotoballer.com/fantasy-football-draft-rankings-august-updates-2026/1905031) | You need a second independent tier board | Rankings are generic half-PPR, not bonus-adjusted. |
| [FantasyPros weekly movers](https://www.fantasypros.com/2026/08/fantasy-football-risers-fallers-2026-nfl-preseason-week-1/) | You need trend context | Movement is a signal to investigate, not a reason to pay the new price. |

### Remove from the redraft core

- **KeepTradeCut and FantasyCalc:** primarily dynasty/trade-market tools. Their
  values are not a reliable one-QB redraft board.
- **PFF and RotoWire:** useful if already subscribed, but not necessary for the
  core free workflow.
- **CheatSheet King and Fantasy Football Fellas:** availability and custom-scoring
  fidelity were not strong enough to make them primary recommendations.
- **Reddit sheets:** useful idea generators, never the source of truth for injury,
  role, scoring, or ADP claims.

## Draft workflow

### 3-7 days before

- [ ] Confirm teams, roster slots, bench, IR, Flex/Superflex, keepers, and draft order.
- [ ] Confirm whether 40+ and 50+ bonuses stack.
- [ ] Import exact scoring into DraftKick, LineupExperts, or Footballguys Classic.
- [ ] Compare the custom output with FFToday half-PPR ADP.
- [ ] Apply the conservative ranking model only within established tiers.
- [ ] Refresh offensive-line starters, material injuries, and team context.
- [ ] Calculate position/archetype schedule ease with only a 2% preseason weight.
- [ ] Flag Weeks 1-4 separately for late-round players who need early usability.
- [ ] Mark each player as target, fair price, stop price, or avoid.
- [ ] Run at least three mocks from the actual draft slot.
- [ ] Test an early-QB, middle-QB, and late-QB build.

### Draft day

- [ ] Refresh injuries and depth-chart news.
- [ ] Refresh active offensive linemen and important opposing defensive injuries.
- [ ] Refresh the host-platform ADP, not only consensus ADP.
- [ ] Keep this guide, the custom board, and the live draft room in separate windows.
- [ ] Cross off players in one source of truth.
- [ ] Draft by tiers; do not chase a run after the tier has already emptied.
- [ ] Before every pick, ask: “Who is most likely to gain a round of value by Week 1?”

### Final rounds

- [ ] Prefer bench players with a plausible role change over low-ceiling veterans.
- [ ] Use IR eligibility rather than clogging a short bench.
- [ ] Select D/ST for early matchup and pressure potential.
- [ ] Select an accurate, secure kicker last.

## Sources and limitations

### Core sources

- [League scoring](./broncon24_league_scoring.txt) — local source of truth for
  scoring; retrieved August 21, 2026.
- [Generated player injury context](./player_injuries.md) and
  [machine-readable data](./player_injuries.json) — current games-missed tiers,
  confidence, evidence dates, and source links for all 300 ranked entities.
- [Generated position-specific schedule context](./strength_of_schedule.md) and
  [machine-readable data](./strength_of_schedule.json) — full-season and playoff
  opponent averages/ranks for all 32 teams at QB, RB, WR, TE, K, and D/ST; retrieved
  August 21, 2026 and used only as the guide's 2% preseason tiebreaker.
- [FFToday 12-team half-PPR ADP](https://www.fftoday.com/rankings/26-adp-half-ppr.html) —
  market data dated August 16, sourced from Underdog and Yahoo.
- [ESPN 2026 PPR Top 300](https://g.espncdn.com/s/ffldraftkit/26/NFL26_CS_PPR300.pdf?adddata=2026CS_PPR300) —
  updated August 19; 10-team, full-PPR, conventional scoring.
- [NFL.com late-round sleepers](https://www.nfl.com/news/2026-nfl-fantasy-football-six-late-round-sleepers-to-target) —
  role and player evidence; its recommendations use full PPR and ESPN ADP.
- [NFL.com late-round rookies](https://www.nfl.com/news/2026-nfl-fantasy-football-15-rookies-worth-a-late-round-draft-pick) —
  current rookie opportunity and Aug. 18 ESPN ADP context.
- [NFL.com values and risks](https://www.nfl.com/news/2026-nfl-fantasy-football-10-overvalued-undervalued-nfl-players-to-know-before-you-draft) —
  player arguments, not custom-scoring rankings.
- [Fantasy Alarm injury report](https://www.fantasyalarm.com/articles/nfl/fantasy-football-draft-guide/2026-offseason-fantasy-football-injury-report/190980) —
  updated August 20; secondary synthesis that should be refreshed against team news.
- [FantasyPros Draft Wizard FAQ](https://draftwizard.fantasypros.com/football/draft-tools/) —
  official support and custom-scoring limitations.
- [Footballguys Classic apps](https://www.footballguys.com/article/footballguys-classic-drafting-apps) and
  [plans](https://www.footballguys.com/plans) — official free-version and paid-feature boundaries.
- [LineupExperts premium plans](https://www.lineupexperts.com/Premium-Accounts) —
  official live-sync access boundary.
- [NFL Analytics 2026 schedule-strength audit](https://www.nflanalytic.com/explainer-2026-schedule-strength.html) —
  historical validation showing the weak predictive value of prior-record SOS.
- [FantasyPros SOS caution](https://www.fantasypros.com/2018/06/strength-of-schedule-should-not-influence-your-draft-strategy/) —
  ten-year fantasy-focused warning about preseason defensive volatility.
- [FantasyPros 2026 positional SOS](https://www.fantasypros.com/nfl/strength-of-schedule.php) —
  current position-specific schedule reference; use only as a cross-check.
- [nflfastR examples](https://github.com/nflverse/nflfastR/blob/master/vignettes/nflfastR.Rmd) —
  open play-by-play method for separate defensive pass/rush EPA calculations.
- [NFL Next Gen Stats pressure methodology](https://www.nfl.com/news/next-gen-stats-introduction-to-pressure-probability) —
  definitions for pressure, quick pressure, and pressure rate over expected.
- [Opponent-adjusted blocking research](https://arxiv.org/abs/2604.01491) —
  evidence that line outcomes depend on opponent, help, QB behavior, and context.
- [ESPN blocking win-rate methodology](https://www.espn.com/nfl/story/_/id/38356170/2023-nfl-pass-rush-run-s) —
  definitions for pass-block, pass-rush, and run-stop wins.
- [4for4 RB](https://www.4for4.com/2024/preseason/most-predictable-running-back-stats) and
  [WR predictability](https://www.4for4.com/2024/preseason/most-predictable-wide-receiver-stats) —
  historical stability and next-season predictiveness of opportunity and efficiency inputs.

### Confidence and open questions

**High confidence**

- The mathematical scoring deltas and examples
- The need to use half-PPR rather than the local ESPN PPR rank as the base
- The free/paid boundaries explicitly documented by tool providers
- The August 16 half-PPR ADP values cited above
- Context should refine rather than replace talent, opportunity, VORP, and tiers
- Preseason schedule strength should receive little weight because defensive and
  opponent quality changes substantially year to year

**Moderate confidence**

- Player target rounds, because room-specific ADP changes rapidly
- Role-based sleeper recommendations, because preseason usage is noisy
- Injury interpretation, because camp status can change in one practice
- The exact context-component weights; they are conservative decision heuristics,
  not coefficients fitted specifically to this league's historical results
- Current defensive and offensive-line grades, which require regular injury,
  personnel, and current-season data updates

**Must confirm**

- Bonus stacking
- Actual roster and lineup settings
- Draft slot and keeper cost
- Host-platform ADP on draft day
- Same-day injury and depth-chart reports
- League playoff weeks before applying a playoff-schedule component

This guide should be refreshed after the final major preseason games and again
within 24 hours of the league draft.
