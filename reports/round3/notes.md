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
