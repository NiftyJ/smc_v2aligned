"""
Runs the bot (strategy.backtest) on the Dukascopy M1 file and writes every order it placed:

    python tools/run_backtest.py --round 0                 -> reports/round0/bot_trades_round0.csv

One row per order, UTC: id, decided (close of the signal candle), dir, order (limit = sniper at the M1
order block, half = momentum limit halfway back to the stop), entry, stop, target, fill_time (blank if
it never filled), rule, filters_passed, outcome, R, then the details behind it.

Account-level limits: strategy.backtest() has none (no one-position rule, no daily / weekly loss limit,
no cooldown, no session filter), so the comparison run and the "limits on" run are the same run.
The live script's own limits (--max-loss, one fill per order) are not in the backtest either.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import REPORTS, RUN, bot_trades, load_prices  # noqa: E402
from strategy import Settings, report  # noqa: E402


def run(round_no, prices=None, out_dir=None, settings=None, quiet=False):
    t0 = time.time()
    df = load_prices(prices) if prices else load_prices()
    trades = bot_trades(df, settings or Settings())
    out_dir = out_dir or os.path.join(REPORTS, f"round{round_no}")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"bot_trades_round{round_no}.csv")
    trades.to_csv(path, index=False)
    if not quiet:
        print(f"{len(df):,} M1 candles {df.index[0]} -> {df.index[-1]} (UTC); "
              f"{len(trades)} orders, {trades['fill_time'].notna().sum()} filled; {time.time() - t0:.0f}s")
        print(f"saved {path}")
    return trades, path


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--round", type=int, required=True)
    p.add_argument("--prices", help=f"M1 file (default data/XAUUSD_1m.csv), run {RUN[0]:%Y-%m-%d} -> {RUN[1]:%Y-%m-%d}")
    args = p.parse_args()
    trades, _ = run(args.round, args.prices)
    filled = trades[trades["fill_time"].notna()].rename(columns={"fill_time": "filled"})
    print(report(filled.assign(placed=filled["decided"])) if len(filled) else "no fills")


if __name__ == "__main__":
    main()
