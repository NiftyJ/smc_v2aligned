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
