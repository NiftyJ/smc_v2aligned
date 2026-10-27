"""
EXTRA trades (the bot took them, you didn't): why you would not take each one (the brief, 4b).

    python tools/explain_extra.py --round 0        -> reports/round0/extra_why_dev.csv

Every extra trade gets each flag below that holds, then ONE category: the first flag in this order
(the reason that sits highest in your process wins, so the re-tries of a trade against your direction
count as against_htf, and `duplicate` is left for re-tries of an idea that was otherwise fine).
  against_htf   against the direction you traded that week (your trades in the same ISO week; if none,
                your trades in the 7 days before)
  no_htf_poi    not at any POI you marked on M15 or higher that was live then (between the mark's start
                and 1 day after its end) and points this way: an order block / FVG / reaction of this
                direction, liquidity on this side, or the starting edge of a range (its bottom quarter for
                a long, top quarter for a short). "At" = inside it or within max(its height, 2 x the bot's
                risk) of it
  inside_range  the entry sits in the middle 40% of the last 6 hours' high-low, not at an edge
  no_sweep      momentum: nothing in the hour before the trigger traded beyond the low (high, for a short)
                of the 6 hours before that, i.e. no liquidity was taken before the break
  weak_break    sniper: the M1 break candle's body is smaller than 3 in 4 of the break candles you marked
                (your M1 BOS marks), both in M1 ATRs
  chop_day      a day (UTC) you took nothing and the bot took 3+ trades or lost 2+ times
  duplicate     a re-entry of the same idea: a sniper re-try, or the bot already had an order the same
                way within 2 h whose entry is within 1R of this one
  other         none of the above
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import REPORTS, load_labels, load_prices  # noqa: E402
from smcml.detectors import atr  # noqa: E402

ORDER = ["against_htf", "no_htf_poi", "inside_range", "no_sweep", "weak_break", "chop_day", "duplicate"]
POI_KINDS = ("ob", "fvg", "liquidity", "range", "reaction")
HTF = ("M15", "M30", "H1", "H4", "D1")


def week_direction(mine):
    """Your direction per ISO week: +1 / -1 if you traded only (or mostly) one way, 0 if split."""
    wk = mine["start"].dt.to_period("W")
    return mine.groupby(wk)["d"].agg(lambda x: int(np.sign(x.sum())))


def your_direction(mine, by_week, t):
    w = pd.Timestamp(t).to_period("W")
    if w in by_week.index:
        return by_week[w]
    before = mine[(mine["start"] < t) & (mine["start"] >= t - pd.Timedelta("7D"))]
    return int(np.sign(before["d"].sum())) if len(before) else 0


LONG_SIDE = {"bull": 1, "bear": -1, "low": 1, "high": -1}      # which trades a mark is a POI for


def poi_marks(marks):
    """Your POI marks on M15+: an order block / FVG / reaction the way it points, liquidity on its side
    (sell-side below = longs), and a range only at the edge a trade starts from (the bottom quarter for
    longs, the top quarter for shorts), so a big range box is not a POI from top to bottom."""
    m = marks[marks["kind"].isin(POI_KINDS) & marks["tf"].isin(HTF)].copy()
    m["lo"] = m["bottom"].fillna(m["level"])
    m["hi"] = m["top"].fillna(m["level"])
    m["until"] = m["end"].fillna(m["start"] + pd.Timedelta("3D")) + pd.Timedelta("1D")
    m["side"] = m["dir"].map(LONG_SIDE).fillna(0).astype(int)        # 0 = either way
    rng = m[m["kind"] == "range"]
    q = (rng["hi"] - rng["lo"]) / 4
    lows = rng.assign(hi=rng["lo"] + q, side=1)
    highs = rng.assign(lo=rng["hi"] - q, side=-1)
    return pd.concat([m[m["kind"] != "range"], lows, highs], ignore_index=True)


def at_your_poi(pm, t, entry, risk, d):
    live = pm[(pm["start"] <= t) & (pm["until"] >= t) & ((pm["side"] == d) | (pm["side"] == 0))]
    if live.empty:
        return False, ""
    gap = np.maximum(live["lo"] - entry, entry - live["hi"]).clip(lower=0)
    room = np.maximum(live["hi"] - live["lo"], 2 * risk)
    near = live[gap <= room]
    if near.empty:
        return False, ""
    r = near.iloc[0]
    return True, f"{r['tf']} {r['kind']} #{r['id']}"


def break_strength(df, a1, times):
    """Body of the M1 candle closing at each time, in M1 ATRs (14)."""
    pos = df.index.searchsorted(pd.to_datetime(times) - pd.Timedelta("1min"))
    pos = np.clip(pos, 0, len(df) - 1)
    body = (df["close"].to_numpy() - df["open"].to_numpy())[pos]
    return np.abs(body) / a1[pos]


def explain(extra, bot_all, df, marks, mine):
    if extra.empty:
        return extra.assign(category=[], flags=[])
    hi, lo, op, cl = (df[k].to_numpy() for k in ("high", "low", "open", "close"))
    a1 = atr(hi, lo, cl, 14)
    pm = poi_marks(marks)
    by_week = week_direction(mine)
    your_bos = marks[(marks["kind"] == "structure") & (marks["tf"] == "M1")]
    yb = break_strength(df, a1, your_bos["end"].dropna() + pd.Timedelta("1min"))
    weak_cut = np.nanquantile(yb, 0.25) if len(yb) else np.nan
    my_days = set(mine["start"].dt.normalize())
    bot_all = bot_all.copy()
    bot_all["day"] = bot_all["decided"].dt.normalize()
    per_day = bot_all.groupby("day").agg(n=("id", "size"), stops=("outcome", lambda x: (x == "stop").sum()))
    out = []
    for r in extra.itertuples():
        d = 1 if r.dir == "long" else -1
        risk = abs(r.entry - r.stop)
        flags, notes = [], []
        prev = bot_all[(bot_all["dir"] == r.dir) & (bot_all["decided"] < r.decided)
                       & (bot_all["decided"] >= r.decided - pd.Timedelta("2h"))
                       & ((bot_all["entry"] - r.entry).abs() <= risk)]
        shot = getattr(r, "shot", 1)
        if (pd.notna(shot) and shot > 1) or len(prev):
            flags.append("duplicate")
            notes.append(f"re-try {int(shot)}" if pd.notna(shot) and shot > 1 else f"after bot #{prev.iloc[-1]['id']}")
        yd = your_direction(mine, by_week, r.decided)
        if yd == -d:
            flags.append("against_htf")
            notes.append(f"you traded {'short' if d == 1 else 'long'} that week")
        day = r.decided.normalize()
        if day not in my_days and day in per_day.index and (per_day.at[day, "n"] >= 3 or per_day.at[day, "stops"] >= 2):
            flags.append("chop_day")
            notes.append(f"bot {per_day.at[day, 'n']} trades / {per_day.at[day, 'stops']} stops that day, you none")
        ok, which = at_your_poi(pm, r.decided, r.entry, risk, d)
        if not ok:
            flags.append("no_htf_poi")
        else:
            notes.append(f"at your {which}")
        if str(r.rule).startswith("sniper") and pd.notna(getattr(r, "first_bos", np.nan)):
            s = break_strength(df, a1, [r.first_bos])[0]
            if np.isfinite(weak_cut) and s < weak_cut:
                flags.append("weak_break")
                notes.append(f"break body {s:.2f} ATR < your 25% {weak_cut:.2f}")
        i = df.index.searchsorted(r.decided)
        w = slice(max(i - 360, 0), i)
        h6, l6 = hi[w].max(), lo[w].min()
        p = (r.entry - l6) / (h6 - l6) if d == 1 else (h6 - r.entry) / (h6 - l6)
        if 0.3 <= p <= 0.7:
            flags.append("inside_range")
            notes.append(f"entry at {p:.0%} of the 6 h range")
        if str(r.rule).startswith("momentum"):
            before, last = slice(max(i - 420, 0), max(i - 60, 0)), slice(max(i - 60, 0), i)
            took = (lo[last].min() < lo[before].min()) if d == 1 else (hi[last].max() > hi[before].max())
            if not took:
                flags.append("no_sweep")
        cat = next((f for f in ORDER if f in flags), "other")
        out.append(dict(id=r.id, category=cat, flags=";".join(flags), note="; ".join(notes)))
    return extra.merge(pd.DataFrame(out), on="id")


def run(round_no, period="dev", df=None):
    out_dir = os.path.join(REPORTS, f"round{round_no}")
    extra = pd.read_csv(os.path.join(out_dir, f"extra_{period}.csv"),
                        parse_dates=["decided", "fill_time", "first_placed", "exit_time", "first_bos"])
    bot = pd.read_csv(os.path.join(out_dir, f"bot_trades_round{round_no}.csv"), parse_dates=["decided", "fill_time"])
    marks, mine, _ = load_labels()
    df = df if df is not None else load_prices()
    res = explain(extra, bot, df, marks, mine)
    res.to_csv(os.path.join(out_dir, f"extra_why_{period}.csv"), index=False)
    return res


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--round", type=int, required=True)
    p.add_argument("--period", default="dev")
    args = p.parse_args()
    res = run(args.round, args.period)
    print(res["category"].value_counts().to_string())
    flags = res["flags"].str.split(";").explode()
    print("\nflags (a trade can have several):")
    print(flags[flags != ""].value_counts().to_string())


if __name__ == "__main__":
    main()
