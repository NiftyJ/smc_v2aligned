"""
LEAK CHECK: could the backtest have used a price that live trading would not have had yet?

    python tools/leak_check.py             -> reports/backtest/leak_check.md and leak_check.csv  (about 30 minutes)
    python tools/leak_check.py --quick     -> the first 5 months, fewer cuts, no self-test (a smoke test)
    python tools/leak_check.py --self-test-only

A leak (look-ahead) is a decision on candle t that depends on a candle after t: the backtest then knows
some of the future and looks better than live trading can be. The checks, on data/XAUUSD_1m.csv with the
bot's own code and settings:

1. The data. Time stamps must be candle OPEN times, UTC: the bot reads candle t as closing at t + 1 minute,
   so close-time stamps would let every decision see a minute ahead. The US data releases at 12:30 / 13:30
   UTC show it: their spike is in the candle stamped :30, not :31. Also: the two downloads in the file
   agree where they overlap, and no candle is repeated or impossible.
2. The trend (D1, H4, H1). Every price from a cut on is moved $300 up, then down: the trend on every
   candle before the cut must stay the same. A trend read from a candle still forming would change.
3. The zones (FVGs, order blocks and swing points on M15, M30, H1, H4, D1: the sniper's POIs and the
   targets) and the M5 pause ranges (momentum): the same test. Every zone known by the cut, and when it
   was used up if that was before the cut, must stay the same.
4. The whole bot, replayed. It is run on the prices up to a cut only, as live trading would have them,
   and must have done exactly what the full run did up to then: the same orders, moves, cancels, fills
   and exits, the same result for every trade closed by then, and the same orders waiting at the cut.
   The cuts sit on candles where the full run decided something (a sniper order, a move to the next
   range, a re-try, a fill, a stop, a target, a cancel, a momentum order, its fill), because a look-ahead
   of a few candles only shows on the last candle before the cut.

A test passes only with zero differences. And a check that can't fail proves nothing, so the self-test
plants one leak per test (the trend read from the candle still forming, zones known one candle early, the
bot's stops using the ATR of the next candle) and each must be caught.
"""
import argparse
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import PRICES, REPORTS, load_prices, low_priority  # noqa: E402
from strategy import Settings, _momentum, _sniper, shapes  # noqa: E402
from bias import htf_bias  # noqa: E402
from poi import pois  # noqa: E402
from smcml.bias import bar_length  # noqa: E402
from smcml.detectors import atr  # noqa: E402

OUT = os.path.join(REPORTS, "backtest")
POISON = 300.0                                          # $ added to (then taken from) every price from the cut on
ZONE_TFS = ("15min", "30min", "1h", "4h", "1D")         # the sniper's POIs (M15 - H1) and the targets (H1 - D1)
PRICE_COLS = ["open", "high", "low", "close"]
ZONE_KEY = ["tf", "type", "top", "bottom", "origin", "formed", "known"]
SNIPER_DECISION = ["entry", "stop", "target", "risk", "target_tf", "target_type", "tf", "poi_type", "poi_top",
                   "poi_bottom", "hl", "poi_formed", "poi_known", "poi_touch", "sweep_time", "swept", "broken",
                   "first_bos", "m1_ob_time", "order", "shot"]
MOMENTUM_DECISION = ["entry", "stop", "target", "risk", "trigger", "tf", "pause_top", "pause_bottom", "pause_start"]
CANCEL_FIELDS = ["entry", "stop", "target", "why", "ended", "shot", "order", "tf", "poi_formed", "poi_touch"]
RESULT = ["exit_time", "exit", "outcome", "R"]


# ----------------------------------------------------------------------------- helpers
def norm(v):
    """One spelling per value, so dict keys and comparisons work across numpy / pandas types."""
    if isinstance(v, (np.datetime64, pd.Timestamp)):
        return pd.Timestamp(v)
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating):
        return float(v)
    return v


def missing(v):
    return v is None or (not isinstance(v, str) and pd.isna(v))


def same(a, b):
    """Equal, with NaN / NaT equal to each other and floats to 1e-9."""
    a, b = norm(a), norm(b)
    if missing(a) or missing(b):
        return missing(a) and missing(b)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= 1e-9 * max(1.0, abs(a))
    return a == b


def keyed(records, fields):
    return {tuple(norm(r[f]) for f in fields): r for r in records}


def poisoned(df, cut, shift):
    """df with every price from the candle at `cut` on moved by `shift` dollars."""
    p = df.copy()
    p.loc[p.index >= cut, PRICE_COLS] += shift
    return p


def row(test, cut, what, compared, mismatches, detail=""):
    return dict(test=test, cut=cut, what=what, compared=int(compared), mismatches=int(mismatches),
                result="PASS" if mismatches == 0 else "FAIL", detail=detail)


def run_raw(df, s):
    """backtest() and live_orders(recent=None) in one pass: the filled sniper trades, the momentum orders,
    the sniper journal (every order's end) and the orders still waiting at the last candle."""
    base = bar_length(df.index)
    bias, z = htf_bias(df), pois(df)
    journal, live = [], []
    sniper = _sniper(df, s, bias, z, base, live=live, journal=journal)
    momentum = _momentum(df, s, bias, z, base, live=live)
    return dict(sniper=pd.DataFrame(sniper), momentum=pd.DataFrame(momentum), journal=journal, live=live, base=base)


# ----------------------------------------------------------------------------- 1. the data
def check_data(path=PRICES):
    raw = pd.read_csv(path)
    t = pd.to_datetime(raw["time"], format="mixed", utc=True).dt.tz_localize(None).to_numpy()
    iso = raw["time"].astype(str).str.endswith("Z").to_numpy()
    out = []
    a = raw.loc[~iso, PRICE_COLS].set_index(pd.DatetimeIndex(t[~iso]))
    b = raw.loc[iso, PRICE_COLS].set_index(pd.DatetimeIndex(t[iso]))
    a, b = a[~a.index.duplicated()], b[~b.index.duplicated()]
    both = a.join(b, lsuffix="_a", rsuffix="_b", how="inner")
    if len(both):
        gap = np.abs(both[[f"{k}_a" for k in PRICE_COLS]].to_numpy() - both[[f"{k}_b" for k in PRICE_COLS]].to_numpy())
        shifted = max(np.mean(np.isclose(a["close"].reindex(b.index + pd.Timedelta(minutes=m)).to_numpy(),
                                         b["close"].to_numpy())) for m in (-1, 1))
        bad = int((gap[:, [0, 3]] > 1e-9).any(axis=1).sum())
        out.append(row("data", pd.NaT, "the two downloads agree where they overlap (open and close)", len(both),
                       bad + (shifted > 0.05),
                       f"{len(both):,} candles in both ({both.index.min():%Y-%m-%d} -> {both.index.max():%Y-%m-%d}); "
                       f"largest high/low difference ${gap[:, 1:3].max():.2f}; closes one minute apart agree "
                       f"{shifted:.1%} of the time (so neither part is shifted)"))
    df = load_prices(path, start=None, end=None)
    rng = df["high"] - df["low"]
    wd = df.index.dayofweek < 5
    mean = {(h, m): rng[wd & (df.index.hour == h) & (df.index.minute == m)].mean() for h in (12, 13) for m in (29, 30, 31)}
    ok = all(mean[h, 30] > mean[h, 31] and mean[h, 30] > mean[h, 29] for h in (12, 13))
    out.append(row("data", pd.NaT, "time stamps are candle opens (US releases at 12:30 / 13:30 UTC)", 4, 0 if ok else 1,
                   "average candle size, weekdays: " + ", ".join(f"{h}:{m:02d} ${mean[h, m]:.2f}" for h in (12, 13)
                                                                  for m in (29, 30, 31))))
    out.append(row("data", pd.NaT, "no candle repeated or out of order after loading", len(df),
                   int(df.index.duplicated().sum() + (not df.index.is_monotonic_increasing)),
                   f"{len(raw) - len(df):,} repeated rows in the file (the overlap) are read once"))
    imp = (df["high"] < df[["open", "close"]].max(axis=1)) | (df["low"] > df[["open", "close"]].min(axis=1))
    out.append(row("data", pd.NaT, "no impossible candle (high / low outside open / close)", len(df), int(imp.sum())))
    out.append(row("data", pd.NaT, "every time stamp on a whole minute", len(df), int((df.index.second != 0).sum())))
    return out, df


# ----------------------------------------------------------------------------- 2. and 3. poisoned futures
def check_trend(df, cuts, bias_fn=htf_bias):
    ref = bias_fn(df)
    out = []
    for cut in cuts:
        before = ref.index < cut
        for shift in (POISON, -POISON):
            b = bias_fn(poisoned(df, cut, shift))
            bad = (b.loc[before] != ref.loc[before]).any(axis=1)
            first = f"first difference {bad[bad].index[0]}" if bad.any() else ""
            out.append(row("trend D1 / H4 / H1", cut, f"prices {shift:+.0f} from the cut", before.sum() * 3, bad.sum(), first))
    return out


def zones_by(z, cut):
    k = z[z["known"] <= cut].copy()
    k["origin"] = k["origin"].fillna(-1.0)
    k["used"] = k["used"].where(k["used"] <= cut)                # used up by the cut, else not yet
    return k[ZONE_KEY + ["used"]]


def check_zones(df, cuts, zones_fn=pois):
    ref = zones_fn(df, tfs=ZONE_TFS)
    out = []
    for cut in cuts:
        a = zones_by(ref, cut)
        for shift in (POISON, -POISON):
            b = zones_by(zones_fn(poisoned(df, cut, shift), tfs=ZONE_TFS), cut)
            m = a.merge(b, on=ZONE_KEY, how="outer", suffixes=("_a", "_b"), indicator=True)
            alone = m["_merge"] != "both"
            used = ~alone & ~((m["used_a"] == m["used_b"]) | (m["used_a"].isna() & m["used_b"].isna()))
            detail = "; ".join(f"{r['tf']} {r['type']} known {r['known']} only {'with' if r['_merge'] == 'right_only' else 'without'}"
                               " the poison" for r in m[alone].head(3).to_dict("records"))
            out.append(row("zones M15 - D1", cut, f"prices {shift:+.0f} from the cut", len(a), alone.sum() + used.sum(), detail))
    return out


def check_pause(df, cuts):
    ref = shapes(df, "5min")
    out = []
    for cut in cuts:
        closed = (ref.index + pd.Timedelta("5min")) <= cut
        a = ref[closed]
        for shift in (POISON, -POISON):
            b = shapes(poisoned(df, cut, shift), "5min").loc[a.index]
            bad = ~((a == b) | (a.isna() & b.isna())).all(axis=1)
            first = f"first difference {bad[bad].index[0]}" if bad.any() else ""
            out.append(row("M5 pause ranges", cut, f"prices {shift:+.0f} from the cut", len(a), bad.sum(), first))
    return out


# ----------------------------------------------------------------------------- 4. the bot, replayed
def sniper_orders(ref):
    """Every sniper order of a run, one dict each: filled ones (from the trades) and the rest (journal)."""
    first = {(norm(j["direction"]), norm(j["placed"]), norm(j["filled"])): j["first_placed"]
             for j in ref["journal"] if j["event"] == "filled"}
    out = []
    for r in ref["sniper"].to_dict("records") if len(ref["sniper"]) else []:
        out.append(dict(r, first_placed=first[(norm(r["direction"]), norm(r["placed"]), norm(r["filled"]))],
                        end=pd.Timestamp(r["filled"]), event="filled"))
    for j in ref["journal"]:
        if j["event"] != "filled":
            out.append(dict(j, end=pd.Timestamp(j["ended"])))
    return out


def replay(ref, df, c, s):
    """Runs the bot on df[: c + 1] (the prices up to candle c only) and lists every difference with the full
    run up to the close of candle c. Returns (number of things compared, differences)."""
    tr = run_raw(df.iloc[:c + 1], s)
    t_open, t_close = df.index[c], df.index[c] + ref["base"]
    diffs, n = [], 0

    def pair(a, b, what, fields):
        """The same things in both runs, with the same values; if filled by the cut, at the same candle,
        and if closed by the cut, with the same exit and R (else still open in the cut run)."""
        nonlocal n
        for k in sorted(a.keys() | b.keys(), key=str):
            n += 1
            if k not in a or k not in b:
                diffs.append(f"{what} {k} only in the {'full' if k in a else 'cut'} run")
                continue
            x, y = a[k], b[k]
            bad = [f for f in fields if not same(x.get(f), y.get(f))]
            fx, fy = (pd.Timestamp(v["filled"]) if not missing(v.get("filled")) else pd.NaT for v in (x, y))
            fx = fx if not missing(fx) and fx <= t_open else pd.NaT     # the full run's fill, if by the cut
            if not same(fx, fy):
                bad.append(f"filled {fx} (full run) / {fy} (cut run)")
            elif not missing(fx):
                if pd.Timestamp(x["exit_time"]) <= t_close:
                    bad += [f for f in RESULT if not same(x[f], y[f])]
                elif y["outcome"] != "open":
                    bad.append(f"outcome {y['outcome']} (the full run was still in the trade)")
            if bad:
                diffs.append(f"{what} {k}: " + ", ".join(bad))

    by_fill = lambda t: t[t["filled"] <= t_open].to_dict("records") if len(t) else []   # noqa: E731
    pair(keyed(by_fill(ref["sniper"]), ["direction", "placed", "filled"]),
         keyed(by_fill(tr["sniper"]), ["direction", "placed", "filled"]), "sniper trade", SNIPER_DECISION)
    mom = lambda t: t[t["placed"] <= t_close].to_dict("records") if len(t) else []     # noqa: E731
    pair(keyed(mom(ref["momentum"]), ["direction", "placed"]), keyed(mom(tr["momentum"]), ["direction", "placed"]),
         "momentum order", MOMENTUM_DECISION)
    cancelled = lambda j: [x for x in j if x["event"] == "cancelled" and pd.Timestamp(x["ended"]) <= t_close]  # noqa: E731
    pair(keyed(cancelled(ref["journal"]), ["direction", "first_placed", "placed"]),
         keyed(cancelled(tr["journal"]), ["direction", "first_placed", "placed"]), "cancelled sniper order", CANCEL_FIELDS)
    # the sniper orders waiting at the close of candle c
    alive = [o for o in sniper_orders(ref) if pd.Timestamp(o["first_placed"]) <= t_close
             and (o["end"] > t_open if o["event"] == "filled" else o["end"] > t_close)]
    a = keyed(alive, ["direction", "poi_touch", "shot"])
    b = keyed([x for x in tr["live"] if x["type"] == "sniper"], ["direction", "poi_touch", "shot"])
    for k in sorted(a.keys() | b.keys(), key=str):
        n += 1
        if k not in a or k not in b:
            diffs.append(f"waiting sniper order {k} only in the {'full' if k in a else 'cut'} run")
        elif pd.Timestamp(a[k]["placed"]) <= t_close:         # not moved after the cut: it must be the same order
            bad = [f for f in ("placed", "entry", "stop", "target") if not same(a[k][f], b[k][f])]
            if bad:
                diffs.append(f"waiting sniper order {k}: " + ", ".join(bad))
    return n, diffs


def decision_events(ref, df):
    """(what, candle) for every decision of the full run: the candle it was made on (at its close)."""
    closes = df.index + ref["base"]
    at_close = lambda t: int(np.searchsorted(closes, pd.Timestamp(t)))     # noqa: E731
    at_open = lambda t: int(np.searchsorted(df.index, pd.Timestamp(t)))    # noqa: E731
    ev = []
    for o in sniper_orders(ref):
        ev.append(("sniper order" if o["shot"] == 1 else "sniper re-try after a stop", at_close(o["first_placed"])))
        if pd.Timestamp(o["placed"]) != pd.Timestamp(o["first_placed"]):
            ev.append(("sniper order moved to the next range", at_close(o["placed"])))
        if o["event"] == "cancelled":
            ev.append(("sniper order cancelled", at_close(o["ended"])))
        if o["event"] == "filled":
            ev.append(("sniper fill", at_open(o["filled"])))
            if o["outcome"] in ("stop", "target"):
                ev.append((f"sniper {o['outcome']}", at_close(o["exit_time"])))
    for r in ref["momentum"].to_dict("records") if len(ref["momentum"]) else []:
        ev.append(("momentum order", at_close(r["placed"])))
        if pd.notna(r["filled"]):
            ev.append(("momentum fill", at_open(r["filled"])))
            if r["outcome"] in ("stop", "target"):
                ev.append((f"momentum {r['outcome']}", at_close(r["exit_time"])))
    return pd.DataFrame(ev, columns=["what", "bar"])


def pick_cuts(ev, df, early_end, late, rng):
    """One decision of each kind before early_end (short runs), plus one decision in each late window."""
    ev = ev[ev["bar"] < len(df)]
    t = df.index[ev["bar"].to_numpy()]
    out = []
    early = ev[t < early_end]
    for what, g in early.groupby("what", sort=True):
        out.append((what, int(g["bar"].iloc[rng.integers(len(g))])))
    for a, b in late:
        g = ev[(t >= a) & (t < b)]
        if len(g):
            r = g.iloc[rng.integers(len(g))]
            out.append((r["what"], int(r["bar"])))
    return sorted(out, key=lambda x: x[1])


def check_replay(ref, df, s, cuts, log=print):
    out = []
    for what, c in cuts:
        t0 = time.time()
        n, diffs = replay(ref, df, c, s)
        out.append(row("whole bot replayed", df.index[c], f"{what}: run on the prices up to this candle only", n,
                       len(diffs), "; ".join(diffs[:4])))
        log(f"  replay to {df.index[c]} ({what}): {n} compared, {len(diffs)} differences, {time.time() - t0:.0f}s")
    return out


# ----------------------------------------------------------------------------- the checks must catch a real leak
def leaky_bias(df, lookback=10, use_close=True):
    """PLANTED LEAK (self-test only): bias.htf_bias reading the D1 / H4 / H1 candle that is still forming."""
    from bias import TIMEFRAMES, compute_bias
    from smcml.bias import resample
    out = pd.DataFrame(index=df.index)
    closes = (df.index + bar_length(df.index)).to_numpy()
    for name, tf in TIMEFRAMES.items():
        htf = resample(df, tf)
        b = compute_bias(htf, lookback, use_close).to_numpy()
        k = np.searchsorted(htf.index.to_numpy(), closes, side="right") - 1      # by START: the candle not closed yet
        out[f"bias_{name}"] = np.where(k >= 0, b[np.clip(k, 0, None)], 0).astype(int)
    return out


def leaky_zones(df, tfs, swing_n=5):
    """PLANTED LEAK (self-test only): every zone known one candle of its timeframe early."""
    z = pois(df, tfs=tfs, swing_n=swing_n)
    z["known"] = z["known"] - z["tf"].map(pd.Timedelta)
    return z


def leaky_atr(h, l, c, n):
    """PLANTED LEAK (self-test only): the ATR of the next candle."""
    a = atr(h, l, c, n)
    return np.r_[a[1:], a[-1:]]


def self_test(log=print):
    """Plants one leak per test, on the first 5 months, and checks that the test finds it: the trend read
    from the candle still forming, zones known one candle early, and the bot reading the ATR one candle
    ahead (its stops; the replay must catch it). Returns rows: PASS = the planted leak was caught."""
    import strategy
    rng = np.random.default_rng(7)
    df = load_prices(start=None, end=pd.Timestamp("2024-06-01"))
    inside = df.index[(df.index >= pd.Timestamp("2024-02-15")) & (df.index < pd.Timestamp("2024-05-25"))]
    cuts = sorted(inside[np.sort(rng.choice(len(inside), 4, replace=False))])
    out = []

    def caught(what, rows):
        n, found = sum(r["compared"] for r in rows), sum(r["mismatches"] for r in rows)
        out.append(dict(test="self-test (planted leaks)", cut=pd.NaT, what=what, compared=n, mismatches=found,
                        result="PASS" if found else "FAIL",
                        detail=f"caught in {sum(r['mismatches'] > 0 for r in rows)} of {len(rows)} runs" if found else "NOT caught"))
        log(f"  self-test, {what}: {found} differences found")

    caught("planted: the trend read from the D1 / H4 / H1 candle still forming", check_trend(df, cuts, bias_fn=leaky_bias))
    caught("planted: every zone known one candle early", check_zones(df, cuts, zones_fn=leaky_zones))
    real, strategy.atr = strategy.atr, leaky_atr
    try:
        s = Settings()
        ref = run_raw(df, s)
        ev = decision_events(ref, df)
        picks = []
        for what in ("sniper order", "momentum order"):
            g = ev[(ev["what"] == what) & (df.index[ev["bar"].clip(upper=len(df) - 1)] < pd.Timestamp("2024-05-25"))]
            picks += [(what, int(b)) for b in g["bar"].to_numpy()[np.sort(rng.choice(len(g), min(2, len(g)), replace=False))]]
        caught("planted: the bot's stops use the ATR of the next candle (M1 and M5)", check_replay(ref, df, s, picks, log))
    finally:
        strategy.atr = real
    return out


# ----------------------------------------------------------------------------- the report
def write_md(rows, path, took, span):
    R = pd.DataFrame(rows)
    lines = ["# Leak check", "",
             f"Prices: data/XAUUSD_1m.csv, {span}. Run with `python tools/leak_check.py` ({took / 60:.0f} minutes). "
             "Every test passes only with zero differences; the method is in the docstring of `tools/leak_check.py`.", "",
             "| test | runs | things compared | differences | result |", "|---|---|---|---|---|"]
    for test, g in R[R["test"] != "self-test (planted leaks)"].groupby("test", sort=False):
        lines.append(f"| {test} | {len(g)} | {g['compared'].sum():,} | {g['mismatches'].sum()} | "
                     f"{'PASS' if (g['result'] == 'PASS').all() else 'FAIL'} |")
    st = R[R["test"] == "self-test (planted leaks)"]
    if len(st):
        lines += ["", "**Self-test.** A check that can't fail proves nothing, so one leak is planted per test (on the "
                  "first 5 months) and the test must find it:", "",
                  "| planted leak | differences found | result |", "|---|---|---|"]
        lines += [f"| {r.what.replace('planted: ', '')} | {r.mismatches:,} ({r.detail}) | {r.result} |" for r in st.itertuples()]
        R = R[R["test"] != "self-test (planted leaks)"]
    lines += ["", "## Every run", "", "| test | cut | what | compared | differences | detail |", "|---|---|---|---|---|---|"]
    for r in R.itertuples():
        cut = "" if pd.isna(r.cut) else f"{pd.Timestamp(r.cut):%Y-%m-%d %H:%M}"
        lines.append(f"| {r.test} | {cut} | {r.what} | {r.compared:,} | {r.mismatches} | {r.detail} |")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def run(quick=False, with_self_test=True, settings=None, log=print):
    """All four checks (and the self-test). Returns (rows, the full run's raw outputs, df): the full run is
    the backtest itself, so tools/backtest_report.py reuses it."""
    t0 = time.time()
    s = settings or Settings()
    rng = np.random.default_rng(20261027)
    rows, df = check_data()
    if with_self_test:
        log("self-test: planting leaks")
        rows += self_test(log)
    if quick:
        df = df[df.index < pd.Timestamp("2024-06-01")]
    log(f"data: {len(df):,} candles {df.index[0]} -> {df.index[-1]}")
    end = df.index[-1]
    span = pd.Timestamp("2024-02-01"), end - pd.Timedelta("2D")
    inside = df.index[(df.index >= span[0]) & (df.index < span[1])]
    n_poison = 4 if quick else 12
    cuts = sorted(inside[np.sort(rng.choice(len(inside), n_poison, replace=False))])
    for t in ("2024-03-12 12:00", "2024-05-07 00:00") if quick else ("2024-06-12 12:00", "2025-02-04 00:00"):
        cuts.append(df.index[df.index.searchsorted(pd.Timestamp(t))])          # on a whole H4 / D1 candle
    cuts = sorted(cuts)
    log(f"trend: {len(cuts)} cuts")
    rows += check_trend(df, cuts)
    log(f"zones: {len(cuts)} cuts")
    rows += check_zones(df, cuts)
    pause_cuts = cuts[:: max(len(cuts) // 4, 1)][:4]
    log(f"pause: {len(pause_cuts)} cuts")
    rows += check_pause(df, pause_cuts)
    log("the full run")
    t1 = time.time()
    ref = run_raw(df, s)
    log(f"  {len(ref['sniper'])} sniper trades, {len(ref['momentum'])} momentum orders, {time.time() - t1:.0f}s")
    ev = decision_events(ref, df)
    late = () if quick else ((pd.Timestamp("2024-09-01"), pd.Timestamp("2025-02-01")),
                             (pd.Timestamp("2025-03-01"), pd.Timestamp("2025-08-01")),
                             (pd.Timestamp("2025-08-01"), end))
    early_end = pd.Timestamp("2024-05-01") if quick else pd.Timestamp("2024-06-15")
    replay_cuts = pick_cuts(ev, df, early_end, late, rng)
    log(f"replays: {len(replay_cuts)}")
    rows += check_replay(ref, df, s, replay_cuts, log)
    took = time.time() - t0
    os.makedirs(OUT, exist_ok=True)
    pd.DataFrame(rows).to_csv(os.path.join(OUT, "leak_check.csv"), index=False)
    write_md(rows, os.path.join(OUT, "leak_check.md"), took, f"{df.index[0]:%Y-%m-%d} -> {df.index[-1]:%Y-%m-%d}")
    return rows, ref, df


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--quick", action="store_true", help="the first 5 months, fewer cuts, no self-test")
    p.add_argument("--self-test-only", action="store_true", help="only plant the leaks and check each is caught")
    args = p.parse_args()
    low_priority()
    if args.self_test_only:
        R = pd.DataFrame(self_test())
        print(R[["what", "mismatches", "result"]].to_string(index=False))
        return
    rows, _, _ = run(quick=args.quick, with_self_test=not args.quick)
    R = pd.DataFrame(rows)
    print(R.groupby("test", sort=False).agg(runs=("result", "size"), compared=("compared", "sum"),
                                            differences=("mismatches", "sum")).to_string())
    print("ALL PASS" if (R["result"] == "PASS").all() else "FAILED: see reports/backtest/leak_check.md")


if __name__ == "__main__":
    main()
