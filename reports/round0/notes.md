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
