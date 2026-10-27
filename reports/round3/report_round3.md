# Round 3: the bot against your trades (development period 2024-01-05 -> 2024-07-31)

## Round 3: where the limit sits

**Categories (round 2).** The two largest are extra `no_htf_poi` (206) and `against_htf` (75). Rounds 1
and 2 worked on those, and more ideas aimed at them failed the keep rule:

- Premium/discount: buy only in the lower half of the H1/H4/D1 dealing range. Your entries are deeper in
  the range than the bot's extras (median 0.48 of the H1 range against 0.75), but 6 of the 8 matched trades
  are in the upper half, so it would cost far more recall than it gains in precision.
- M5/M15 structure your way: no separation.

So this round went down the list. The largest missed category is `other` (21): the bot took your
direction in your window, but its limit sat at another level.

**What's behind it.** The why-not trace over those windows shows two patterns:

1. The bot's sniper stops are tiny. 43% are under one M1 ATR (median 1.1 ATR), against 11% of yours
   (median 2.65 ATR). They are hit within minutes, and the POI's setups are used up.
2. Your long limits sit at the top of the M1 order block or FVG (median position 1.00 in the zone). The
   bot's sit at the candle's open, below the top by the upper wick.

**Attempts (development period only):**

| attempt | rule | recall | precision | result |
|---|---|---|---|---|
| round 2 | — | 8.2% | 2.13% | |
| a | momentum on M1: an M1 pause range and an M1 break | 8.2% | 1.8% | rejected. Still 0 of your 23 momentum trades. The bot's pause detector needs a 6-ATR impulse first, and is on at only 4% of your momentum decisions. Your trigger close is inside the range, not a breakout. |
| b | the M1 break must leave an FVG (displacement) | 7.2% | 1.9% | rejected: both fell |
| c | skip setups whose stop is closer than 1 M1 ATR (MIN_RISK_ATR 0.25 → 1.0) | 4.1% | 1.6% | rejected: 4 of the 6 matched sniper trades had tight bot stops |
| e | check the trend before the POI is used up | 8.2% | 2.08% | rejected: 9 more trades, none matched |
| **f** | **the limit sits at the high of the M1 order block (the low, for shorts)** | **8.2%** | **2.14%** | **kept** |

**The rule kept:** the sniper's limit goes at the top of the M1 order block (its high) for a long and the
bottom (its low) for a short, where you put yours, instead of at the candle's open. The stop is unchanged.

**Effect on dev:** recall 8.2% (unchanged), precision 2.13% → 2.14%. Placement differences on matched
trades went from 6 to 5 of 8. The mean entry gap to yours fell from 0.24R to 0.18R. Bot trades 376 →
373, and extras against your direction 75 → 73. The bot's results: +210.6R (was +226.2R), win rate 10.5%
(was 10.2%), max drawdown 66.0R. The higher limit fills more often but at a worse price.

The headline numbers barely move. The change is kept because it moves the bot's entries to where you
place yours and passes the keep rule. It is not a recall gain.

Files: `strategy.py` (`place()` and the module docstring). Rejected attempts: `reports/rejected/round3*.diff`.
Attempt c was a settings value only, so it has no diff.

## The numbers

| dev | value |
|---|---|
| my trades | 97 (70 filled) |
| bot trades | 373 (370 filled) |
| **recall** = both / my trades | **8.2%** (8 / 97) |
| **precision** = both / bot trades | **2.1%** (8 / 373) |
| duplicates | 1 |
| extra | 364 |
| placement differences | 5 |
| bot trades per week, against mine | 12.5 / 3.3 |
| the bot's results (limits on = the same run) | 370 filled, win rate 10.5%, mean +0.57R, total +210.6R, max DD 66.0R |
| the bot's results on **both** trades only | 7 filled, win rate 28.6%, mean +2.71R, total +19.0R, max DD 3.0R |
| the bot's results on **extra** trades only | 362 filled, win rate 10.2%, mean +0.53R, total +192.6R, max DD 64.0R |
| the bot's results on duplicates only | 1 filled, win rate 0.0%, mean -1.00R, total -1.0R, max DD 1.0R |
| recall by your order | half 0/23 (0%), limit 8/71 (11%), market 0/3 (0%) |
| recall by your subtype | momentum 0/23 (0%), sniper 8/74 (11%) |
| matched / (matched + extra) by bot rule | momentum 2/36, sniper 6/336 |

Results are in R with no costs (the bot's default `COST = 0`). Your own R is not compared: your targets were drawn afterwards.

## Missed trades: why the bot didn't take yours

| category | trades | share |
|---|---|---|
| other | 21 | 24% |
| blocked_by_filter:bias_d1 | 16 | 18% |
| no_detection:m5_bos | 12 | 13% |
| no_detection:m1_bos | 8 | 9% |
| no_detection:m5_pause | 6 | 7% |
| blocked_by_filter:bias_h1 | 5 | 6% |
| timing | 5 | 6% |
| wrong_direction | 4 | 4% |
| blocked_by_filter:one_setup_per_poi | 3 | 3% |
| no_detection:htf_poi | 3 | 3% |
| blocked_by_filter:bias_h4 | 3 | 3% |
| entry_type | 2 | 2% |
| no_detection:m1_sweep | 1 | 1% |

Each missed trade, its category, the condition that failed and the values: `why_not_dev.csv`.

**other** (21), e.g.:

- #451 2024-03-21 23:59 long limit: the bot took the same direction in your window at another level. bot #58 long sniper | 1h FVG | first range decided 03-21 20:09 entry 2180.56 (1.92R from yours, -230 min)
- #494 2024-03-26 04:57 long limit: order placed. bias D1 +1 H4 +1 H1 +1 at the end of the window (the trend allowed your way 57% of it)
- #502 2024-03-26 15:46 long limit: the bot took the same direction in your window at another level. bot #63 long sniper | 1h FVG | first range decided 03-26 13:17 entry 2187.91 (6.62R from yours, -149 min)

**blocked_by_filter:bias_d1** (16), e.g.:

- #49 2024-01-09 15:33 short limit: sweep + break, but the trend disagrees (the POI is used up). at 01-09 12:42: D1 +0 H4 +0 H1 -1 (your direction -1)
- #70 2024-01-16 15:44 short limit: sweep + break, but the trend disagrees (the POI is used up). at 01-16 11:47: D1 +0 H4 -1 H1 -1 (your direction -1)
- #81 2024-01-17 03:34 short limit: sweep + break, but the trend disagrees (the POI is used up). at 01-16 20:56: D1 +0 H4 -1 H1 -1 (your direction -1)

**no_detection:m5_bos** (12), e.g.:

- #144 2024-01-29 16:25 long half: no M5 break of structure. your ranges: H4 range staircase #320 01-29 00:00 2019.19-2055.91; M1 range pause #142 01-29 15:40 2023.69-2026.89; M1 range pause #146 01-29 16:20 2024.27-2026.11 | bias D1 +0 H4 -1 H1 +1 at the end of the window (the trend allowed your way 0% of it)
- #174 2024-02-02 15:59 long half: no M5 break of structure. your ranges: M5 range staircase #180 02-02 15:35 2032.49-2037.96; M1 range pause #175 02-02 15:38 2031.99-2035.03 | bias D1 +0 H4 +1 H1 +1 at the end of the window (the trend allowed your way 0% of it)
- #195 2024-02-05 00:01 short half: no M5 break of structure. your ranges: M1 range pause #194 02-04 23:45 2037.83-2040.04 | bias D1 +0 H4 +1 H1 +1 at the end of the window (the trend allowed your way 0% of it)

**no_detection:m1_bos** (8), e.g.:

- #90 2024-01-19 14:28 short limit: swept, waiting for the break. bot POI 15min OB 2023.06-2025.49; bot M1 swing low 2022.22 high 2020.62, break level 2020.62 | yours: M1 structure BOS #89 01-19 14:23 2031.72 | bias D1 +0 H4 -1 H1 -1 at the end of the window (the trend allowed your way 0% of it)
- #117 2024-01-24 14:18 short limit: swept, waiting for the break. bot POI 15min OB 2024.12-2025.58; bot M1 swing low 2025.56 high 2023.54, break level 2023.54 | yours: M1 structure BOS #101 01-24 09:01 2029.79; M1 structure BOS #114 01-24 12:16 2031.50 | bias D1 +0 H4 -1 H1 +1 at the end of the window (the trend allowed your way 0% of it)
- #371 2024-02-28 11:24 long limit: swept, waiting for the break. bot POI 15min FVG 2025.86-2026.67; bot M1 swing low 2026.76 high 2027.80, break level 2027.80 | yours: M1 structure BOS #370 02-28 10:45 2027.53; M1 structure BOS #375 02-28 12:14 2029.17; M1 structure BOS #378 02-28 12:36 2029.09 | bias D1 -1 H4 +1 H1 -1 at the end of the window (the trend allowed your way 0% of it)

## Extra trades: why you wouldn't take the bot's

| category | trades | share |
|---|---|---|
| no_htf_poi | 202 | 55% |
| against_htf | 73 | 20% |
| inside_range | 26 | 7% |
| chop_day | 19 | 5% |
| weak_break | 15 | 4% |
| other | 11 | 3% |
| no_sweep | 9 | 2% |
| duplicate | 9 | 2% |

A trade can have several reasons; the category is the first in the order of `tools/explain_extra.py`. All reasons, counted separately:

| category | trades | share |
|---|---|---|
| no_htf_poi | 268 | 74% |
| chop_day | 209 | 57% |
| duplicate | 137 | 38% |
| weak_break | 131 | 36% |
| inside_range | 115 | 32% |
| against_htf | 73 | 20% |
| no_sweep | 33 | 9% |

