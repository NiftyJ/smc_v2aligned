# Round 4: the bot against your trades (development period 2024-01-05 -> 2024-07-31)

## Round 4: no change kept

The bot is the round-3 bot, so the numbers below are round 3's. Running the round again gave the same
result.

**Categories (round 3).** Extra: `no_htf_poi` 202, `against_htf` 73. Missed: `other` 21,
`bias_d1` 16, `m5_bos` 12 and `m5_pause` 6 (your momentum trades), `m1_bos` 8.

**What the why-not trace shows (dev):**

1. **Missed `other` (21).** Almost all of these are buys in the March–April rally. In every one of your
   windows the bot bought earlier and higher than you, usually 2–6 times. Its stops were $0.3–1.5 and were
   hit within minutes. You entered hours later, deeper, with a stop 2–3 times wider. For example, around
   #599 and #603 the bot's entries were at 2348–2357, and yours at 2325–2329. When your order filled, the bot had **no POI armed** for 74–90% of the
   candles in your window: its POIs had been used by those early tries, or broken.
2. **Your stops.** Your sniper stops sit around the low of the last 1–2 hours. On average they are about
   1R under the low of the last 15 minutes. So they cover the whole pullback, not the M1 sweep. The
   bot's stop is under the M1 sweep's low (median 1.1 M1 ATR, against your 2.65).
3. **Missed `bias_d1` (16).** Only 4 of these are the data warm-up: the prices start 2024-01-02, so the
   D1 trend is unknown until 2024-02-13. The other 12 are real disagreements:
   - 9 buys between 02-16 and 03-01. The bot's D1 trend still read down then (lower highs and lows since
     late December), and only turned up on the breakout of 03-01.
   - 3 sells at tops (#730, #817, #831) while the D1 read up.

   You traded the turn before the daily structure confirmed it. A weekly trend might be what you
   follow, but it can't be built from prices that start in January 2024.
4. **Extra `against_htf` (73).** These come from just 6 weeks. 49 are in 2 weeks (from 05-20 and from
   07-15) where you sold the top while the bot kept buying, 34 times in the week of 07-15.
5. **Momentum (0 of your 23).** The bot's pause detector can't see your pauses:
   - Your M1 pause ranges follow a leg of about 11 M1 ATRs (median). They give back about half of it
     (median 0.52; a quarter give back more than 0.71).
   - The candle you click is an M1 break of structure your way in only 3 of 23 trades.
   - With the detector at its loosest (the impulse within 60 candles, up to 75% given back), it is on
     64% of the time and still on at only 7 of your 23 decisions.

   This can't be fixed by changing a number. It needs your definition of the trigger (see the final report).
6. Your M1 break-of-structure marks don't show one swing size. About half break swings with 5 or more
   candles on each side; the other half are not at a candle's extreme. So no swing-size rule was tried.

**Attempts (development period only):**

| attempt | rule | recall | precision | bot trades | result |
|---|---|---|---|---|---|
| round 3 | — | 8.2% | 2.14% | 373 | |
| a | H4 order blocks and FVGs are POIs too (M15, M30, H1, H4) | 8.2% | 2.04% | 392 | rejected: precision fell and recall didn't move. The bot still fires at the first sweep + break after the touch and is stopped before your deeper entry. |
| b | the stop goes under the lowest point since price reached the POI | 6.2% | 1.95% | 307 | rejected: both fell. The two matches that were re-tries after a stop-out (#496, #612) are gone. |
| c | the stop goes under the POI's higher low | 6.2% | 2.14% | 280 | rejected: recall fell, precision unchanged |
| d | the M1 break is a close above the high since the sweep only, without the older swing high | 7.2% | 1.48% | 474 | rejected: both fell |

**Finding (not kept, as the brief asks):** attempts b and c make the bot much more profitable on dev, but
they match you less:

| | total R | win rate | max drawdown |
|---|---|---|---|
| round 3 | +203R | 10.3% | 66R |
| b | +308.6R | 14.8% | 52R |
| c | +317.6R | 15.6% | 46R |

These are from the quick dev runs, which stop at 2024-08-02. The full run gives round 3 +210.6R.

Two rounds in a row without a kept change ends the work. So round 5 is the last try before the final
check.

Rejected code: `reports/rejected/round4*.diff`.

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

