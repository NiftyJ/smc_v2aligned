"""
WHY NOT: for a time and a direction, every condition the bot checks and whether it passed, from the
D1 / H4 bias down to the M1 trigger. Read-only: it runs strategy.backtest() with its trace switched on,
which records what each rule decided and changes nothing (tests/test_tools.py checks that).

    python tools/why_not.py --at "2024-03-05 14:20" --dir long              # +-15 min around that time
    python tools/why_not.py --at "2024-03-05 14:20" --dir long --before 480  # the 8 h before (a limit)
    python tools/why_not.py --round 0                 # every missed trade of reports/round0/missed_dev.csv

The sniper chain (strategy._sniper), in the bot's own order:
  1. a POI is armed: price came back into a bullish M15 / M30 / H1 order block (its first touch), less
     than a day ago, the order block not replaced by a newer one, no close below its higher low
  2. no order already waiting in that direction (while one waits, sweep detection is off)
  3. M1 sweep: a candle trades below the last M1 swing low
  4. M1 break: within 30 candles, a close above the high of that drop (or the last swing high)
  5. D1 and H4 bias both up (checked at the break; the POI is used up either way)
  6. the stop is at least 0.25 ATR from the entry, and the entry is below the close
The momentum chain (strategy._momentum): an M5 close above the last M5 swing high, D1 and H4 bias up,
the last closed M5 candle in a pause-up range, that pause not traded yet, room for the stop.
Shorts: the same, mirrored.

CATEGORIES (the brief, 4a), one per missed trade:
  wrong_direction            the bot traded the opposite way in your decision window, not your way
  timing                     the bot took the same idea but too far from you in time (or price, for a
                             limit: decided within 2 h after your window, or entry 0.5-1.5R away)
  no_detection:<detector>    a detector never fired in your window (htf_poi, m1_sweep, m1_bos, m5_bos,
                             m5_pause); your own mark for that step is quoted
  blocked_by_filter:<name>   every detector of a path fired, a filter said no (bias, pending_order,
                             one_setup_per_poi, min_risk, one_per_pause)
  entry_type                 your entry was a limit at an FVG (the bot's entries are an OB open or half)
  other                      explained in the note
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import REPORTS, TF, bot_trades, load_labels, load_prices  # noqa: E402
from strategy import Settings  # noqa: E402

WINDOW = pd.Timedelta("15min")
LIMIT_BEFORE = pd.Timedelta("8h")
# how far each stage got (higher = further along the chain)
SNIPER_RANK = [("order placed", 9, ""), ("re-entry order placed", 9, ""),
               ("sweep + break, but D1 / H4 bias disagree", 8, "blocked_by_filter:bias"),
               ("sweep + break, but the order block is too close", 8, "blocked_by_filter:min_risk"),
               ("break, but the stop is too tight", 8, "blocked_by_filter:min_risk"),
               ("swept, waiting for the break", 6, "no_detection:m1_bos"),
               ("swept, no break within", 6, "no_detection:m1_bos"),
               ("sweep", 5, "no_detection:m1_bos"),
               ("an order is already waiting", 4, "blocked_by_filter:pending_order"),
               ("waiting for a sweep", 3, "no_detection:m1_sweep"),
               ("swing low already swept", 3, "no_detection:m1_sweep"),
               ("no swing low yet", 3, "no_detection:m1_sweep"),
               ("no POI armed (this POI already had its setup)", 2, "blocked_by_filter:one_setup_per_poi"),
               ("no POI armed", 1, "no_detection:htf_poi"),
               ("disarmed", 1, "no_detection:htf_poi")]
MOMENTUM_RANK = [("order placed", 9, ""),
                 ("M5 break in a pause, but no room for a stop", 8, "blocked_by_filter:min_risk"),
                 ("M5 break, but this pause was already traded", 8, "blocked_by_filter:one_per_pause"),
                 ("M5 break, but D1 / H4 bias disagree", 7, "blocked_by_filter:bias"),
                 ("M5 break, but no", 5, "no_detection:m5_pause"),
                 ("no M5 break of structure", 3, "no_detection:m5_bos")]


def rank(stage, table):
    for prefix, r, cat in table:
        if stage.startswith(prefix):
            return r, cat
    return 0, "other"


# ----------------------------------------------------------------------------- running the trace
def windows_of(trades):
    """Your decision window per trade: market / half: decision +-15 min; limit: 8 h before the fill
    candle to its end (the brief's matching windows)."""
    out = []
    for r in trades.itertuples():
        if r.order in ("market", "half"):
            out.append((r.decision - WINDOW, r.decision + WINDOW))
        else:
            out.append((r.fill_candle - LIMIT_BEFORE, r.fill_candle + r.tf_td))
    return out


def run_trace(df, wins, settings=None):
    """One backtest with the trace on for every M1 / M5 candle whose CLOSE is inside one of the windows.
    Returns (bot trades, sniper records, momentum records, the sniper's POIs)."""
    base = pd.Timedelta("1min")
    closes = df.index + base
    m1 = set()
    m5_index = df.index.floor("5min").unique()
    m5_closes = m5_index + pd.Timedelta("5min")
    m5 = set()
    for a, b in wins:
        i, j = closes.searchsorted(a, side="left"), closes.searchsorted(b, side="right")
        m1.update(range(i, j))
        i, j = m5_closes.searchsorted(a, side="left"), m5_closes.searchsorted(b, side="right")
        m5.update(range(i, j))
    trace = {"sniper": {"bars": m1, "out": []}, "momentum": {"m5": m5, "out": []}}
    bot = bot_trades(df, settings or Settings(), trace=trace)
    sn = pd.DataFrame(trace["sniper"]["out"])
    if len(sn):
        sn["time"] = closes[sn["t"].to_numpy()]
    mo = pd.DataFrame(trace["momentum"]["out"])
    return bot, sn, mo, trace["sniper"].get("pois", {})


# ----------------------------------------------------------------------------- explaining one trade
def bias_at(sn, d, a, b):
    w = sn[(sn["direction"] == d) & (sn["time"] >= a) & (sn["time"] <= b)]
    if w.empty:
        return np.nan, np.nan, 0.0
    ok = (w["bias_d1"] == d) & (w["bias_h4"] == d)
    last = w.iloc[-1]
    return int(last["bias_d1"]), int(last["bias_h4"]), float(ok.mean())


def furthest(rec, table, d, a, b, key="time"):
    w = rec[(rec["direction"] == d) & (rec[key] >= a) & (rec[key] <= b)] if len(rec) else rec
    if w is None or w.empty:
        return None
    r = [rank(s, table) for s in w["stage"].fillna("")]
    k = int(np.argmax([x[0] for x in r]))
    row = w.iloc[k]
    return dict(stage=row["stage"], rank=r[k][0], category=r[k][1], time=row[key], row=row)


def my_marks(marks, trade):
    """Your marks in the trade's setup, by step."""
    m = marks[(marks["setup"] == trade.setup) & (marks["kind"] != "trade")]
    return m.sort_values("start")


def mark_text(m):
    if m is None or m.empty:
        return "none"
    out = []
    for r in m.itertuples():
        where = f"{r.bottom:.2f}-{r.top:.2f}" if pd.notna(r.top) else f"{r.level:.2f}" if pd.notna(r.level) else ""
        out.append(f"{r.tf} {r.kind}{' ' + r.subtype if isinstance(r.subtype, str) else ''} #{r.id} "
                   f"{r.start:%m-%d %H:%M} {where}".strip())
    return "; ".join(out)


def pois_near(pois, d, t, price, k=3):
    """The bot's armed POIs (order blocks / FVGs) the same way, nearest in time to t, with their zones."""
    rows = []
    for t0, t1, info in pois.get(d, []):
        t0, t1 = pd.Timestamp(t0), pd.Timestamp(t1)
        gap = pd.Timedelta(0) if t0 <= t <= t1 else min(abs(t - t0), abs(t - t1))
        rows.append((gap, t0, t1, info))
    rows.sort(key=lambda x: x[0])
    return [f"{i['tf']} {i.get('poi_type', 'ob').upper()} {i['poi_bottom']:.2f}-{i['poi_top']:.2f} "
            f"armed {a:%m-%d %H:%M}->{b:%m-%d %H:%M}" for _, a, b, i in rows[:k]]


def explain(trade, bot, sn, mo, pois, marks):
    """Category, failing condition and the values behind it, for one missed trade of yours."""
    d = trade.d
    if trade.order in ("market", "half"):
        a, b = trade.decision - WINDOW, trade.decision + WINDOW
        when = trade.decision
    else:
        a, b = trade.fill_candle - LIMIT_BEFORE, trade.fill_candle + trade.tf_td
        when = trade.fill_candle
    res = dict(id=trade.id, setup=trade.setup, start=trade.start, dir=trade.dir, order=trade.order,
               subtype=trade.subtype, entry=trade.entry, stop=trade.stop, window_from=a, window_to=b)
    d1, h4, ok_share = bias_at(sn, d, a, b)
    res.update(bias_d1=d1, bias_h4=h4, bias_ok_share=ok_share)
    same = bot[(bot["d"] == d)]
    opp = bot[(bot["d"] == -d) & (bot["decided"] >= a) & (bot["decided"] <= b)]
    in_win = same[(same["decided"] >= a) & (same["decided"] <= b)]
    marks_t = my_marks(marks, trade)
    res["your_marks"] = mark_text(marks_t)
    # ---- the bot took something in or near your window
    def bot_txt(x):
        return (f"bot #{x['id']} {x['dir']} {x['rule']} decided {x['decided']:%m-%d %H:%M} entry {x['entry']:.2f} "
                f"({abs(x['entry'] - trade.entry) / trade.risk:.2f}R from yours, "
                f"{(x['decided'] - when) / pd.Timedelta('1min'):+.0f} min)")
    if trade.order == "limit":
        dist = (in_win["entry"] - trade.entry).abs() / trade.risk
        later = same[(same["decided"] > b) & (same["decided"] <= b + pd.Timedelta("2h"))
                     & ((same["entry"] - trade.entry).abs() <= 0.5 * trade.risk)]
        fvg = marks_t[(marks_t["kind"] == "fvg") & (marks_t["tf"] == "M1")]
        at_fvg = fvg[(fvg["bottom"] - 0.25 * trade.risk <= trade.entry) & (trade.entry <= fvg["top"] + 0.25 * trade.risk)]
        if (dist <= 0.5).any():
            res.update(category="other", condition="one bot trade for two of yours (it matched your other trade)",
                       values=bot_txt(in_win[dist <= 0.5].iloc[0]))
        elif len(later):
            res.update(category="timing", condition="same entry, decided after your fill candle (within 2 h)",
                       values=bot_txt(later.iloc[0]))
        elif len(in_win) and len(at_fvg):
            res.update(category="entry_type", condition="your limit sat at an M1 FVG; the bot's at an M1 OB open",
                       values=f"your FVG #{at_fvg.iloc[0]['id']}; " + bot_txt(in_win.iloc[dist.argmin()]))
        elif (dist <= 1.5).any():
            res.update(category="other", condition="same idea, the bot's limit 0.5-1.5R from yours",
                       values=bot_txt(in_win.iloc[dist.argmin()]))
        elif len(in_win):
            res.update(category="other", condition="the bot took the same direction in your window at another level",
                       values=bot_txt(in_win.iloc[dist.argmin()]))
        if "category" in res:
            return res
    else:
        dt = (same["decided"] - when).abs()
        if (dt <= WINDOW).any():
            res.update(category="other", condition="one bot trade for two of yours (it matched your other trade)",
                       values=bot_txt(same[dt <= WINDOW].iloc[0]))
            return res
        if (dt <= pd.Timedelta("2h")).any():
            res.update(category="timing", condition="same direction within 2 h, not within 15 min",
                       values=bot_txt(same.loc[dt.idxmin()]))
            return res
        opp = bot[(bot["d"] == -d) & ((bot["decided"] - when).abs() <= pd.Timedelta("2h"))]
    if len(opp) and not len(in_win):
        x = opp.iloc[0]
        res.update(category="wrong_direction", condition="the bot traded the other way in your window",
                   values=bot_txt(x))
        return res
    # ---- nothing taken: how far did each path get?
    f_sn = furthest(sn, SNIPER_RANK, d, a, b)
    f_mo = furthest(mo, MOMENTUM_RANK, d, a, b) if len(mo) else None
    paths = [p for p in (("sniper", f_sn), ("momentum", f_mo)) if p[1] is not None]
    if not paths:
        res.update(category="other", condition="no candles in the window", values="")
        return res
    # your label says which setup it is (sniper / momentum, the bot's two): explain it by that chain
    prefer = "momentum" if trade.subtype == "momentum" else "sniper"
    paths.sort(key=lambda p: p[0] == prefer, reverse=True)
    name, f = paths[0]
    res["path"] = name
    res["furthest"] = f["stage"]
    if len(paths) > 1:
        res["other_path"] = f"{paths[1][0]}: {paths[1][1]['stage']}"
    cat = f["category"] or "other"
    vals = f"bias D1 {d1:+d} H4 {h4:+d} at the end of the window ({ok_share:.0%} of it agreeing)" \
        if np.isfinite(d1) else ""
    if cat == "blocked_by_filter:bias":
        cat = "blocked_by_filter:bias_d1" if d1 != d else "blocked_by_filter:bias_h4" if h4 != d else cat
        row = f["row"]
        vals = f"at {f['time']:%m-%d %H:%M}: D1 {int(row.get('bias_d1', 0)):+d} H4 {int(row.get('bias_h4', 0)):+d} " \
               f"(your direction {d:+d})"
    elif cat == "no_detection:htf_poi":
        mine = marks_t[marks_t["step"].isin(["htf_poi", "h1_poi", "m15_poi", "htf_range"])]
        vals = f"your POI: {mark_text(mine)} | bot POIs nearest in time: " + \
               "; ".join(pois_near(pois, d, when, trade.entry)) + " | " + vals
    elif cat in ("no_detection:m1_sweep", "no_detection:m1_bos"):
        row = f["row"]
        step = "sweep" if cat.endswith("sweep") else "m1_bos"
        mine = marks_t[marks_t["step"] == step] if step == "m1_bos" else marks_t[marks_t["kind"] == "sweep"]
        vals = (f"bot POI {row.get('poi_tf', '')} {str(row.get('poi_poi_type', 'ob')).upper()} "
                f"{row.get('poi_poi_bottom', np.nan):.2f}-{row.get('poi_poi_top', np.nan):.2f}; "
                f"bot M1 swing low {row.get('swing_low', np.nan):.2f} high {row.get('swing_high', np.nan):.2f}"
                + (f", break level {row.get('break_level'):.2f}" if pd.notna(row.get("break_level", np.nan)) else "")
                + f" | yours: {mark_text(mine)} | " + vals)
    elif cat in ("no_detection:m5_pause", "no_detection:m5_bos"):
        mine = marks_t[marks_t["kind"] == "range"]
        vals = f"your ranges: {mark_text(mine)} | " + vals
    elif cat == "blocked_by_filter:pending_order":
        w = bot[(bot["d"] == d) & (bot["decided"] < f["time"])].tail(1)
        if len(w):
            x = w.iloc[0]
            vals = f"waiting: bot #{x['id']} placed {x['decided']:%m-%d %H:%M} entry {x['entry']:.2f} " \
                   f"({x['end_reason']}) | " + vals
    res.update(category=cat, condition=f["stage"], values=vals)
    return res


def classify(missed, df=None, marks=None, settings=None):
    df = df if df is not None else load_prices()
    if marks is None:
        marks, _, _ = load_labels()
    wins = windows_of(missed)
    bot, sn, mo, pois = run_trace(df, wins, settings)
    bot["d"] = np.where(bot["dir"] == "long", 1, -1)
    if len(mo):     # a bias "no" only blocks a momentum trade if its pause range was on
        no_pause = mo["stage"].str.startswith("M5 break, but D1 / H4 bias disagree") & (mo.get("pause_on", 0) != 1)
        mo.loc[no_pause, "stage"] = "M5 break, but no M5 pause range in this direction (and the bias disagrees)"
    rows = [explain(r, bot, sn, mo, pois, marks) for r in missed.itertuples()]
    return pd.DataFrame(rows), sn, mo


# ----------------------------------------------------------------------------- CLI
def print_one(at, d, before, after, settings=None):
    df = load_prices()
    marks, mine, _ = load_labels()
    at = pd.Timestamp(at)
    a, b = at - pd.Timedelta(minutes=before), at + pd.Timedelta(minutes=after)
    bot, sn, mo, pois = run_trace(df, [(a, b)], settings)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_colwidth", 90)
    cols = ["time", "bias_d1", "bias_h4", "poi", "pending", "machine", "swing_low", "swing_high", "break_level", "stage"]
    w = sn[sn["direction"] == d]
    print(f"SNIPER {'long' if d == 1 else 'short'} {a} -> {b} (candle closes):")
    print(w[cols].to_string(index=False) if len(w) else "  (no candles)")
    if len(mo):
        print("\nMOMENTUM (M5 closes):")
        print(mo[mo["direction"] == d].drop(columns=["m5_bar", "direction"]).to_string(index=False))
    print("\nbot POIs armed nearest to that time:", *pois_near(pois, d, at, np.nan, 5), sep="\n  ")
    near = bot[(bot["decided"] >= a - pd.Timedelta("2h")) & (bot["decided"] <= b + pd.Timedelta("2h"))]
    print("\nbot orders within 2 h of the window:")
    print(near[["id", "decided", "dir", "order", "entry", "stop", "target", "fill_time", "rule", "outcome", "R"]]
          .to_string(index=False) if len(near) else "  none")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--at", help="UTC time, e.g. '2024-03-05 14:20'")
    p.add_argument("--dir", choices=["long", "short"])
    p.add_argument("--before", type=int, default=15, help="minutes before --at (480 for a limit's 8 h)")
    p.add_argument("--after", type=int, default=15)
    p.add_argument("--round", type=int, help="explain every missed trade of reports/round<N>/missed_<period>.csv")
    p.add_argument("--period", default="dev")
    args = p.parse_args()
    if args.round is not None:
        out_dir = os.path.join(REPORTS, f"round{args.round}")
        _, mine, _ = load_labels()
        ids = pd.read_csv(os.path.join(out_dir, f"missed_{args.period}.csv"))["id"]
        res, _, _ = classify(mine[mine["id"].isin(ids)])
        path = os.path.join(out_dir, f"why_not_{args.period}.csv")
        res.to_csv(path, index=False)
        print(res["category"].value_counts().to_string())
        print(f"saved {path}")
    elif args.at and args.dir:
        print_one(args.at, 1 if args.dir == "long" else -1, args.before, args.after)
    else:
        p.error("give --at and --dir, or --round")


if __name__ == "__main__":
    main()
