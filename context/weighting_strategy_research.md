# Weighting strategy research

**Decision date:** 2026-08-25  
**League format used:** 12-team, half-PPR, 1 QB / 2 RB / 2 WR / 1 TE / 1 FLEX / K / DST  
**Roster caveat:** the supplied league export contains scoring but not roster slots, so the
starting lineup above is an explicit, editable assumption in `ranking_model.json`.

## Decision

Use an **ensemble projection plus corrected value-over-baseline** model as the primary
ranking signal. Score the simple mean of ESPN Mike Clay and FFToday raw-stat projections
under this league's rules, then compare players with position-aware replacement baselines.
Use market consensus and current-context signals as conservative guardrails.

This is the best-supported option for a static, preseason cheat sheet. Projection ensembles
have the strongest multi-season accuracy record of the candidate inputs, while corrected
value over baseline translates projected points into draft value without systematically
overvaluing scarce-looking one-starter positions.

## League-rule mapping

The scorer reads `broncon24_league_scoring.txt` on every rebuild. It applies:

- 0.05 points per passing yard, 4 per passing touchdown, and -2 per interception;
- 0.1 points per rushing or receiving yard;
- 5 points per rushing or receiving touchdown;
- 0.5 points per reception; and
- -2 points per fumble lost when a source supplies that statistic.

The two current projection feeds do not forecast long-touchdown, yardage-game, two-point,
or fumble counts. Those events are excluded and disclosed, rather than filled with a manual
constant. K and DST receive no projection-value premium and remain late, streamable picks.

## Alternatives appraised

| Heuristic | Track-record evidence | Fit for this league | Decision |
|---|---|---|---|
| ADP alone | In a 2015 validation, ADP explained less out-of-sample variance than aggregate projections (overall R-squared 0.23 versus 0.53). | Good market-price signal, but it does not encode custom 5-point skill TDs or passing bonuses. | Keep as part of the 30% consensus guardrail. |
| Expert-rank consensus | The same validation reported overall R-squared 0.27; FantasyPros also publishes a multi-year expert-accuracy methodology and leaderboard. RB expert ranks were more competitive than projections in that single-season test. | Useful at absorbing news and role uncertainty, but ranking gaps are ordinal rather than projected point gaps. | Keep in the baseline consensus. |
| Single projection source | Individual leaders vary by position and time window. In the 2014-2025 study, no provider dominated every position. | Can be custom-scored, but exposes the sheet to one model's assumptions. | Reject as the primary signal. |
| Projection ensemble | Fantasy Football Analytics' 2014-2025 comparison found source aggregation consistently strong; its simple average slightly beat its historical-error weighting overall. An older validation found aggregate projections at overall R-squared 0.53. | Directly supports custom scoring and reduces source-specific error. | Select as the forecast layer. |
| Static VBD using the first undrafted player | Captures positional scarcity, but a six-season oracle exercise found that this common baseline overvalued QB and TE in every tested year. | RB/WR replacement logic is useful, but a naive QB12/TE12 baseline is a poor 1QB adjustment. | Reject the naive baseline. |
| Corrected VBD | The same 2019-2024 exercise found a median-starter baseline (QB6/TE6 in a 12-team league) removed nearly all systematic QB/TE bias. Fry, Lundberg, and Ohlmann's draft simulations also found a dynamic value-based heuristic outperformed competing strategies on average. | Translates custom projected points into scarcity-aware value and corrects one-starter positions. | Select as the valuation layer. |
| Dynamic value over next available | The academic simulation supports reacting to likely availability at the next pick. | Potentially strongest during a live draft, but cannot be represented faithfully by one static ordering without the user's draft slot and live selections. | Future live-draft enhancement, not the sheet's base ordering. |

## Implemented formula

```text
base score =
    60% custom-scored ensemble value over baseline
  + 30% baseline consensus (ESPN rank + FantasyPros ECR + FFToday ADP)
  +  5% opportunity/depth-chart context
  +  2% team scoring environment
  +  2% offensive-line fit
  +  1% position-specific schedule
  - injury/risk penalty (capped at 5 points)
```

The evidence validates **projection averaging** and **corrected replacement baselines**;
it does not prove that 60/30/5/2/2/1 is a universally optimal coefficient vector. The outer
weights are a conservative implementation choice: projections get roughly twice the weight
of ordinal consensus, current context gets 10% total, and the existing movement caps prevent
the model from making unstable leaps on small score differences. A true optimization of those
coefficients would require several seasons of archived preseason inputs and league outcomes,
which are not available in this repository.

## Replacement calculation

- RB and WR: simulate all dedicated starters, then allocate the league's flex spots to the
  highest remaining RB/WR/TE projections. The best unselected player at each position is its
  replacement baseline.
- QB and TE: use the median starter (QB6 and TE6 under the assumed 12-team, one-starter
  format), the correction with the strongest direct multi-year backtest found in this review.
- K and DST: zero projected-value premium; use late-round/streaming guidance.

## Sources and evidence quality

- [Fantasy Football Analytics, 2014-2025 projection accuracy](https://fantasyfootballanalytics.net/which-projections-are-most-accurate): twelve-season, position-level MAE comparison; strongest direct evidence for averaging projections. The site is an analytics vendor, but publishes its metric, seasons, player cutoffs, and tables.
- [Fantasy Football Analytics, rankings versus projections](https://fantasyfootballanalytics.net/2016/04/accuracy-of-rankings-vs-projections.html): older single-season out-of-sample comparison of projections, ECR, and ADP; useful corroboration, not sufficient alone.
- [Fry, Lundberg, and Ohlmann, Journal of Quantitative Analysis in Sports](https://iro.uiowa.edu/esploro/outputs/journalArticle/A-Player-Selection-Heuristic-for-a/9984380640402771): peer-reviewed simulation evidence for dynamic value-based drafting; old and based on the 2005 season, so it supports the framework rather than today's coefficients.
- [RotoAlpha QB/TE baseline study](https://rotoalpha.com/nfl/articles/fantasy-football-when-to-draft-qb-and-te): transparent 2019-2024 oracle test of replacement definitions. It is a vendor analysis rather than peer-reviewed research, but directly tests the one-QB/one-TE bias this model must avoid.
- [RotoAlpha kicker analysis](https://rotoalpha.com/nfl/articles/fantasy-football-when-to-draft-a-kicker): supports treating kicker and defense as late, streamable positions rather than granting them misleading VBD.
- [FantasyPros draft accuracy methodology](https://www.fantasypros.com/about/faq/football-draft-accuracy-methodology/): documents half-PPR expert-rank evaluation and draft-relevant weighting.
- [ESPN Mike Clay 2026 Projection Guide](https://g.espncdn.com/s/ffldraftkit/26/NFLDK2026_CS_ClayProjections2026.pdf) and [FFToday 2026 projections](https://www.fftoday.com/rankings/playerproj.php): the two complete, machine-readable current raw-stat inputs. FantasyPros' public projection page was evaluated but exposes only a partial table without authentication, so it is not used as an automated projection feed.

## Limitations

- The strongest historical tests evaluate projection accuracy or simulated draft points, not
  this exact league's championship rate.
- Scoring bonuses absent from projection feeds are omitted. This most affects high-volume and
  explosive players; the market-consensus guardrail partially limits the omission's impact.
- The roster-slot assumption materially affects baselines. Update it if the league uses a
  different number of starters or flexes.
- Inputs are preseason snapshots. Rebuild close to the draft to incorporate current roles,
  injuries, and market prices.
