# Round 5: the bot against your trades (development period 2024-01-05 -> 2024-07-31)

## Round 5: the POI is a fair value gap

**Category (round 4).** The largest is still extra `no_htf_poi` (202 of 364): the bot traded where
you had marked no zone.

**What's behind it.** Splitting the bot's dev trades by the POI that armed them:

| bot POI | extra | matched |
|---|---|---|
| M15 FVG | 83 | 4 |
| M30 FVG | 70 | 2 |
| H1 FVG | 56 | 0 |
| M15 order block | 58 | 0 |
| M30 order block | 42 | 0 |
| H1 order block | 21 | 0 |
| (momentum) | 34 | 2 |

None of the bot's 121 trades from order-block POIs matched one of yours. Your own marks point the
same way:
- 36 of your 44 zone marks on M15 or higher are FVGs, and 8 are order blocks.
- In your sniper setups: 19 FVGs and 6 order blocks.
- 12 setups mark only FVGs, 5 only order blocks, 1 both.

**Attempts (development period only):**

| attempt | rule | recall | precision | bot trades | result |
|---|---|---|---|---|---|
| round 4 | — | 8.2% | 2.14% | 373 | |
| a | the sweep must take a low made at the POI (after price reached it), not a low left on the way into it | 4.1% | 1.22% | 329 | rejected: both fell. The trades that matched yours were the quick ones: the sweep on the way into the POI. |
| **b** | **the sniper's POI is a fair value gap on M15/M30/H1; order blocks no longer arm it** | **8.2%** | **2.90%** | **276** | **kept** |

**The rule kept:** the sniper trades the first touch of the latest fair value gap of its direction on
M15, M30 or H1. Order blocks are no longer POIs on their own. Setting `POI_KINDS = ("ob", "fvg")` brings
them back.

**Effect on dev:**

| | round 4 | round 5 |
|---|---|---|
| recall | 8.2% | 8.2% (all 8 matches kept) |
| precision | 2.14% | 2.90% |
| bot trades | 373 | 276 |
| trades per week (yours: 3.3) | 12.5 | 9.3 |
| extras against your direction that week | 73 | 49 |
| duplicates | 1 | 0 |
| extra `no_htf_poi` | 202 | 148 |
| win rate | 10.5% | 11.4% |
| mean R | +0.57R | +0.70R |
| total R | +210.6R | +190.6R |
| max drawdown | 66R | 51R |

**The cost.** Your setups built on an order block (5 of 18 with a zone mark) now get no POI from the
bot. None of them was matched before. Two missed categories grow, as trades move into them from
`other` and `one_setup_per_poi`:
- `no_detection:htf_poi`: 3 → 6
- `no_detection:m1_bos`: 8 → 13

Your journal describes the order block as the POI, but your labels mark FVGs. If some order blocks are
POIs for you (for example, only an order block that left an FVG), say which, and that can come back
as its own rule.

Files: `strategy.py` (`Settings.POI_KINDS` and the module docstring). Rejected attempt:
`reports/rejected/round5a_sweep_of_a_low_made_at_the_poi.diff`.

## The numbers

| dev | value |
|---|---|
| my trades | 97 (70 filled) |
| bot trades | 276 (273 filled) |
| **recall** = both / my trades | **8.2%** (8 / 97) |
| **precision** = both / bot trades | **2.9%** (8 / 276) |
| duplicates | 0 |
| extra | 268 |
| placement differences | 5 |
| bot trades per week, against mine | 9.3 / 3.3 |
| the bot's results (limits on = the same run) | 273 filled, win rate 11.4%, mean +0.70R, total +190.6R, max DD 51.0R |
| the bot's results on **both** trades only | 7 filled, win rate 28.6%, mean +2.71R, total +19.0R, max DD 3.0R |
| the bot's results on **extra** trades only | 266 filled, win rate 10.9%, mean +0.65R, total +171.6R, max DD 49.0R |
| the bot's results on duplicates only | no fills |
| recall by your order | half 0/23 (0%), limit 8/71 (11%), market 0/3 (0%) |
| recall by your subtype | momentum 0/23 (0%), sniper 8/74 (11%) |
| matched / (matched + extra) by bot rule | momentum 2/36, sniper 6/240 |

Results are in R with no costs (the bot's default `COST = 0`). Your own R is not compared: your targets were drawn afterwards.

## Missed trades: why the bot didn't take yours

| category | trades | share |
|---|---|---|
| other | 20 | 22% |
| blocked_by_filter:bias_d1 | 17 | 19% |
| no_detection:m1_bos | 13 | 15% |
| no_detection:m5_bos | 12 | 13% |
| no_detection:htf_poi | 6 | 7% |
| no_detection:m5_pause | 6 | 7% |
| timing | 5 | 6% |
| blocked_by_filter:bias_h1 | 3 | 3% |
| wrong_direction | 3 | 3% |
| entry_type | 2 | 2% |
| blocked_by_filter:one_setup_per_poi | 1 | 1% |
| no_detection:m1_sweep | 1 | 1% |

Each missed trade, its category, the condition that failed and the values: `why_not_dev.csv`.

**other** (20), e.g.:

- #451 2024-03-21 23:59 long limit: the bot took the same direction in your window at another level. bot #39 long sniper | 1h FVG | first range decided 03-21 20:09 entry 2180.56 (1.92R from yours, -230 min)
- #494 2024-03-26 04:57 long limit: order placed. bias D1 +1 H4 +1 H1 +1 at the end of the window (the trend allowed your way 57% of it)
- #502 2024-03-26 15:46 long limit: the bot took the same direction in your window at another level. bot #44 long sniper | 1h FVG | first range decided 03-26 13:17 entry 2187.91 (6.62R from yours, -149 min)

**blocked_by_filter:bias_d1** (17), e.g.:

- #49 2024-01-09 15:33 short limit: sweep + break, but the trend disagrees (the POI is used up). at 01-09 12:42: D1 +0 H4 +0 H1 -1 (your direction -1)
- #70 2024-01-16 15:44 short limit: sweep + break, but the trend disagrees (the POI is used up). at 01-16 11:47: D1 +0 H4 -1 H1 -1 (your direction -1)
- #81 2024-01-17 03:34 short limit: sweep + break, but the trend disagrees (the POI is used up). at 01-16 20:56: D1 +0 H4 -1 H1 -1 (your direction -1)

**no_detection:m1_bos** (13), e.g.:

- #117 2024-01-24 14:18 short limit: swept, waiting for the break. bot POI 30min FVG 2026.06-2026.34; bot M1 swing low 2025.45 high 2024.63, break level 2024.63 | yours: M1 structure BOS #101 01-24 09:01 2029.79; M1 structure BOS #114 01-24 12:16 2031.50 | bias D1 +0 H4 -1 H1 +1 at the end of the window (the trend allowed your way 0% of it)
- #371 2024-02-28 11:24 long limit: swept, waiting for the break. bot POI 15min FVG 2025.86-2026.67; bot M1 swing low 2026.76 high 2027.80, break level 2027.80 | yours: M1 structure BOS #370 02-28 10:45 2027.53; M1 structure BOS #375 02-28 12:14 2029.17; M1 structure BOS #378 02-28 12:36 2029.09 | bias D1 -1 H4 +1 H1 -1 at the end of the window (the trend allowed your way 0% of it)
- #419 2024-03-04 06:47 long limit: swept, waiting for the break. bot POI 15min FVG 2083.87-2084.55; bot M1 swing low 2084.91 high 2086.12, break level 2086.12 | yours: M1 structure BOS #418 03-04 02:50 2083.39 | bias D1 +1 H4 +1 H1 +1 at the end of the window (the trend allowed your way 100% of it)

**no_detection:m5_bos** (12), e.g.:

- #144 2024-01-29 16:25 long half: no M5 break of structure. your ranges: H4 range staircase #320 01-29 00:00 2019.19-2055.91; M1 range pause #142 01-29 15:40 2023.69-2026.89; M1 range pause #146 01-29 16:20 2024.27-2026.11 | bias D1 +0 H4 -1 H1 +1 at the end of the window (the trend allowed your way 0% of it)
- #174 2024-02-02 15:59 long half: no M5 break of structure. your ranges: M5 range staircase #180 02-02 15:35 2032.49-2037.96; M1 range pause #175 02-02 15:38 2031.99-2035.03 | bias D1 +0 H4 +1 H1 +1 at the end of the window (the trend allowed your way 0% of it)
- #195 2024-02-05 00:01 short half: no M5 break of structure. your ranges: M1 range pause #194 02-04 23:45 2037.83-2040.04 | bias D1 +0 H4 +1 H1 +1 at the end of the window (the trend allowed your way 0% of it)

## Extra trades: why you wouldn't take the bot's

| category | trades | share |
|---|---|---|
| no_htf_poi | 148 | 55% |
| against_htf | 49 | 18% |
| inside_range | 23 | 9% |
| weak_break | 16 | 6% |
| chop_day | 9 | 3% |
| no_sweep | 9 | 3% |
| other | 8 | 3% |
| duplicate | 6 | 2% |

A trade can have several reasons; the category is the first in the order of `tools/explain_extra.py`. All reasons, counted separately:

| category | trades | share |
|---|---|---|
| no_htf_poi | 194 | 72% |
| chop_day | 144 | 54% |
| duplicate | 102 | 38% |
| weak_break | 92 | 34% |
| inside_range | 81 | 30% |
| against_htf | 49 | 18% |
| no_sweep | 33 | 12% |

