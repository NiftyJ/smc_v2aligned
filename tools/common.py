"""
Shared by the tools: the price file, your labels, the periods, and the bot's trades as one table.

    from common import load_prices, load_labels, bot_trades, PERIODS

Times are UTC everywhere. The Dukascopy file is UTC and so are the labels, so the bot runs on the
prices as they are (its D1 candles then start at 00:00 UTC) and its trades come out in UTC.
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from strategy import Settings, backtest  # noqa: E402

PRICES = os.path.join(ROOT, "data", "XAUUSD_1m.csv")
LABELS = os.path.join(ROOT, "data", "labels_XAUUSD_1m_15_linked.csv")
REPORTS = os.path.join(ROOT, "reports")
RUN = (pd.Timestamp("2024-01-01"), pd.Timestamp("2025-04-01"))   # the backtest: 2024-01-01 -> 2025-03-31

# [start, end): the brief's periods. Your trades count by the candle you clicked; the bot's by `decided`.
PERIODS = {"dev": (pd.Timestamp("2024-01-05"), pd.Timestamp("2024-08-01")),
           "holdout": (pd.Timestamp("2024-08-01"), pd.Timestamp("2024-11-09")),
           "late": (pd.Timestamp("2024-11-09"), pd.Timestamp("2025-03-13"))}
TF = {"M1": "1min", "M5": "5min", "M15": "15min", "M30": "30min", "H1": "1h", "H4": "4h", "D1": "1D"}
DIR = {"long": 1, "short": -1}


# ----------------------------------------------------------------------------- prices
def load_prices(path=PRICES, start=RUN[0], end=RUN[1]):
    """Dukascopy M1 bars (UTC) as the bot wants them: index 'time', columns open, high, low, close.
    The file mixes '2024-01-02 05:01:00' and '2025-11-17T14:02:00Z' (smcml.data.load_mt5_csv can't read
    that), and repeats some candles where two downloads overlap (Nov 2025): sorted, first copy kept."""
    raw = pd.read_csv(path)
    t = pd.to_datetime(raw["time"], format="mixed", utc=True).dt.tz_localize(None)
    df = pd.DataFrame({k: raw[k].astype(float).to_numpy() for k in ("open", "high", "low", "close")},
                      index=pd.DatetimeIndex(t, name="time"))
    df = df[~df.index.duplicated(keep="first")].sort_index()
    if start is not None:
        df = df[df.index >= start]
    if end is not None:
        df = df[df.index < end]
    return df


# ----------------------------------------------------------------------------- labels
def load_labels(path=LABELS):
    """(marks, trades). Setups whose note starts with SUGGESTED are dropped with everything in them.
    trades gets: d (+1 / -1), tf_td, risk, decision (market / half: the close of the clicked candle),
    fill_candle (limit: the clicked candle = where it filled), period."""
    L = pd.read_csv(path)
    for c in ("start", "end"):
        L[c] = pd.to_datetime(L[c], format="mixed")
    note = L["note"].fillna("").astype(str)
    suggested = set(L.loc[(L["kind"] == "setup") & note.str.startswith("SUGGESTED"), "id"])
    L = L[~L["id"].isin(suggested) & ~L["setup"].isin(suggested)].copy()
    T = L[L["kind"] == "trade"].copy()
    T["d"] = T["dir"].map(DIR).astype(int)
    T["tf_td"] = T["tf"].map(TF).map(pd.Timedelta)
    T["risk"] = (T["entry"] - T["stop"]).abs()
    market = T["order"].isin(["market", "half"])
    T["decision"] = (T["start"] + T["tf_td"]).where(market)
    T["fill_candle"] = T["start"].where(~market)
    T["period"] = period_of(T["start"])
    T = T.sort_values("start", kind="stable").reset_index(drop=True)
    reviewed = L[L["kind"] == "reviewed"]
    return L, T, (reviewed["start"].min(), reviewed["end"].max())


def period_of(times):
    times = pd.Series(pd.to_datetime(times))
    out = pd.Series("", index=times.index, dtype=object)
    for name, (a, b) in PERIODS.items():
        out[(times >= a) & (times < b)] = name
    out[times < PERIODS["dev"][0]] = "pre"
    out[times >= PERIODS["late"][1]] = "after"
    return out.to_numpy()


# ----------------------------------------------------------------------------- the bot's trades
SNIPER_FILTERS = "{trend};poi_{tf}_{zone}_touched;m1_sweep;m1_bos;min_risk"
REENTRY_FILTERS = "{trend};poi_{tf}_{zone}_touched;stopped_before;m1_break_after_stop;min_risk"
MOMENTUM_FILTERS = "m5_bos;{trend};{tf}_pause;pause_not_traded;room_for_stop"


def bot_trades(df, settings=None, trace=None):
    """Runs the bot's backtest on df and returns every order it placed, one row each (the brief's columns
    first): filled sniper and momentum orders from backtest(), plus the sniper orders that were cancelled
    or still waiting at the end (from the journal; backtest() leaves those out)."""
    s = settings or Settings()
    journal = []
    tr = backtest(df, s, journal=journal, trace=trace)
    rows = []
    first = {(j["direction"], j["placed"], j["filled"]): j["first_placed"] for j in journal if j["event"] == "filled"}
    for r in tr.to_dict("records"):
        r = dict(r)
        if r["type"] == "sniper":
            r["first_placed"] = first.get((r["direction"], r["placed"], r["filled"]), r["placed"])
            r["end_reason"] = r["outcome"]
        else:
            r["first_placed"] = r["placed"]
            r["end_reason"] = "not filled (target first or 1 day)" if r["outcome"] == "not filled" else r["outcome"]
        rows.append(r)
    for j in journal:
        if j["event"] == "filled":
            continue
        r = dict(j)
        r.update(filled=pd.NaT, exit_time=pd.NaT, exit=np.nan, outcome="not filled", R=0.0,
                 end_reason=f"{j['event']}: {j['why']}".strip(": "))
        r["rr"] = abs(r["target"] - r["entry"]) / r["risk"]
        rows.append(r)
    t = pd.DataFrame(rows)
    if t.empty:
        return t
    t = t.sort_values(["placed", "type", "direction"], kind="stable").reset_index(drop=True)
    sn = (t["type"] == "sniper").to_numpy()
    shot = (t["shot"].fillna(1).astype(int) if "shot" in t else pd.Series(1, index=t.index)).to_numpy()
    steps = (t["order"] if "order" in t else pd.Series("", index=t.index)).fillna("").to_numpy()
    zone = (t["poi_type"] if "poi_type" in t else pd.Series("ob", index=t.index)).fillna("ob").to_numpy()
    trend = ";".join(f"bias_{k}" for k in s.TREND_TFS) + (f" ({s.TREND_NEED} of {len(s.TREND_TFS)})"
                                                         if s.TREND_NEED < len(s.TREND_TFS) else "")
    rule = [(f"sniper re-entry (try {k})" if k > 1 else "sniper") + f" | {tf} {zk.upper()} | {o}" if is_sn
            else f"momentum | {tf} pause" for is_sn, k, tf, o, zk in zip(sn, shot, t["tf"], steps, zone)]
    out = pd.DataFrame({
        "id": np.arange(1, len(t) + 1),
        "decided": t["placed"].to_numpy(),
        "dir": np.where(t["direction"] == 1, "long", "short"),
        "order": np.where(sn, "limit", "half"),
        "entry": t["entry"].to_numpy(), "stop": t["stop"].to_numpy(), "target": t["target"].to_numpy(),
        "fill_time": t["filled"].to_numpy(),
        "rule": rule,
        "filters_passed": [(REENTRY_FILTERS if k > 1 else SNIPER_FILTERS).format(tf=tf, zone=zk, trend=trend) if is_sn
                           else MOMENTUM_FILTERS.format(tf=tf, trend=trend) for is_sn, k, tf, zk in zip(sn, shot, t["tf"], zone)],
        "outcome": t["outcome"].to_numpy(), "R": t["R"].to_numpy(),
    })
    keep = ["type", "direction", "first_placed", "end_reason", "risk", "rr", "exit_time", "target_tf", "target_type",
            "poi_top", "poi_bottom", "hl", "poi_formed", "poi_known", "poi_touch", "sweep_time", "swept", "broken",
            "first_bos", "m1_ob_time", "shot", "trigger", "pause_top", "pause_bottom", "pause_start"]
    for k in keep:
        if k in t:
            out[k] = t[k].to_numpy()
    return out


def results(trades):
    """Filled trades: count, win rate, mean R, total R, max drawdown in R (equity in exit order)."""
    f = trades[trades["fill_time"].notna()] if "fill_time" in trades else trades
    done = f[f["outcome"].isin(["target", "stop"])]
    n = len(f)
    if n == 0:
        return dict(filled=0, closed=0, win_rate=np.nan, mean_R=np.nan, total_R=0.0, max_dd_R=0.0)
    order = f.sort_values("exit_time" if "exit_time" in f else "fill_time", kind="stable")
    eq = order["R"].fillna(0).cumsum().to_numpy()
    dd = float(np.max(np.maximum.accumulate(np.r_[0.0, eq]) - np.r_[0.0, eq]))
    return dict(filled=n, closed=len(done), win_rate=(done["outcome"] == "target").mean() if len(done) else np.nan,
                mean_R=f["R"].mean(), total_R=f["R"].sum(), max_dd_R=dd)
