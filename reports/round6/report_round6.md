# Round 6: the bot against your trades (development period 2024-01-05 -> 2024-07-31)

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

## The numbers

| dev | value |
|---|---|
| my trades | 97 (70 filled) |
| bot trades | 207 (204 filled) |
| **recall** = both / my trades | **8.2%** (8 / 97) |
| **precision** = both / bot trades | **3.9%** (8 / 207) |
| duplicates | 0 |
| extra | 199 |
| placement differences | 5 |
| bot trades per week, against mine | 6.9 / 3.3 |
| the bot's results (limits on = the same run) | 204 filled, win rate 9.8%, mean +0.47R, total +95.5R, max DD 49.0R |
| the bot's results on **both** trades only | 7 filled, win rate 28.6%, mean +2.71R, total +19.0R, max DD 3.0R |
| the bot's results on **extra** trades only | 197 filled, win rate 9.1%, mean +0.39R, total +76.5R, max DD 48.0R |
| the bot's results on duplicates only | no fills |
| recall by your order | half 1/23 (4%), limit 7/71 (10%), market 0/3 (0%) |
| recall by your subtype | momentum 1/23 (4%), sniper 7/74 (9%) |
| matched / (matched + extra) by bot rule | momentum 2/36, sniper 6/171 |

Results are in R with no costs (the bot's default `COST = 0`). Your own R is not compared: your targets were drawn afterwards.

## Missed trades: why the bot didn't take yours

| category | trades | share |
|---|---|---|
| no_detection:htf_poi | 20 | 22% |
| other | 16 | 18% |
| blocked_by_filter:bias_d1 | 13 | 15% |
| no_detection:m5_bos | 12 | 13% |
| no_detection:m1_bos | 9 | 10% |
| no_detection:m5_pause | 6 | 7% |
| timing | 4 | 4% |
| wrong_direction | 3 | 3% |
| entry_type | 2 | 2% |
| blocked_by_filter:bias_h1 | 2 | 2% |
| blocked_by_filter:one_setup_per_poi | 2 | 2% |

Each missed trade, its category, the condition that failed and the values: `why_not_dev.csv`.

**no_detection:htf_poi** (20), e.g.:

- #257 2024-01-05 04:25 short limit: no POI armed. your POI: H4 fvg #239 01-03 08:00 2049.97-2058.62; H1 fvg #240 01-03 10:00 2048.65-2052.61 | bot POIs nearest in time: 15min FVG 2042.49-2044.01 armed 01-05 06:57->01-05 07:11; 30min FVG 2042.61-2043.81 armed 01-05 07:02->01-05 07:08; 15min FVG 2039.14-2040.99 armed 01-05 10:54->01-05 13:20 | bias D1 +0 H4 +0 H1 -1 at the end of the window (the trend allowed your way 0% of it)
- #18 2024-01-05 16:17 short market: no POI armed. your POI: H1 ob #58 01-05 15:00 2057.08-2064.01 | bot POIs nearest in time: 15min FVG 2045.18-2050.10 armed 01-05 17:23->01-08 04:00; 30min FVG 2039.14-2041.63 armed 01-05 10:54->01-05 14:00; 30min FVG 2045.35-2049.72 armed 01-05 18:39->01-05 19:10 | bias D1 +0 H4 +0 H1 +1 at the end of the window (the trend allowed your way 0% of it)
- #90 2024-01-19 14:28 short limit: no POI armed. your POI: H1 fvg #74 01-16 15:00 2033.86-2037.49 | bot POIs nearest in time: 15min FVG 2029.71-2031.63 armed 01-19 15:00->01-22 01:11; 30min FVG 2031.98-2034.13 armed 01-19 15:00->01-22 14:00; 15min FVG 2021.52-2022.28 armed 01-19 05:32->01-19 06:21 | bias D1 +0 H4 -1 H1 -1 at the end of the window (the trend allowed your way 0% of it)

**other** (16), e.g.:

- #419 2024-03-04 06:47 long limit: the bot took the same direction in your window at another level. bot #5 long sniper | 1h FVG | next range (3) decided 03-04 02:50 entry 2083.16 (1.52R from yours, -237 min)
- #502 2024-03-26 15:46 long limit: the bot took the same direction in your window at another level. bot #32 long sniper | 1h FVG | first range decided 03-26 13:17 entry 2187.91 (6.62R from yours, -149 min)
- #507 2024-03-27 09:19 long limit: same idea, the bot's limit 0.5-1.5R from yours. bot #33 long sniper | 15min FVG | first range decided 03-27 04:14 entry 2177.42 (1.19R from yours, -305 min)

**blocked_by_filter:bias_d1** (13), e.g.:

- #49 2024-01-09 15:33 short limit: sweep + break, but the trend disagrees (the POI is used up). at 01-09 12:42: D1 +0 H4 +0 H1 -1 (your direction -1)
- #70 2024-01-16 15:44 short limit: sweep + break, but the trend disagrees (the POI is used up). at 01-16 11:47: D1 +0 H4 -1 H1 -1 (your direction -1)
- #81 2024-01-17 03:34 short limit: sweep + break, but the trend disagrees (the POI is used up). at 01-16 20:56: D1 +0 H4 -1 H1 -1 (your direction -1)

**no_detection:m5_bos** (12), e.g.:

- #144 2024-01-29 16:25 long half: no M5 break of structure. your ranges: H4 range staircase #320 01-29 00:00 2019.19-2055.91; M1 range pause #142 01-29 15:40 2023.69-2026.89; M1 range pause #146 01-29 16:20 2024.27-2026.11 | bias D1 +0 H4 -1 H1 +1 at the end of the window (the trend allowed your way 0% of it)
- #174 2024-02-02 15:59 long half: no M5 break of structure. your ranges: M5 range staircase #180 02-02 15:35 2032.49-2037.96; M1 range pause #175 02-02 15:38 2031.99-2035.03 | bias D1 +0 H4 +1 H1 +1 at the end of the window (the trend allowed your way 0% of it)
- #195 2024-02-05 00:01 short half: no M5 break of structure. your ranges: M1 range pause #194 02-04 23:45 2037.83-2040.04 | bias D1 +0 H4 +1 H1 +1 at the end of the window (the trend allowed your way 0% of it)

## Extra trades: why you wouldn't take the bot's

| category | trades | share |
|---|---|---|
| no_htf_poi | 112 | 56% |
| against_htf | 34 | 17% |
| inside_range | 16 | 8% |
| weak_break | 11 | 6% |
| no_sweep | 9 | 5% |
| chop_day | 8 | 4% |
| other | 5 | 3% |
| duplicate | 4 | 2% |

A trade can have several reasons; the category is the first in the order of `tools/explain_extra.py`. All reasons, counted separately:

| category | trades | share |
|---|---|---|
| no_htf_poi | 146 | 73% |
| duplicate | 93 | 47% |
| chop_day | 81 | 41% |
| weak_break | 74 | 37% |
| inside_range | 56 | 28% |
| against_htf | 34 | 17% |
| no_sweep | 33 | 17% |

