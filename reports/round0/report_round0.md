# Round 0: the bot against your trades (development period 2024-01-05 -> 2024-07-31)

## What the bot does differently from you (baseline, development period)

The bot matched 3 of your 97 trades, and 3 of its 232 trades match one of yours. In trading terms:

1. **Direction.** The bot only trades when its D1 and H4 trends (swing pivots on closed candles) both point
   the trade's way. Its D1 trend stays undecided until 13 Feb 2024 because the price file starts on
   2 Jan 2024 and it needs about 6 weeks of daily candles. So none of your January and early-February
   trades could be taken. After that, D1 and H4 together agree with your direction on half of your trades
   (D1 alone 56%, H4 alone 71%). 12 of your shorts came while the bot read both D1 and H4 as up. When the
   trend disagrees at the moment of the M1 break, the bot also gives up that POI for the rest of the touch.
2. **Where it trades from.** The bot's POI is the first touch of any M15, M30 or H1 order block. Your POIs
   are mostly fair value gaps: 55 of the 70 zones you marked on M15 or higher are FVGs, usually on H4 or H1,
   refined on M30 or M15. 75% of the bot's extra trades are not at any POI you marked on M15 or higher.
3. **One setup per touch.** The bot takes one M1 setup per POI touch, and tries again only after a
   stop-out. You often take 2 to 8 entries in the same setup at successive M1 breaks.
4. **The M1 trigger.** The bot needs a sweep of the last M1 swing low, then a close above the "real" swing
   high within 30 candles. In 17 of your trades it saw the sweep but never got that close in your window.
5. **Entry and stop.** The bot's limit sits at the open of the M1 order-block candle, with the stop under
   the sweep's low. Your long entries sit at the top of the M1 order block or FVG you marked (median
   position 1.00 in the zone; shorts at the bottom), with the stop at or just beyond its far edge (risk is
   about 1.1 times the zone's height).
6. **Momentum.** Your momentum trades are M1 pause ranges broken by an M1 candle. The close of the candle
   you clicked is the trigger (65 of 65 half orders), the entry is halfway back to the stop, and the stop
   is at the range's extreme. The bot only looks at M5 pause ranges broken by an M5 candle. It matched 0
   of your 23 momentum trades.
7. **How often.** The bot trades 7.8 times a week against your 3.3. 54% of its extra trades fall on days
   when you didn't trade and it took 3 or more trades or lost twice.
8. **Tiny stops at night.** The bot's minimum stop is 0.25 times the M1 ATR, which at night can be
   $0.13. Your smallest sniper stop is $0.18, and 9 in 10 of yours are wider than $0.58.
9. **Your limit orders.** For only 35% of your filled limits did the entry fill in the candle you
   clicked. For the rest, price reached the entry later: 29% within 15 minutes, 16% within 16 to
   60 minutes, 16% within 1 to 8 hours, and 5% after more than 8 hours. For those, the click looks like
   the time you placed the order. The brief's matching window (up to 8 hours before your fill candle) is
   kept as written. The `timing` category shows the cases this affects.

The bot's +147.7R on this period comes from trades you would not take (+150.7R on the extra trades,
−2.0R on the 3 matched).

## The numbers

| dev | value |
|---|---|
| my trades | 97 (70 filled) |
| bot trades | 232 (229 filled) |
| **recall** = both / my trades | **3.1%** (3 / 97) |
| **precision** = both / bot trades | **1.3%** (3 / 232) |
| duplicates | 1 |
| extra | 228 |
| placement differences | 2 |
| bot trades per week, against mine | 7.8 / 3.3 |
| the bot's results (limits on = the same run) | 229 filled, win rate 10.5%, mean +0.64R, total +147.7R, max DD 52.0R |
| the bot's results on **both** trades only | 2 filled, win rate 0.0%, mean -1.00R, total -2.0R, max DD 2.0R |
| the bot's results on **extra** trades only | 226 filled, win rate 10.6%, mean +0.67R, total +150.7R, max DD 52.0R |
| the bot's results on duplicates only | 1 filled, win rate 0.0%, mean -1.00R, total -1.0R, max DD 1.0R |
| recall by your order | half 0/23 (0%), limit 3/71 (4%), market 0/3 (0%) |
| recall by your subtype | momentum 0/23 (0%), sniper 3/74 (4%) |
| matched / (matched + extra) by bot rule | momentum 2/40, sniper 1/191 |

Results are in R with no costs (the bot's default `COST = 0`). Your own R is not compared: your targets were drawn afterwards.

## Missed trades: why the bot didn't take yours

| category | trades | share |
|---|---|---|
| no_detection:m1_bos | 17 | 18% |
| other | 17 | 18% |
| blocked_by_filter:one_setup_per_poi | 14 | 15% |
| no_detection:m5_bos | 14 | 15% |
| no_detection:htf_poi | 10 | 11% |
| blocked_by_filter:bias_d1 | 7 | 7% |
| no_detection:m5_pause | 6 | 6% |
| wrong_direction | 3 | 3% |
| timing | 3 | 3% |
| blocked_by_filter:bias_h4 | 2 | 2% |
| blocked_by_filter:pending_order | 1 | 1% |

Each missed trade, its category, the condition that failed and the values: `why_not_dev.csv`.

**no_detection:m1_bos** (17), e.g.:

- #49 2024-01-09 15:33 short limit: swept, waiting for the break. bot POI 15min 2034.94-2036.27; bot M1 swing low 2035.55 high 2031.50, break level 2031.50 | yours: none | bias D1 +0 H4 +0 at the end of the window (0% of it agreeing)
- #70 2024-01-16 15:44 short limit: swept, waiting for the break. bot POI 15min 2040.36-2042.35; bot M1 swing low 2033.62 high 2031.10, break level 2031.10 | yours: M1 structure BOS #77 01-17 02:40 2026.82 | bias D1 +0 H4 -1 at the end of the window (0% of it agreeing)
- #90 2024-01-19 14:28 short limit: swept, waiting for the break. bot POI 15min 2023.06-2025.49; bot M1 swing low 2022.22 high 2020.62, break level 2020.62 | yours: M1 structure BOS #89 01-19 14:23 2031.72 | bias D1 +0 H4 -1 at the end of the window (0% of it agreeing)

**other** (17), e.g.:

- #437 2024-03-14 17:50 long limit: same idea, the bot's limit 0.5-1.5R from yours. bot #42 long sniper | 1h OB | first range decided 03-14 13:21 entry 2162.24 (0.70R from yours, -269 min)
- #484 2024-03-25 05:38 long limit: the bot took the same direction in your window at another level. bot #46 long momentum | 5min pause decided 03-25 02:40 entry 2175.80 (5.73R from yours, -178 min)
- #488 2024-03-25 08:32 long limit: the bot took the same direction in your window at another level. bot #46 long momentum | 5min pause decided 03-25 02:40 entry 2175.80 (8.29R from yours, -352 min)

**blocked_by_filter:one_setup_per_poi** (14), e.g.:

- #257 2024-01-05 04:25 short limit: no POI armed (this POI already had its setup). bias D1 +0 H4 +0 at the end of the window (0% of it agreeing)
- #18 2024-01-05 16:17 short market: no POI armed (this POI already had its setup). bias D1 +0 H4 +0 at the end of the window (0% of it agreeing)
- #371 2024-02-28 11:24 long limit: no POI armed (this POI already had its setup). bias D1 -1 H4 +1 at the end of the window (0% of it agreeing)

**no_detection:m5_bos** (14), e.g.:

- #144 2024-01-29 16:25 long half: no M5 break of structure. your ranges: H4 range staircase #320 01-29 00:00 2019.19-2055.91; M1 range pause #142 01-29 15:40 2023.69-2026.89; M1 range pause #146 01-29 16:20 2024.27-2026.11 | bias D1 +0 H4 -1 at the end of the window (0% of it agreeing)
- #174 2024-02-02 15:59 long half: no M5 break of structure. your ranges: M5 range staircase #180 02-02 15:35 2032.49-2037.96; M1 range pause #175 02-02 15:38 2031.99-2035.03 | bias D1 +0 H4 +1 at the end of the window (0% of it agreeing)
- #195 2024-02-05 00:01 short half: no M5 break of structure. your ranges: M1 range pause #194 02-04 23:45 2037.83-2040.04 | bias D1 +0 H4 +1 at the end of the window (0% of it agreeing)

## Extra trades: why you wouldn't take the bot's

| category | trades | share |
|---|---|---|
| no_htf_poi | 123 | 54% |
| against_htf | 54 | 24% |
| no_sweep | 12 | 5% |
| inside_range | 12 | 5% |
| other | 10 | 4% |
| weak_break | 7 | 3% |
| chop_day | 7 | 3% |
| duplicate | 3 | 1% |

A trade can have several reasons; the category is the first in the order of `tools/explain_extra.py`. All reasons, counted separately:

| category | trades | share |
|---|---|---|
| no_htf_poi | 171 | 75% |
| chop_day | 122 | 54% |
| duplicate | 84 | 37% |
| weak_break | 78 | 34% |
| inside_range | 77 | 34% |
| against_htf | 54 | 24% |
| no_sweep | 37 | 16% |

