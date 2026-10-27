"""
The final check (the brief, section 6), run once at the end: the baseline bot and the final bot on the
development period, the holdout and the late period.

    python tools/final_check.py --final 6          -> reports/final/final_check.md, plus the matched /
                                                      missed / extra trades per column as CSV

It reads reports/round0/bot_trades_round0.csv and reports/round<final>/bot_trades_round<final>.csv
(tools/round.py runs the bot over the whole backtest, 2024-01-01 -> 2025-03-31) and matches them with
the same rules as every round (compare_labels.compare). The late period is recall only.
"""
import argparse
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import PERIODS, REPORTS, load_labels  # noqa: E402
import compare_labels as cl  # noqa: E402

COLUMNS = [("baseline", "dev"), ("final", "dev"), ("baseline", "holdout"), ("final", "holdout"), ("final", "late")]
RECALL_ONLY = {"late"}


def cells(n, period):
    """The rows of the brief's table for one column."""
    r = n["res_all"]
    full = period not in RECALL_ONLY
    res = (f"{r['win_rate']:.1%}, {r['mean_R']:+.2f}R, {r['total_R']:+.1f}R, {r['max_dd_R']:.1f}R"
           if full and r["filled"] else "—")
    return {
        "recall": f"{n['recall']:.1%} ({n['both']}/{n['my_trades']})",
        "precision": f"{n['precision']:.1%} ({n['both_bot_in_window']}/{n['bot_trades']})" if full else "—",
        "bot trades / week (mine)": f"{n['bot_per_week']:.1f} ({n['my_per_week']:.1f})" if full else "—",
        "win rate, mean R, total R, max DD (limits on = the same run)": res,
    }


def run(final, baseline=0):
    out_dir = os.path.join(REPORTS, "final")
    os.makedirs(out_dir, exist_ok=True)
    _, mine, reviewed = load_labels()
    bots = {"baseline": cl.load_bot(os.path.join(REPORTS, f"round{baseline}", f"bot_trades_round{baseline}.csv")),
            "final": cl.load_bot(os.path.join(REPORTS, f"round{final}", f"bot_trades_round{final}.csv"))}
    table, nums = {}, {}
    for who, period in COLUMNS:
        num, matched, missed, extra, _ = cl.compare(mine, bots[who], period, reviewed)
        nums[who, period] = num
        table[f"{who}: {period}"] = cells(num, period)
        for name, t in (("matched", matched), ("missed", missed), ("extra", extra)):
            t.to_csv(os.path.join(out_dir, f"{who}_{name}_{period}.csv"), index=False)
    rows = list(next(iter(table.values())))
    lines = ["| | " + " | ".join(table) + " |", "|---" * (len(table) + 1) + "|"]
    lines += [f"| {k} | " + " | ".join(table[c][k] for c in table) + " |" for k in rows]
    span = ", ".join(f"{p} {a:%Y-%m-%d} -> {b - pd.Timedelta('1D'):%Y-%m-%d}" for p, (a, b) in PERIODS.items())
    md = (f"# Final check: baseline (round {baseline}) against final (round {final})\n\n{span}. "
          "Results are in R with no costs; the late period is recall only.\n\n" + "\n".join(lines) + "\n")
    with open(os.path.join(out_dir, "final_check.md"), "w", encoding="utf-8") as fh:
        fh.write(md)
    return md, nums


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--final", type=int, required=True, help="the final round")
    p.add_argument("--baseline", type=int, default=0)
    args = p.parse_args()
    md, _ = run(args.final, args.baseline)
    print(md)


if __name__ == "__main__":
    main()
