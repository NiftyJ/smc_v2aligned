# Final report: smc_v2 against your labels

Working copy: `smc_v2_align/` (a copy; the live bot was not touched). The baseline is the first
commit, tagged `baseline`. Every change is listed in `CHANGES.md`, and each round has a report in
`reports/round<N>/`.

**In short:**
- After 8 rounds and 5 kept changes, the bot matches 8 of your 97 dev trades (up from 3), and 8 of its
  207 trades are yours (up from 3 of 232).
- The gain didn't hold on the holdout (recall 6.1% → 4.1%), so it was fitted to the dev trades.
- What did hold: the bot is more selective, with about half as many trades, closer to your rate.
- Before and after the changes, the bot is about break-even on the holdout before costs, and loses
  after a normal spread.
- The rest of the gap is in things the bot can't see in prices alone. See the 5 differences below
  and what each needs from you.

## The final check

This was run once, at the end, with the final code. Round 8 is the round-6 bot.

    python tools/final_check.py --final 8      -> reports/final/final_check.md (+ the trades per column as CSV)

| | baseline: dev | final: dev | baseline: holdout | final: holdout | final: late (recall only) |
|---|---|---|---|---|---|
| recall | 3.1% (3/97) | 8.2% (8/97) | 6.1% (3/49) | 4.1% (2/49) | 4.4% (3/68) |
| precision | 1.3% (3/232) | 3.9% (8/207) | 1.8% (3/166) | 2.1% (2/94) | — |
| bot trades / week (mine) | 7.8 (3.3) | 6.9 (3.3) | 11.7 (3.5) | 6.6 (3.5) | — |
| win rate, mean R, total R, max DD (limits on = the same run) | 10.5%, +0.64R, +147.7R, 52.0R | 9.8%, +0.47R, +95.5R, 49.0R | 7.4%, +0.03R, +4.8R, 35.0R | 7.6%, +0.04R, +3.4R, 28.0R | — |

The periods are dev 2024-01-05 → 2024-07-31, holdout 2024-08-01 → 2024-11-08, and late
2024-11-09 → 2025-03-12. R is before costs.

**Plainly: the changes were fitted to the development trades.**

- On dev, recall went from 3.1% to 8.2% and precision from 1.3% to 3.9%.
- On the holdout, recall fell from 6.1% to 4.1%: the bot matched 2 of your 49 trades instead of 3.
  Precision rose only from 1.8% to 2.1%, and that is because the bot trades half as often (11.7 → 6.6
  a week), not because it picks your trades.
- The late period's recall, 4.4%, is about half the dev figure, in line with the holdout.
- At these levels one trade moves recall by 1 to 2 points, so the dev gain rests on 5 trades.

What did carry over: the bot is more selective out of sample too. It trades about half as often, closer
to your rate (6.6 against your 3.5 a week on the holdout), with a smaller drawdown (35R → 28R) and
the same result.

**Profit doesn't carry over either, before or after the changes.**
- On the holdout, the baseline bot made +4.8R from 163 fills. This is the code copied from the live
  folder. The final bot made +3.4R from 92. Both are about break-even, and that is before costs: the
  backtest has `COST = 0`.
- The bot's stops are small: a median of $0.89 (baseline) and $1.04 (final) on the holdout, against
  your $1.83 on dev.
- A spread of $0.20–0.30 a trade would cost about 43–65R (baseline) or 21–32R (final) over the
  holdout. Both would end clearly negative.
- Please check this with your broker's real spread before trusting the live bot's results. Set `COST`
  in `Settings` in `strategy.py`, then run `python tools/run_backtest.py --round 9`.
- On dev, the same costs take about 77–116R off the baseline's +147.7R, and 48–72R off the final's
  +95.5R.

## The 5 biggest differences still there, and what would fix each

1. **Your momentum trades.** These are 23 of your 97 dev trades, and the bot catches 1 of them (#549,
   through a sniper re-try).
   - Your momentum trades start from an M1 range (pause, staircase or wyckoff). The range follows a leg
     of about 11 M1 ATRs (median) and gives back about half of it.
   - You click inside the range. The clicked candle is an M1 break of structure your way in only 3 of
     23; 14 of 23 have one in the 15 minutes before.
   - The bot's pause detector needs a spike of at least 6 ATRs within 12 candles, and at most half of
     it given back. It is on at 1 of your 23 decisions. At its loosest it is on 64% of the time and
     still sees only 7.
   - **Needed:** what makes you click. For about 20 momentum trades, mark the trigger candle with its
     reason (for example, "the range low was swept and this candle closed back inside", or "first
     higher low in the range"). With that, the trigger can be coded and checked.
2. **When and how deep you enter.** These are 16 missed trades in `other`, plus most of the bot's
   re-tries.
   - The bot buys the first sweep and break after price touches its POI. That entry is early and high,
     with a stop under the M1 sweep (median 1.1 M1 ATR). It is stopped within minutes and tries again,
     up to 3 times.
   - You buy hours later and deeper, with a stop under the whole pullback (median 2.65 ATR, around the
     low of the last 1–2 hours).
   - Half of the bot's matches are those re-tries: it reaches your entry only by being stopped out first.
   - Wider structural stops made the bot far more profitable but lost those matches (round 4,
     findings).
   - **Needed:**
     - Which level you wait to see taken before you enter (the session low, the previous day's low, an
       M15 swing low?). A "liquidity taken" mark linked to each trade would let the sweep target be
       coded.
     - Your stop rule in words, so the stop and the re-try logic can change together.
     - For limit orders, the time you placed the order. Only 35% of your limits filled in the candle
       you clicked, so the clicked candle is not always the order time.
3. **Direction at turns.** These are 13 missed trades blocked by the D1 trend, plus 34 extra trades
   against the way you traded that week.
   - You trade the turn before the daily structure confirms it:
     - 9 buys between 2024-02-16 and 03-01, while the bot's D1 trend still read down;
     - sells at the July top while it read up.
   - The bot's extras against your direction cluster in a few reversal weeks.
   - **Needed:** what tells you the direction at a turn. If it is the weekly trend, that needs about a
     year of price history before 2024, and the price file starts on 2024-01-02.
   - **Please also send earlier M1 prices** (same Dukascopy source, from 2023-10-01 or earlier). The
     bot's D1 trend can't be known until 2024-02-13, so the bot could not trade at all for the first
     6 weeks of the development period, and 4 of your trades fall there. I didn't download other data
     because the brief says the comparison is only valid on the same prices.
4. **Which zone is the POI.** 20 of your trades had no bot POI armed, and 112 of the bot's 199 extra
   trades are at places where you had no zone marked.
   - Your POIs are mostly H1/H4 FVGs, often several days old, plus some D1 order blocks and M5
     structure, chosen by context.
   - The bot arms the first touch of the newest big FVG on M15/M30/H1, for one day.
   - Your entries are often not inside the zone you marked: 21% are inside, 57% above it.
   - **Needed:** how you pick one zone among several. Marking the zones you looked at and skipped
     (a "seen, not traded" mark) would show what you reject. That is what the bot most needs to learn
     here.
5. **Frequency.**
   - After the changes the bot trades 6.9 times a week on dev, against your 3.3.
   - 97 of its 199 extra trades (49%) fall on days you took no trade at all.
   - You often take no trade for days. Nothing in the price data tells the bot when you are not
     looking.
   - **Needed:** the review windows already show when you looked at the chart. A label for days you
     reviewed and chose not to trade, with the reason (news, chop, no clear trend), would let a rule be
     found.

## Possible bugs (not changed unless noted)

- **`smcml/data.py` `load_mt5_csv`** can't read the Dukascopy file. The file mixes `2024-01-02 05:01:00`
  and `2025-11-17T14:02:00Z` time formats, and repeats some candles where two downloads overlap
  (Nov 2025). `strategy.py --data ...` uses this loader. The tools use their own loader
  (`tools/common.py` `load_prices`).
- **`poi.py:146`** uses `np.datetime64("NaT")` without a unit. NumPy warns that this will become an
  error ("The 'generic' unit for NumPy timedelta is deprecated").
- **A setup the trend forbids still uses up its POI.** `_sniper` applies "one setup per touch" before
  the trend check. A sweep and break against the trend kills that POI for the rest of its touch.
  Changing the order made no difference to matching (round 3, attempt e), but it is probably not
  intended.
- **Tiny stops and no costs.**
  - `MIN_RISK_ATR = 0.25` M1 ATR allows stops of $0.13 at night, below a normal XAUUSD spread.
  - `COST` defaults to 0, so all R figures here are before costs.
  - The bot's tight-stop trades would suffer most from costs. Run `strategy.py --cost` with your
    broker's spread before trusting the profit numbers.
- **The D1 trend needs about 6 weeks of daily candles** (10-candle swings on each side, and two swing
  highs and lows) before it is known. If the live script loads less history than that, the bot can't
  trade at all. Please check how many days `live_mt5.py` loads.
- **Live and backtest differ a little.**
  - `live_orders(recent="7D")` builds the sniper's POIs from the last 7 days only. A POI older than
    that is never armed live, though the backtest can arm it.
  - The ATR used by the FVG size rule (round 6) is computed on those 7 days, so it is less settled for
    gaps from the first day or two of the window.
  - Both are small, because a newer FVG of the same kind usually replaces an older one.
- **`Settings.MAX_BARS_WAIT_FILL = 40` is never used by the strategy.** A sniper limit is not
  cancelled after 40 candles. It waits until the POI's one-day window ends, or until a close beyond
  the stop's range or the higher low. `show_sweep.py`, however, draws and describes a 40-candle cancel.
  Either the rule is missing or the chart is wrong. I left both as they are, because changing it would
  change the bot's trades.
- **`backtest()` returns filled trades only.** Sniper orders that were cancelled, or still waiting at
  the end, appear only through the journal. `tools/common.py` `bot_trades` adds them.
- **Cosmetic:** `show_trades.py` and `show_sweep.py` still say "D1 and H4 bias". The trend is now D1,
  H4 and H1.
- **Fixed on the way:**
  - Round 1: the live order name of an FVG POI could collide with an order block known at the same
    candle.
  - Round 3: the minimum-risk check in `SweepMachine` used the order block's high while `place()` used
    its open.
