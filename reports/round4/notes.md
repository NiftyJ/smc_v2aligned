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
