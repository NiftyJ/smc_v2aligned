# Round 2: the bot against your trades (development period 2024-01-05 -> 2024-07-31)

## Round 2: the trend

**Largest category (round 1):** extra `no_htf_poi`, 233 trades, again. Round 1 already changed what a POI
is. I checked one more idea for this category: requiring the M5/M15 structure to point the trade's way at
the entry. It doesn't separate your trades from the bot's: 73% of the bot's no_htf_poi extras are with the
M5 trend, against 59% of your sniper entries. You often enter at a pullback, when the lower timeframe
still points the other way. Most of the rest of this category is time when you had no setup at all. So
this round took the next category: extra `against_htf`, 107 trades the bot took against the direction
you traded that week. Your missed trades blocked by the trend (16) or taken the other way by the bot (8)
belong here too.

**What's behind it.** The bot's direction is "D1 and H4 trends both agree" (swing pivots, 10 candles each
side). On your 97 development trades, that agrees with your direction 51% of the time. Other choices on
the same detector: H4 alone 71%, H1 alone 71%, D1 alone 56%, 2 of D1/H4/H1 69%, all three 41% (or less).
Your direction often comes from a higher-timeframe zone and a structure shift (for example, the July
shorts from an H4 bearish FVG), which no trend rule here reads.

**Attempts (development period only):**

| attempt | trend rule | recall | precision | bot trades | extra against your direction that week |
|---|---|---|---|---|---|
| round 1 | D1 and H4 | 8.2% | 1.7% | 473 | 107 (23%) |
| a | 2 of D1 / H4 / H1 | 10.3% | 1.3% | 766 | 188 (25%) |
| b | H4 only | 10.3% | 1.3% | 794 | — |
| **c** | **D1, H4 and H1 all agree** | **8.2%** | **2.1%** | **376** | **75 (20%)** |
| d | H4 and H1 | 9.3% | 1.6% | 565 | 130 (23%) |

**Kept: c.** The trade's direction needs the D1, H4 and H1 trends all pointing its way. It keeps all 8
matched trades, removes 97 bot trades (a third of them against your direction that week, against 23% of
all extras), and is the only variant that reduces this round's category.

**A finding, not kept:** the looser rules (a, b, d) each match 1 or 2 more of your trades (#70, #767,
#376). They also pass the brief's rule on paper, since recall gains more points than precision loses.
But the bot then trades 19 to 27 times a week against your 3.3, and more often against your direction
(188 trades with a). That is the opposite of this round's aim, so none of them was kept. On a combined
score (both / (yours + the bot's − both)), c is best: 1.72%, against 1.42% (round 1), 1.17% (a) and
1.38% (d).

**Effect on dev:** recall 8.2% (unchanged), precision 1.7% → 2.1%, bot trades 15.9 → 12.6 a week.
Extra trades against your direction 107 → 75. The bot's results: +226.2R (was +238.5R), win rate
10.2% (was 9.4%), max drawdown 66.0R (was 64.8R).

The price file starts on 2 Jan 2024, so the D1 trend is unknown until 13 Feb. The bot can't trade before
then on any trend rule that uses D1. That is a data limit, not a rule (see the final report).

Files: `strategy.py` (`trend_of`, settings `TREND_TFS`, `TREND_NEED`), `tools/why_not.py` and
`tools/common.py` (the trend in the trace and in `filters_passed`), and `tests/test_strategy.py`.

## The numbers

| dev | value |
|---|---|
| my trades | 97 (70 filled) |
| bot trades | 376 (373 filled) |
| **recall** = both / my trades | **8.2%** (8 / 97) |
| **precision** = both / bot trades | **2.1%** (8 / 376) |
| duplicates | 1 |
| extra | 367 |
| placement differences | 6 |
| bot trades per week, against mine | 12.6 / 3.3 |
| the bot's results (limits on = the same run) | 373 filled, win rate 10.2%, mean +0.61R, total +226.2R, max DD 66.0R |
| the bot's results on **both** trades only | 7 filled, win rate 28.6%, mean +2.71R, total +19.0R, max DD 3.0R |
| the bot's results on **extra** trades only | 365 filled, win rate 9.9%, mean +0.57R, total +208.2R, max DD 64.0R |
| the bot's results on duplicates only | 1 filled, win rate 0.0%, mean -1.00R, total -1.0R, max DD 1.0R |
| recall by your order | half 0/23 (0%), limit 8/71 (11%), market 0/3 (0%) |
| recall by your subtype | momentum 0/23 (0%), sniper 8/74 (11%) |
| matched / (matched + extra) by bot rule | momentum 2/36, sniper 6/339 |

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

- #451 2024-03-21 23:59 long limit: the bot took the same direction in your window at another level. bot #58 long sniper | 1h FVG | first range decided 03-21 20:09 entry 2180.55 (1.91R from yours, -230 min)
- #494 2024-03-26 04:57 long limit: order placed. bias D1 +1 H4 +1 H1 +1 at the end of the window (the trend allowed your way 57% of it)
- #502 2024-03-26 15:46 long limit: the bot took the same direction in your window at another level. bot #63 long sniper | 1h FVG | first range decided 03-26 13:17 entry 2187.87 (6.60R from yours, -149 min)

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
| no_htf_poi | 206 | 56% |
| against_htf | 75 | 20% |
| inside_range | 25 | 7% |
| chop_day | 18 | 5% |
| weak_break | 13 | 4% |
| other | 11 | 3% |
| duplicate | 10 | 3% |
| no_sweep | 9 | 2% |

A trade can have several reasons; the category is the first in the order of `tools/explain_extra.py`. All reasons, counted separately:

| category | trades | share |
|---|---|---|
| no_htf_poi | 273 | 74% |
| chop_day | 212 | 58% |
| duplicate | 143 | 39% |
| weak_break | 130 | 35% |
| inside_range | 120 | 33% |
| against_htf | 75 | 20% |
| no_sweep | 33 | 9% |

