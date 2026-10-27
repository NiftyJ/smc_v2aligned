## Round 6: an FVG has to be a real imbalance

**Category (round 5).** The largest is still extra `no_htf_poi` (148 of 268). Since round 5, every
sniper POI is an FVG, so the question is which FVGs you treat as POIs.

**What's behind it (development period; your marks from before the holdout):**

1. **Not the break-of-structure FVGs.** One idea was that only a gap left by the move that broke
   structure on its timeframe counts. Only 6 of your 27 FVG marks are of that kind. That is the same 25%
   as for all gaps, and all 6 bot sniper matches came from gaps that are not. So it was not tried.
2. **Size.** The gap's height in ATRs (14) of its own timeframe:

   | | smallest | 10% | 25% | median |
   |---|---|---|---|---|
   | your FVG marks (27 found in poi.py) | 0.45 | 0.67 | 0.81 | 1.04 |
   | all gaps on M15 / M30 / H1 / H4 | — | 0.04 | 0.11 | 0.24–0.28 |
   | the gaps behind the bot's extra trades | 0.01 | — | 0.18 | 0.39 |

   By timeframe, the median of your marks is M15 1.11, M30 1.33, H1 0.81 and H4 1.01. You mark only the
   big imbalances, roughly the top fifth of the gaps. The bot armed every gap.

**The threshold** comes from your marks and was fixed before the test: half an ATR. 96% of your marks are at
least that, and your smallest is 0.45. It was tested once and not tuned on the matches.

**Attempts (development period only):**

| attempt | rule | recall | precision | bot trades | result |
|---|---|---|---|---|---|
| round 5 | — | 8.2% | 2.90% | 276 | |
| **a** | **an FVG is a POI only if its gap is at least half an ATR of its timeframe** | **8.2%** | **3.86%** | **207** | **kept** |

**Effect on dev:**

| | round 5 | round 6 |
|---|---|---|
| recall | 8.2% | 8.2% |
| precision | 2.90% | 3.86% |
| bot trades | 276 | 207 |
| trades per week (yours: 3.3) | 9.3 | 6.9 |
| extras against your direction that week | 49 | 34 |
| extra `no_htf_poi` | 148 | 112 |

Recall stays at 8 matches, but the set changes. It gains #549, a momentum trade of yours caught by a
bot re-try at an H1 FVG. It loses #496, which the bot had caught from a tiny M15 gap.

**Finding: profit roughly halves.** The bot's results on dev:

| | round 5 | round 6 |
|---|---|---|
| win rate | 11.4% | 9.8% |
| mean R | +0.70R | +0.47R |
| total R | +190.6R | +95.5R |
| max drawdown | 51R | 49R |

The roughly 70 trades from small gaps were profitable for the bot: about +95R on dev, with no costs
(`COST = 0`) and the bot's tight stops. You don't trade those gaps, and the brief puts matching you
first, so the change is kept. This is a real trade-off for you to weigh. With realistic costs, the
small-gap trades would lose a good part of that, because their stops are tight.

**The cost in missed trades.** `no_detection:htf_poi` (no bot POI armed in your window) rises from 6
to 20. This is your trades where the only gap the bot had was a small one. None of them was matched
before.

Files: `strategy.py` (`Settings.FVG_MIN_ATR`, the POI filter in `_sniper`, the module docstring).
