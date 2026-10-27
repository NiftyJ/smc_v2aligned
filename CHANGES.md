# Changes: aligning smc_v2 to your labels

This is a copy of the live bot's folder, `smc_v2_align/`. The live bot was not touched. The untouched
copy is the first commit, tagged `baseline`. Each kept change is one commit, and the commit message is
its trading rule.

All numbers are for the **development period** (2024-01-05 → 2024-07-31), the only period used to
choose changes. Recall is how many of your 97 trades the bot also took. Precision is how many of the
bot's trades are also yours. Results are in R with no costs (the bot's `COST = 0`). The holdout and late
periods are in `FINAL_REPORT.md`.

## Kept

| round | rule | recall | precision | bot trades/week (yours 3.3) |
|---|---|---|---|---|
| baseline | — | 3.1% | 1.3% | 7.8 |
| 1 | **An FVG is a POI too.** The sniper also trades the first touch of the latest M15/M30/H1 fair value gap of its direction. | 8.2% | 1.7% | 15.9 |
| 2 | **Trade only with the trend on all three.** D1, H4 and H1 must all point the trade's way (was D1 and H4). | 8.2% | 2.1% | 12.6 |
| 3 | **The sniper's limit sits at the top of the M1 order block** (its high; the low for shorts), where you put yours, not at its open. | 8.2% | 2.14% | 12.5 |
| 4 | no change kept | | | |
| 5 | **The sniper's POI is a fair value gap** on M15/M30/H1, as you mark yours. Order blocks no longer arm it on their own. | 8.2% | 2.90% | 9.3 |
| 6 | **An FVG is a POI only if its gap is at least half an ATR of its own timeframe**, like every FVG you mark (smallest 0.45, median 1.04 ATR). | 8.2% | 3.86% | 6.9 |
| 7 | no change kept | | | |
| 8 | no change kept. Stop: two rounds without a kept change, and the last round. | | | |

The final check (`FINAL_REPORT.md`) shows these gains did **not** hold on the holdout: recall went from
6.1% to 4.1%, and precision from 1.8% to 2.1% only because the bot trades less.

The bot's results on dev after each change:

| | baseline | 1 | 2 | 3 | 5 | 6 |
|---|---|---|---|---|---|---|
| total R | +147.7R | +238.5R | +226.2R | +210.6R | +190.6R | +95.5R |
| max drawdown | 52.0R | 64.8R | 66.0R | 66.0R | 51.0R | 49.0R |

### What each kept change touched

1. **FVG POIs** (round 1, commit `6697d48`).
   - `strategy.py`: FVGs are found by `poi.py`, and a newer FVG replaces the older one. An FVG is
     touched on the first trade into its near edge, and its far edge is the "higher low". Adds
     `Settings.POI_KINDS`.
   - `live_mt5.py`: an FVG POI's order gets its own name, so the "never send twice" check can't confuse
     it with an order block known at the same candle.
   - `tools/common.py` and `tools/why_not.py`: show OB or FVG.
   - `tests/test_strategy.py`: tries are counted per POI.
   - Effect: 5 more of your sniper trades matched. The bot traded twice as often.
2. **Trend on all three** (round 2, commit `d827ab8`).
   - `strategy.py`: `trend_of()`, `Settings.TREND_TFS` and `TREND_NEED`. Used by both the sniper and
     momentum orders, at the moment of the M1 or M5 break.
   - The tools and tests show and check the H1 trend.
   - Effect: removed 97 bot trades, a third of them against your direction that week. Kept all 8
     matches.
3. **Limit at the M1 order block's high** (round 3, commit `b54d811`).
   - `strategy.py`: `place()` and the docstring.
   - Effect: placement differences on matched trades 6 → 5. Mean entry gap to yours 0.24R → 0.18R.
4. **FVG POIs only** (round 5, commit `f587f6d`).
   - `strategy.py`: the `Settings.POI_KINDS` default and the docstring.
   - Effect: none of the bot's 121 dev trades from order-block POIs matched yours, and 36 of your 44
     M15+ zone marks are FVGs. Removed those trades and kept all 8 matches.
   - `POI_KINDS = ("ob", "fvg")` brings order blocks back.
5. **FVG size** (round 6, commit `f07a7d9`).
   - `strategy.py`: `Settings.FVG_MIN_ATR = 0.5` and the filter in `_sniper()`. The gap is measured
     against the ATR(14) of its own timeframe at its middle candle, so nothing comes from the future.
   - The threshold comes from your marks (smallest 0.45 ATR, median 1.04) and was fixed before the
     test.
   - **The bot's dev profit fell from +190.6R to +95.5R.** The small gaps it no longer trades were
     profitable for it, before costs. See the findings below.

`tools/` (round 0, commit `7740334`) adds the comparison tools and changes nothing in the bot's trades:

- `python tools/round.py --round N`: the backtest, the comparison, why-not and extra categories, charts
  and the report, for one round.
- `python tools/compare_labels.py --round N --periods dev holdout late`: the comparison only.
- `python tools/why_not.py --round N`: why the bot didn't take each of your missed trades. For any
  moment: `--at "2024-03-05 14:20" --dir long`.
- `python tools/run_backtest.py --round N`: the bot's trades only (`bot_trades_round<N>.csv`).
- `python tools/explain_extra.py --round N`: why you wouldn't have taken each extra bot trade.
- `tests/test_tools.py`: the comparison's matching rules and the trade export are tested; the export
  changes nothing in the backtest.

## Tried and rejected

Each was tried on dev only. The code is in `reports/rejected/*.diff` (settings-only attempts have no
diff).

| round | rule tried | recall | precision | why rejected |
|---|---|---|---|---|
| 1a | an M15/M30/H1 POI counts only inside an H1/H4 zone of its direction | 2.1% | 1.2% | both fell |
| 1b | POIs are H1/H4 order blocks only | 2.1% | 2.1% | recall −1.0 is more than precision +0.8 |
| 1d | FVG POIs, but on H1/H4 | 3.1% | 1.3% | no gain |
| 2a | 2 of D1/H4/H1 | 10.3% | 1.3% | 26/week, more against you (see findings) |
| 2b | H4 only | 10.3% | 1.3% | 27/week (see findings) |
| 2d | H4 and H1 | 9.3% | 1.6% | 19/week (see findings) |
| 3a | momentum on M1 (M1 pause, M1 break) | 8.2% | 1.8% | still 0 of your 23 momentum trades |
| 3b | the M1 break must leave an FVG | 7.2% | 1.9% | both fell |
| 3c | minimum stop 1 M1 ATR (was 0.25) | 4.1% | 1.6% | both fell |
| 3e | the trend checked before the POI is used up | 8.2% | 2.08% | 9 more trades, none a match |
| 4a | H4 order blocks and FVGs are POIs too | 8.2% | 2.04% | precision fell |
| 4b | stop under the lowest point since the POI touch | 6.2% | 1.95% | both fell (see findings) |
| 4c | stop under the POI's higher low | 6.2% | 2.14% | recall fell (see findings) |
| 4d | M1 break above the high since the sweep only | 7.2% | 1.48% | both fell |
| 5a | the sweep must take a low made at the POI | 4.1% | 1.22% | both fell |
| 7a | H4 FVGs (half an ATR or more) are POIs too | 8.2% | 3.6% | precision fell |
| 7b | 2 of D1/H4/H1 (again, with the round-6 POIs) | 9.3% | 2.4% | precision −1.4 is more than recall +1.0 |
| 8a | a POI stays armed until it breaks or is replaced (not one day after the touch) | 8.2% | 3.81% | no gain |

Looked at but not tried, because the data gave no rule to try:
- Premium/discount. The bot's matched trades sit in premium.
- M5/M15 structure your way. It doesn't separate your trades from the bot's.
- A break-of-structure FVG. Only 6 of your 27 FVG marks are one.
- The M1 swing size in your marks. They are mixed.
- A looser momentum pause detector. At its loosest it is on 64% of the time and still sees only 7 of
  your 23 momentum decisions.

## Findings: more money, less like you

The brief asks for these to be reported, not kept. All the profit figures are dev only and before
costs. The final check shows the bot's dev profit does not carry over to the holdout, with or without
the changes (`FINAL_REPORT.md`).

- **Wider stops (4b, 4c).** A stop under the whole pullback, or under the POI's higher low, earned
  +308.6R or +317.6R on dev against +203R, with a lower drawdown (52R or 46R against 66R). But 2 of
  the 8 matches were lost. Those matches were re-tries after the bot's tight stop was hit, which is how
  the bot reaches your later, deeper entries.
- **Looser trend (2a, 2b, 2d).** These matched 1 or 2 more of your trades, but the bot traded 19 to 27
  times a week and more often against your direction.
- **FVG size (round 6, kept).** It matches you better, but halves the bot's dev profit, before costs.
  Weigh it before deploying. `FVG_MIN_ATR = 0` turns it off.
