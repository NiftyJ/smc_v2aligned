# Round 1: the bot against your trades (development period 2024-01-05 -> 2024-07-31)

## Round 1: where the bot trades from

**Largest category (round 0):** extra `no_htf_poi`, 123 of the 228 extra trades (54%). The bot traded
where you had marked no POI on M15 or higher.

**What's behind it.** The bot's POI was always an order block (M15, M30 or H1). 55 of the 70 zones you
marked on M15 or higher are fair value gaps, so the bot was trading from a different kind of zone than you.
Part of the category isn't about zones at all: 73 of the 171 extra trades with this flag came when you had
no live POI mark in that direction anywhere. You weren't looking for a trade then. A POI rule can't
reproduce that on its own, and later rounds deal with direction and frequency.

**Attempts (development period only):**

| attempt | rule | recall | precision | bot trades | result |
|---|---|---|---|---|---|
| baseline | — | 3.1% | 1.3% | 232 | |
| a | an M15/M30/H1 POI counts only if it sits inside an H1/H4 order block or FVG of its direction | 2.1% | 1.2% | 160 | rejected: both fell |
| b | POIs are H1/H4 order blocks only | 2.1% | 2.1% | 94 | rejected: recall fell 1.0 pt, more than precision gained (0.8 pt) |
| **c** | **an FVG is a POI too: the latest M15/M30/H1 FVG of the trade's direction, from its first touch** | **8.2%** | **1.7%** | 473 | **kept** |
| d | as c, but the POIs are on H1/H4 | 3.1% | 1.3% | 230 | not kept: no change |

**The rule kept:** an FVG counts as a POI as well as an order block. On M15, M30 and H1, the most recent
fair value gap of the trade's direction arms the M1 entry from the first time price trades into it. A newer
FVG replaces it, and a close beyond its far edge (an FVG's "higher low") ends it. Everything after the touch
is unchanged: M1 sweep, M1 break, limit at the M1 order block, one setup per touch, up to 3 tries.

**Effect on dev:** recall 3.1% → 8.2%. Your sniper trades matched went from 1 to 6, and the bot's momentum
trades still match 2 of your sniper trades. Precision 1.3% → 1.7%. The cost is frequency: the bot now
trades 15.9 times a week against your 3.3, twice as often as before. Its extra trades not at one of your
POIs fell from 54% to 50% of extras. The 8 matched trades made +19.0R; all bot trades made +238.5R
(was +147.7R), with max drawdown 64.8R (was 52.0R).

Files: `strategy.py` (FVG POIs, setting `POI_KINDS`), `live_mt5.py` (an FVG POI's order gets its own
name, so the "never send twice" check keeps it apart from an order block known at the same candle),
`tools/common.py` and `tools/why_not.py` (show OB or FVG), and `tests/test_strategy.py` (tries are counted
per POI, not per touch time).

## The numbers

| dev | value |
|---|---|
| my trades | 97 (70 filled) |
| bot trades | 473 (470 filled) |
| **recall** = both / my trades | **8.2%** (8 / 97) |
| **precision** = both / bot trades | **1.7%** (8 / 473) |
| duplicates | 1 |
| extra | 464 |
| placement differences | 6 |
| bot trades per week, against mine | 15.9 / 3.3 |
| the bot's results (limits on = the same run) | 470 filled, win rate 9.4%, mean +0.51R, total +238.5R, max DD 64.8R |
| the bot's results on **both** trades only | 7 filled, win rate 28.6%, mean +2.71R, total +19.0R, max DD 3.0R |
| the bot's results on **extra** trades only | 462 filled, win rate 9.1%, mean +0.48R, total +220.5R, max DD 63.8R |
| the bot's results on duplicates only | 1 filled, win rate 0.0%, mean -1.00R, total -1.0R, max DD 1.0R |
| recall by your order | half 0/23 (0%), limit 8/71 (11%), market 0/3 (0%) |
| recall by your subtype | momentum 0/23 (0%), sniper 8/74 (11%) |
| matched / (matched + extra) by bot rule | momentum 2/40, sniper 6/432 |

Results are in R with no costs (the bot's default `COST = 0`). Your own R is not compared: your targets were drawn afterwards.

## Missed trades: why the bot didn't take yours

| category | trades | share |
|---|---|---|
| other | 26 | 29% |
| blocked_by_filter:bias_d1 | 13 | 15% |
| no_detection:m5_bos | 11 | 12% |
| no_detection:m1_bos | 8 | 9% |
| wrong_direction | 8 | 9% |
| no_detection:m5_pause | 6 | 7% |
| timing | 6 | 7% |
| no_detection:htf_poi | 3 | 3% |
| blocked_by_filter:bias_h4 | 3 | 3% |
| blocked_by_filter:one_setup_per_poi | 2 | 2% |
| entry_type | 2 | 2% |
| no_detection:m1_sweep | 1 | 1% |

Each missed trade, its category, the condition that failed and the values: `why_not_dev.csv`.

**other** (26), e.g.:

- #437 2024-03-14 17:50 long limit: same idea, the bot's limit 0.5-1.5R from yours. bot #85 long sniper | 1h OB | first range decided 03-14 13:21 entry 2162.24 (0.70R from yours, -269 min)
- #451 2024-03-21 23:59 long limit: the bot took the same direction in your window at another level. bot #97 long sniper | 1h FVG | first range decided 03-21 20:09 entry 2180.55 (1.91R from yours, -230 min)
- #484 2024-03-25 05:38 long limit: the bot took the same direction in your window at another level. bot #104 long sniper | 30min FVG | first range decided 03-25 03:49 entry 2170.72 (1.64R from yours, -109 min)

**blocked_by_filter:bias_d1** (13), e.g.:

- #49 2024-01-09 15:33 short limit: sweep + break, but D1 / H4 bias disagree (the POI is used up). at 01-09 12:42: D1 +0 H4 +0 (your direction -1)
- #70 2024-01-16 15:44 short limit: sweep + break, but D1 / H4 bias disagree (the POI is used up). at 01-16 11:47: D1 +0 H4 -1 (your direction -1)
- #81 2024-01-17 03:34 short limit: sweep + break, but D1 / H4 bias disagree (the POI is used up). at 01-16 20:56: D1 +0 H4 -1 (your direction -1)

**no_detection:m5_bos** (11), e.g.:

- #144 2024-01-29 16:25 long half: no M5 break of structure. your ranges: H4 range staircase #320 01-29 00:00 2019.19-2055.91; M1 range pause #142 01-29 15:40 2023.69-2026.89; M1 range pause #146 01-29 16:20 2024.27-2026.11 | bias D1 +0 H4 -1 at the end of the window (0% of it agreeing)
- #174 2024-02-02 15:59 long half: no M5 break of structure. your ranges: M5 range staircase #180 02-02 15:35 2032.49-2037.96; M1 range pause #175 02-02 15:38 2031.99-2035.03 | bias D1 +0 H4 +1 at the end of the window (0% of it agreeing)
- #195 2024-02-05 00:01 short half: no M5 break of structure. your ranges: M1 range pause #194 02-04 23:45 2037.83-2040.04 | bias D1 +0 H4 +1 at the end of the window (0% of it agreeing)

**no_detection:m1_bos** (8), e.g.:

- #90 2024-01-19 14:28 short limit: swept, waiting for the break. bot POI 15min OB 2023.06-2025.49; bot M1 swing low 2022.22 high 2020.62, break level 2020.62 | yours: M1 structure BOS #89 01-19 14:23 2031.72 | bias D1 +0 H4 -1 at the end of the window (0% of it agreeing)
- #117 2024-01-24 14:18 short limit: swept, waiting for the break. bot POI 15min OB 2024.12-2025.58; bot M1 swing low 2025.56 high 2023.54, break level 2023.54 | yours: M1 structure BOS #101 01-24 09:01 2029.79; M1 structure BOS #114 01-24 12:16 2031.50 | bias D1 +0 H4 -1 at the end of the window (0% of it agreeing)
- #371 2024-02-28 11:24 long limit: swept, waiting for the break. bot POI 15min FVG 2025.86-2026.67; bot M1 swing low 2026.76 high 2027.80, break level 2027.80 | yours: M1 structure BOS #370 02-28 10:45 2027.53; M1 structure BOS #375 02-28 12:14 2029.17; M1 structure BOS #378 02-28 12:36 2029.09 | bias D1 -1 H4 +1 at the end of the window (0% of it agreeing)

## Extra trades: why you wouldn't take the bot's

| category | trades | share |
|---|---|---|
| no_htf_poi | 233 | 50% |
| against_htf | 107 | 23% |
| inside_range | 40 | 9% |
| chop_day | 25 | 5% |
| weak_break | 18 | 4% |
| other | 16 | 3% |
| duplicate | 13 | 3% |
| no_sweep | 12 | 3% |

A trade can have several reasons; the category is the first in the order of `tools/explain_extra.py`. All reasons, counted separately:

| category | trades | share |
|---|---|---|
| no_htf_poi | 332 | 72% |
| chop_day | 271 | 58% |
| duplicate | 177 | 38% |
| inside_range | 158 | 34% |
| weak_break | 152 | 33% |
| against_htf | 107 | 23% |
| no_sweep | 37 | 8% |

