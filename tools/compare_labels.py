"""
Compares the bot's trades with yours (the brief, sections 2d and 3).

    python tools/compare_labels.py --round 0                        # the development period
    python tools/compare_labels.py --round 7 --periods dev holdout late   # the final check, once

Reads reports/round<N>/bot_trades_round<N>.csv (tools/run_backtest.py) and your labels. Writes, per
period, into reports/round<N>/: matched_<p>.csv, missed_<p>.csv, extra_<p>.csv, duplicates_<p>.csv,
numbers_<p>.md, and sanity.md (the time-zone check).

MATCHING (fixed before any result was looked at; not tuned):
  * same direction, and
  * your market / half trade: the bot's `decided` within +-15 min of your decision (the close of the
    candle you clicked: start + one tf candle);
  * your limit trade: the bot's entry within 0.5 x your risk (|entry - stop|) of your entry, and either
    its `decided` between 8 h before your fill candle and the end of that candle, or its fill within
    +-15 min of your fill candle.
  * Each of your trades gets at most one bot trade and each bot trade at most one of yours: the pairs
    are taken nearest first (market / half: by time, |dt| / 15 min; limit: by entry, |d entry| / 0.5R).
  * A bot trade that fits one of your trades but lost to a nearer one is a DUPLICATE (same idea twice).
  * EXTRA: a bot trade decided inside the period and the reviewed span (2024-01-05 08:05 ->
    2024-11-08) that fits none of yours.
  * PLACEMENT difference (matched pairs): the bot's stop more than 0.5R from yours, or its entry more
    than 0.25R from yours (R = your risk).
Your trades count in a period by the candle you clicked (`start`), the bot's by `decided`.
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import PERIODS, REPORTS, load_labels, load_prices, results  # noqa: E402

TOL_T = pd.Timedelta("15min")
LIMIT_BEFORE = pd.Timedelta("8h")
ENTRY_TOL = 0.5          # x your risk, limit trades
PLACE_STOP, PLACE_ENTRY = 0.5, 0.25


# ----------------------------------------------------------------------------- 2d: time zone / data check
def sanity(df, mine, shift=pd.Timedelta(0)):
    """Is the price file on the labels' clock? For each trade, the M1 candles of the candle you clicked
    (start .. start + tf, moved by `shift`): entry inside their high-low (the brief's check), the trigger
    close of a half order (`level`) = their last close, a limit's fill side reached in them, and how many
    minutes after them a limit's entry was first reached."""
    lo, hi, cl = df["low"].to_numpy(), df["high"].to_numpy(), df["close"].to_numpy()
    idx = df.index
    rows = []
    for r in mine.itertuples():
        a = idx.searchsorted(r.start + shift, side="left")
        b = idx.searchsorted(r.start + shift + r.tf_td, side="left")
        if b <= a:
            rows.append(dict(id=r.id, order=r.order, outcome=r.outcome, data=False))
            continue
        l_, h_ = lo[a:b].min(), hi[a:b].max()
        side = (lo[a:a + 3000] <= r.entry + 1e-9) if r.d == 1 else (hi[a:a + 3000] >= r.entry - 1e-9)
        first = np.flatnonzero(side)
        rows.append(dict(id=r.id, order=r.order, outcome=r.outcome, data=True,
                         entry_in=bool(l_ - 1e-6 <= r.entry <= h_ + 1e-6),
                         level_is_close=bool(abs(r.level - cl[b - 1]) < 0.005) if pd.notna(r.level) else False,
                         half_rule=bool(abs(r.entry - (r.level + r.stop) / 2) < 0.005) if pd.notna(r.level) else False,
                         fill_side_in=bool(len(first) and first[0] < b - a),
                         first_fill_min=(idx[a + first[0]] - (r.start + shift)) / pd.Timedelta("1min") if len(first) else np.nan))
    return pd.DataFrame(rows)


def sanity_report(df, mine):
    s = sanity(df, mine)
    mh, half = s[s["order"].isin(["market", "half"])], s[s["order"] == "half"]
    market = s[s["order"] == "market"]
    lim = s[(s["order"] == "limit") & s["outcome"].isin(["target", "stop"])]
    checks = {"market + half: entry inside the clicked candle's M1 high-low (the brief's check)":
              (int(mh["entry_in"].sum()), len(mh)),
              "market: entry inside the clicked candle's M1 high-low": (int(market["entry_in"].sum()), len(market)),
              "half: the trigger close (`level`) = the close of the clicked candle (to 0.5 cent)":
              (int(half["level_is_close"].sum()), len(half)),
              "half: entry = (trigger close + stop) / 2, i.e. halfway back to the stop":
              (int(half["half_rule"].sum()), len(half)),
              "filled limits: the entry was reached in the clicked candle": (int(lim["fill_side_in"].sum()), len(lim)),
              "trades with M1 data at their candle": (int(s["data"].sum()), len(s))}
    scan = []
    for h in range(-3, 4):
        x = sanity(df, mine[mine["order"] == "half"], pd.Timedelta(hours=h))
        scan.append((h, x["level_is_close"].mean()))
    ff = lim["first_fill_min"]
    late = [("in the clicked candle", ff < 1), ("1-15 min after it", (ff >= 1) & (ff <= 15)),
            ("16-60 min after", (ff > 15) & (ff <= 60)), ("1-8 h after", (ff > 60) & (ff <= 480)),
            ("more than 8 h after", ff > 480)]
    md = ["# Sanity check (brief 2d): are the prices and the labels on the same clock?", "",
          "| check | passed | share |", "|---|---|---|"]
    md += [f"| {k} | {a} / {b} | {a / max(b, 1):.1%} |" for k, (a, b) in checks.items()]
    md += ["", "The trigger close of every half order, with the labels moved by whole hours:", "",
           "| shift | trigger close = clicked candle's close |", "|---|---|"]
    md += [f"| {h:+d} h | {v:.0%} |" for h, v in scan]
    md += ["", "Filled limit orders: when price first reached the entry, counted from the candle you clicked:", "",
           "| first reached | trades |", "|---|---|"]
    md += [f"| {k} | {int(m.sum())} ({m.mean():.0%}) |" for k, m in late]
    return checks, scan, late, s, "\n".join(md)


# ----------------------------------------------------------------------------- matching
def candidates(mine, bot):
    """Every (yours, bot) pair that fits the rules, with its distance (0 = same, 1 = at the tolerance)."""
    pairs = []
    for i, r in mine.iterrows():
        b = bot[bot["d"] == r.d]
        if b.empty:
            continue
        if r.order in ("market", "half"):
            dt = (b["decided"] - r.decision).abs()
            ok = dt <= TOL_T
            for j in b.index[ok]:
                pairs.append((i, j, dt[j] / TOL_T, dt[j] / pd.Timedelta("1min")))
        else:
            if not r.risk > 0:
                continue
            de = (b["entry"] - r.entry).abs()
            in_window = (b["decided"] >= r.fill_candle - LIMIT_BEFORE) & (b["decided"] <= r.fill_candle + r.tf_td)
            by_fill = b["fill_time"].notna() & ((b["fill_time"] - r.fill_candle).abs() <= TOL_T)
            ok = (de <= ENTRY_TOL * r.risk) & (in_window | by_fill)
            for j in b.index[ok]:
                pairs.append((i, j, de[j] / (ENTRY_TOL * r.risk), abs(b.at[j, "decided"] - r.fill_candle)
                              / pd.Timedelta("1min")))
    return pd.DataFrame(pairs, columns=["mine", "bot", "cost", "minutes"])


def match(mine, bot):
    """Nearest-first one-to-one assignment. Returns (pairs taken, duplicate bot rows -> the trade they fit)."""
    c = candidates(mine, bot)
    taken, used_m, used_b = [], set(), set()
    for r in c.sort_values(["cost", "minutes", "bot"], kind="stable").itertuples():
        if r.mine in used_m or r.bot in used_b:
            continue
        taken.append(r)
        used_m.add(r.mine)
        used_b.add(r.bot)
    taken = pd.DataFrame(taken, columns=["Index", "mine", "bot", "cost", "minutes"]).drop(columns="Index")
    dup = c[~c["bot"].isin(used_b)].drop_duplicates("bot")
    return taken, dup


def windows(period, reviewed):
    a, b = PERIODS[period]
    if period in ("dev", "holdout"):                      # extras only inside the reviewed span
        a, b = max(a, reviewed[0]), min(b, reviewed[1])
    return a, b


def compare(mine_all, bot_all, period, reviewed):
    a, b = PERIODS[period]
    mine = mine_all[mine_all["period"] == period].copy()
    ba, bb = windows(period, reviewed)
    near = bot_all[(bot_all["decided"] >= a - LIMIT_BEFORE - TOL_T) & (bot_all["decided"] < b + TOL_T)].copy()
    taken, dup = match(mine, near)
    in_win = (near["decided"] >= ba) & (near["decided"] < bb)
    bot = near[in_win]

    m = mine.loc[taken["mine"]].reset_index()
    k = near.loc[taken["bot"]].reset_index()
    matched = pd.concat([m.add_prefix("my_"), k.add_prefix("bot_")], axis=1)
    matched["minutes"] = taken["minutes"].to_numpy()
    matched["d_entry_R"] = (matched["bot_entry"] - matched["my_entry"]).abs() / matched["my_risk"]
    matched["d_stop_R"] = (matched["bot_stop"] - matched["my_stop"]).abs() / matched["my_risk"]
    matched["placement_diff"] = (matched["d_stop_R"] > PLACE_STOP) | (matched["d_entry_R"] > PLACE_ENTRY)
    missed = mine.drop(index=taken["mine"]).copy()
    # the nearest bot trade the same way (for the diagnosis; not a match)
    for i, r in missed.iterrows():
        same = near[near["d"] == r.d]
        when = r.decision if pd.notna(r.decision) else r.fill_candle
        if len(same):
            j = (same["decided"] - when).abs().idxmin()
            missed.loc[i, ["near_bot_id", "near_bot_decided", "near_bot_entry", "near_bot_rule"]] = \
                [same.at[j, "id"], same.at[j, "decided"], same.at[j, "entry"], same.at[j, "rule"]]
            missed.loc[i, "near_minutes"] = (same.at[j, "decided"] - when) / pd.Timedelta("1min")
            missed.loc[i, "near_d_entry_R"] = abs(same.at[j, "entry"] - r.entry) / r.risk
    dup_rows = near.loc[dup["bot"]].assign(duplicate_of=mine.loc[dup["mine"], "id"].to_numpy())
    dup_rows = dup_rows[dup_rows.index.isin(bot.index)]
    extra = bot.drop(index=[j for j in bot.index if j in set(taken["bot"]) or j in set(dup["bot"])])

    weeks = (bb - ba) / pd.Timedelta("7D")
    both_bot = bot[bot.index.isin(taken["bot"])]
    num = dict(period=period, my_trades=len(mine), my_filled=int(mine["outcome"].isin(["target", "stop"]).sum()),
               bot_trades=len(bot), bot_filled=int(bot["fill_time"].notna().sum()),
               both=len(taken), both_bot_in_window=len(both_bot),
               recall=len(taken) / max(len(mine), 1), precision=len(both_bot) / max(len(bot), 1),
               duplicates=len(dup_rows), extra=len(extra), placement=int(matched["placement_diff"].sum()),
               bot_per_week=len(bot) / weeks, my_per_week=len(mine) / weeks, weeks=weeks,
               res_all=results(bot), res_both=results(both_bot), res_extra=results(extra), res_dup=results(dup_rows))
    return num, matched, missed, extra, dup_rows


# ----------------------------------------------------------------------------- report
def fmt_res(r):
    if not r["filled"]:
        return "no fills"
    return (f"{r['filled']} filled, win rate {r['win_rate']:.1%}, mean {r['mean_R']:+.2f}R, "
            f"total {r['total_R']:+.1f}R, max DD {r['max_dd_R']:.1f}R")


def numbers_md(n, matched=None, missed=None, extra=None):
    lines = [f"| {n['period']} | value |", "|---|---|",
             f"| my trades | {n['my_trades']} ({n['my_filled']} filled) |",
             f"| bot trades | {n['bot_trades']} ({n['bot_filled']} filled) |",
             f"| **recall** = both / my trades | **{n['recall']:.1%}** ({n['both']} / {n['my_trades']}) |",
             f"| **precision** = both / bot trades | **{n['precision']:.1%}** ({n['both_bot_in_window']} / {n['bot_trades']}) |",
             f"| duplicates | {n['duplicates']} |",
             f"| extra | {n['extra']} |",
             f"| placement differences | {n['placement']} |",
             f"| bot trades per week, against mine | {n['bot_per_week']:.1f} / {n['my_per_week']:.1f} |",
             f"| the bot's results (limits on = the same run) | {fmt_res(n['res_all'])} |",
             f"| the bot's results on **both** trades only | {fmt_res(n['res_both'])} |",
             f"| the bot's results on **extra** trades only | {fmt_res(n['res_extra'])} |",
             f"| the bot's results on duplicates only | {fmt_res(n['res_dup'])} |"]
    if matched is not None and missed is not None:
        mine = pd.concat([matched.assign(hit=True).rename(columns=lambda c: c[3:] if c.startswith("my_") else c),
                          missed.assign(hit=False)], ignore_index=True)
        for col in ("order", "subtype"):
            parts = [f"{k} {g['hit'].sum()}/{len(g)} ({g['hit'].mean():.0%})" for k, g in mine.groupby(col)]
            lines.append(f"| recall by your {col} | {', '.join(parts)} |")
    if extra is not None and matched is not None and len(extra) + len(matched):
        bot = pd.concat([matched[["bot_rule"]].rename(columns={"bot_rule": "rule"}).assign(hit=True),
                         extra[["rule"]].assign(hit=False)])
        bot["kind"] = bot["rule"].str.split(" ").str[0]
        parts = [f"{k} {g['hit'].sum()}/{len(g)}" for k, g in bot.groupby("kind")]
        lines.append(f"| matched / (matched + extra) by bot rule | {', '.join(parts)} |")
    return "\n".join(lines)


def load_bot(path):
    bot = pd.read_csv(path, parse_dates=["decided", "fill_time", "first_placed", "exit_time"])
    bot["d"] = np.where(bot["dir"] == "long", 1, -1)
    return bot


def run(round_no, periods=("dev",), out_dir=None, df=None, quiet=False):
    out_dir = out_dir or os.path.join(REPORTS, f"round{round_no}")
    bot = load_bot(os.path.join(out_dir, f"bot_trades_round{round_no}.csv"))
    marks, mine, reviewed = load_labels()
    out = {}
    if round_no == 0 or not os.path.exists(os.path.join(out_dir, "sanity.md")):
        df = df if df is not None else load_prices()
        checks, scan, late, detail, md = sanity_report(df, mine)
        with open(os.path.join(out_dir, "sanity.md"), "w", encoding="utf-8") as fh:
            fh.write(md + "\n")
        detail.to_csv(os.path.join(out_dir, "sanity_detail.csv"), index=False)
        out["sanity"] = checks
        if not quiet:
            print(md)
    for p in periods:
        num, matched, missed, extra, dup = compare(mine, bot, p, reviewed)
        matched.to_csv(os.path.join(out_dir, f"matched_{p}.csv"), index=False)
        missed.to_csv(os.path.join(out_dir, f"missed_{p}.csv"), index=False)
        extra.to_csv(os.path.join(out_dir, f"extra_{p}.csv"), index=False)
        dup.to_csv(os.path.join(out_dir, f"duplicates_{p}.csv"), index=False)
        md = numbers_md(num, matched, missed, extra)
        with open(os.path.join(out_dir, f"numbers_{p}.md"), "w", encoding="utf-8") as fh:
            fh.write(md + "\n")
        out[p] = dict(num=num, matched=matched, missed=missed, extra=extra, dup=dup, md=md)
        if not quiet:
            print(md)
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--round", type=int, required=True)
    p.add_argument("--periods", nargs="+", default=["dev"], choices=list(PERIODS))
    args = p.parse_args()
    run(args.round, args.periods)


if __name__ == "__main__":
    main()
