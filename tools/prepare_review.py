"""
REVIEW CASES: the bot's trades as one-tap questions for you, in one HTML page.

    python tools/prepare_review.py                      # 300 cases from the latest reports/round*/bot_trades_round*.csv
    python tools/prepare_review.py --trades reports/round8/bot_trades_round8.csv --n 300 --cost 0.25
        -> reports/review/review_cases.html   (open it in a browser; Export gives review_answers.csv)

For each case you answer with one tap:
    S  skip       you wouldn't take this setup
    A  approve    you'd take it, as the bot did (its POI, its entry)
    B             the bot's POI, but the OTHER entry (momentum instead of sniper)
    1 / 2 / 3     not at this POI: wait for deeper POI 1 / 2 / 3, sniper entry there
    4 / 5 / 6     not at this POI: wait for deeper POI 1 / 2 / 3, momentum entry there
    (optional) a reason first: no HTF POI, against HTF, inside a range, weak break, chop day, too late
You choose the entry: a sniper can happen inside a range too, and you decide case by case. The entries and stops
are the bot's own rules, unchanged. The chart stops at the decision, as live; what happened next is shown only
after you answer.

Deeper POIs: live M15 / M30 / H1 / H4 order blocks and FVGs of the trade's direction (poi.py, the bot's own
zones), below the bot's POI for a long (above it for a short), nearest first, at least MIN_DEEPER_R of the bot's
risk deeper and at most --max-depth-pct away.

Every POI is replayed with BOTH entries, separately, with the bot's own code (strategy.py), one try each:
    price touches the POI (a deeper one within TOUCH_WAIT of the bot's decision), before a close beyond its far edge
    sniper:   SweepMachine on M1 (a sweep, then a close above the real swing high, within SNIPER_WINDOW of the
              touch), the trend agreeing (trend_of), place(): a limit at the M1 order block's high, the stop under
              the sweep; while it waits each new M1 break moves it to the newest order block; cancelled on a close
              beyond the stop or the POI's far edge, or SNIPER_WINDOW after the touch; target = _target(), 12R+
    momentum: as _momentum() places it: an M5 close above the last M5 swing high while an M5 pause range is on,
              the trend agreeing; a limit halfway back to the stop under the range; 10R; cancelled after
              MOMENTUM_WAIT or if the target trades first
    then walk(): stop or target. R is after --cost. Not replayed: re-tries after a stop-out.
Those results are for training and are shown only after you answer.

Cases: filled trades, LOSERS_SHARE of them stopped out (the ones it loses on teach the most), the rest winners and
open trades, in a shuffled order. --seed makes the same file again.
"""
import argparse
import glob
import json
import math
import os
import re
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import REPORTS, ROOT, load_prices  # noqa: E402
from bias import htf_bias  # noqa: E402
from poi import pois  # noqa: E402
from smcml.bias import resample  # noqa: E402
from smcml.detectors import StructureTracker, SwingTracker, atr, find_order_block, mirror  # noqa: E402
from strategy import Settings, SweepMachine, _target, last_closed, shapes, trend_of, walk  # noqa: E402

POI_TFS = ("15min", "30min", "1h", "4h")
TF_NAME = {"15min": "M15", "30min": "M30", "1h": "H1", "4h": "H4", "1D": "D1"}
LOSERS_SHARE = 0.7
MIN_DEEPER_R = 0.25          # a deeper POI's near edge is at least this many of the bot's R beyond the bot's POI
SAME_LEVEL_R = 0.2           # zones whose near edges are closer than this are one option
MAX_OPTIONS = 3
TOUCH_WAIT = "2D"            # price must reach the POI within this long
WARMUP = 300                 # candles the swing trackers see before the touch
WINDOWS = {"H4": ("30D", "5D"), "H1": ("8D", "2D"), "M15": ("48h", "18h"),   # candles before / after the decision,
           "M5": ("12h", "6h"), "M1": ("4h", "3h")}                         # per timeframe, for the charts
RULES = {"H4": "4h", "H1": "1h", "M15": "15min", "M5": "5min", "M1": None}
EQUAL_ATR = 0.2              # equal lows: other M1 swing lows within this many M1 ATRs of the setup's low ...
EQUAL_LOOKBACK = 240         # ... in the M1 candles before the decision (4 hours)
EQUAL_SWING = 3              # an M1 swing low = lowest with this many candles on each side
TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "review_template.html")


def latest_trades():
    paths = glob.glob(os.path.join(REPORTS, "round*", "bot_trades_round*.csv"))
    if not paths:
        sys.exit("no reports/round*/bot_trades_round*.csv: run tools/run_backtest.py first, or pass --trades")
    return max(paths, key=lambda p: int(re.search(r"round(\d+)\.csv$", p).group(1)))


def pick(trades, n, seed):
    t = trades[trades["fill_time"].notna() & trades["outcome"].isin(["stop", "target", "open"])]
    losers, others = t[t["outcome"] == "stop"], t[t["outcome"] != "stop"]
    k_l = min(len(losers), round(n * LOSERS_SHARE))
    k_o = min(len(others), n - k_l)
    k_l = min(len(losers), n - k_o)
    chosen = pd.concat([losers.sample(k_l, random_state=seed), others.sample(k_o, random_state=seed)])
    return chosen.sample(frac=1, random_state=seed).reset_index(drop=True)


class Rules:
    """The bot's two entries, each run on its own at one chosen POI (one try)."""

    def __init__(self, df, s, cost):
        self.df, self.s, self.cost = df, s, cost
        o, h, l, c = (df[k].to_numpy(float) for k in ("open", "high", "low", "close"))
        self.l, self.h, self.c = l, h, c
        self.times = df.index.to_numpy()
        self.closes_t = self.times + np.timedelta64(1, "m")
        self.a = atr(h, l, c, s.ATR_N)
        self.flipped = {d: mirror(o, h, l, c, d) for d in (1, -1)}
        self.trend = trend_of(htf_bias(df), s)
        self.zt = pois(df)                                         # H1 / H4 / D1: the targets
        self.touch_bars = int(pd.Timedelta(TOUCH_WAIT) / pd.Timedelta("1min"))
        self.window = int(pd.Timedelta(s.SNIPER_WINDOW) / pd.Timedelta("1min"))
        self.wait = int(pd.Timedelta(s.MOMENTUM_WAIT) / pd.Timedelta("1min"))
        tf = s.PAUSE_TFS[0]                                        # the momentum side: M5 candles and pause ranges
        self.m5 = resample(df, "5min")
        o5, h5, l5, c5 = (self.m5[k].to_numpy(float) for k in ("open", "high", "low", "close"))
        self.l5, self.h5, self.c5 = l5, h5, c5
        self.a5 = atr(h5, l5, c5, s.ATR_N)
        self.m5_close = (self.m5.index + pd.Timedelta("5min")).to_numpy()
        self.flip5 = {d: mirror(o5, h5, l5, c5, d) for d in (1, -1)}
        self.P, self.P_tf = shapes(df, tf), tf
        self.kpos = last_closed(self.P.index, tf, self.m5.index)  # last pause candle closed before each M5 candle

    @staticmethod
    def blank():
        return dict(status="", touch=None, placed=None, entry=None, stop=None, target=None, fill=None, exit=None, R=0.0)

    def both(self, i0, d, near, far):
        """From candle i0: price must reach the POI near..far; then the sniper and the momentum entry, each alone."""
        n = len(self.c)
        O, H, L, C = self.flipped[d]
        nf, ff = d * near, d * far                                 # flipped chart: every trade is a long
        end = min(i0 + self.touch_bars, n)
        hit, gone = L[i0:end] <= nf, C[i0:end] < ff
        j = int(np.argmax(hit)) if hit.any() else None
        g = int(np.argmax(gone)) if gone.any() else None
        if j is None or (g is not None and g < j):
            out = dict(self.blank(), status="never reached")
            return dict(sniper=out, momentum=dict(out))
        touch = i0 + j
        stop_at = min(touch + self.window, n)
        gone = C[touch:stop_at] < ff                               # the POI is gone at its first close beyond the far edge
        broken = touch + int(np.argmax(gone)) if gone.any() else None
        when = str(pd.Timestamp(self.times[touch]))[:16]
        sn, mo = self.sniper(d, touch, ff, stop_at), self.momentum(d, touch, broken if broken is not None else stop_at)
        sn["touch"] = mo["touch"] = when
        return dict(sniper=sn, momentum=mo)

    def _result(self, out, d, f, entry, stop, target):
        out["fill"] = str(pd.Timestamp(self.times[f]))[:16]
        x, how = walk(self.l, self.h, f, d, stop, target, f + 1)
        risk = abs(entry - stop)
        if x is None:
            price, how = self.c[-1], "open"
        else:
            price = stop if how == "stop" else target
            out["exit"] = str(pd.Timestamp(self.times[x]))[:16]
        out.update(status=how, R=float((d * (price - entry) - self.cost) / risk))
        return out

    def sniper(self, d, touch, ff, stop_at):
        """_sniper()'s chain at this POI: sweep + break, limit at the M1 order block, successive moves, fill."""
        s, out = self.s, self.blank()
        O, H, L, C = self.flipped[d]
        m = SweepMachine(O, H, L, C, self.a, s)
        for t in range(max(touch - WARMUP, 0), touch):
            m.step(t, False)
        cand, t = None, touch
        for t in range(touch, stop_at):
            if C[t] < ff:
                out["status"] = "POI broken before a setup"
                return out
            cand = m.step(t, True)
            if cand is not None:
                break
        if cand is None:
            out["status"] = "no sweep + break there"
            return out
        if self.trend[t] != d:
            out["status"] = "setup, but the trend disagrees"
            return out
        a = self.a[t]
        entry_f, stop_f = H[cand["ob_bar"]], L[cand["ext_bar"]] - s.STOP_BUFFER_ATR * a
        if not (np.isfinite(a) and entry_f - stop_f >= s.MIN_RISK_ATR * a and entry_f < C[t]):
            out["status"] = "setup, but the stop is too tight"
            return out
        placed, f = t, None
        for u in range(t + 1, stop_at):                            # the order waits, as in _sniper
            m.step(u, False)
            if L[u] <= entry_f:
                f = u
                break
            if C[u] < stop_f or C[u] < ff:
                break
            for e in m.events:                                     # a new break up: the successive order block
                if e[0] == 1:
                    kk = e[2].idx
                    leg = kk + 1 + int(np.argmin(L[kk + 1:u + 1]))
                    ob_bar = find_order_block(O, H, L, C, leg)[0]
                    ne, ns = H[ob_bar], L[leg] - s.STOP_BUFFER_ATR * self.a[u]
                    if np.isfinite(self.a[u]) and ne - ns >= s.MIN_RISK_ATR * self.a[u] and ne < C[u]:
                        entry_f, stop_f, placed = ne, ns, u
        entry, stop = d * entry_f, d * stop_f
        when = pd.Timestamp(self.closes_t[placed])
        target = float(_target(self.zt, when, entry, stop, d, s.SNIPER_MIN_R)["level"])
        out.update(placed=str(when)[:16], entry=float(entry), stop=float(stop), target=target)
        if f is None:
            out["status"] = "order not filled"
            return out
        return self._result(out, d, f, float(entry), float(stop), target)

    def momentum(self, d, t0, t1):
        """_momentum()'s order at this POI: the first M5 break of a pause range between M1 candles t0 and t1."""
        s, P, n, out = self.s, self.P, len(self.c), self.blank()
        O5, H5, L5, C5 = self.flip5[d]
        m0 = int(np.searchsorted(self.m5_close, self.closes_t[t0], side="left"))
        m1 = int(np.searchsorted(self.m5_close, self.closes_t[min(t1, n - 1)], side="right"))
        sw = SwingTracker(s.SWING_N)
        st = StructureTracker(sw)
        found = None
        for m in range(max(m0 - WARMUP, 0), m1):
            sw.update(m, H5, L5)
            up = any(e[0] == 1 for e in st.update(m, C5))
            if m < m0 or not up:
                continue
            j = int(np.searchsorted(self.closes_t, self.m5_close[m]))   # the M1 candle closing with this M5 candle
            if j >= n or self.closes_t[j] != self.m5_close[m] or self.trend[j] != d:
                continue
            k = self.kpos[m]
            if k < 0 or P["pause"].iat[k] != 1 or P["pause_dir"].iat[k] != d:
                continue
            found = (m, j, k)
            break
        if found is None:
            out["status"] = "no range break there"
            return out
        m, j, k = found
        after = int(np.searchsorted(self.m5.index, P.index[k] + pd.Timedelta(self.P_tf)))
        if d == 1:
            stop = min(P["pause_bottom"].iat[k], self.l5[after:m + 1].min(initial=np.inf)) - s.STOP_BUFFER_ATR * self.a5[m]
        else:
            stop = max(P["pause_top"].iat[k], self.h5[after:m + 1].max(initial=-np.inf)) + s.STOP_BUFFER_ATR * self.a5[m]
        trigger = self.c5[m]
        entry = trigger - s.MOMENTUM_LIMIT * (trigger - stop)
        risk = d * (entry - stop)
        if not risk > 0:
            out["status"] = "range break, but no room for a stop"
            return out
        target = entry + d * s.MOMENTUM_R * risk
        out.update(placed=str(pd.Timestamp(self.m5_close[m]))[:16], entry=float(entry), stop=float(stop), target=float(target))
        last = min(j + self.wait, n - 1)
        hit_e = (self.l[j + 1:last + 1] <= entry) if d == 1 else (self.h[j + 1:last + 1] >= entry)
        hit_t = (self.h[j + 1:last + 1] >= target) if d == 1 else (self.l[j + 1:last + 1] <= target)
        fe = int(np.argmax(hit_e)) if hit_e.any() else None
        ft = int(np.argmax(hit_t)) if hit_t.any() else None
        if fe is None or (ft is not None and ft < fe):
            out["status"] = "order not filled"
            return out
        return self._result(out, d, j + 1 + fe, float(entry), float(stop), float(target))


def candles(df, a, b, when, digits):
    w = df[(df.index >= a) & (df.index < b)]
    mins = ((w.index - when) / pd.Timedelta("1min")).astype(int)
    return dict(t=mins.tolist(), **{k: np.round(w[k].to_numpy(float), digits).tolist() for k in ("open", "high", "low", "close")})


def num(x, digits):
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return round(x, digits) if math.isfinite(x) else None


def equal_lows(rules, i0, d, stop, digits):
    """Other M1 swing lows (highs for a short) at about the setup's low: resting liquidity under the order block.
    The setup's low is the stop without its buffer; the lowest swing low near it is the setup itself, left out."""
    O, H, L, C = rules.flipped[d]
    a = rules.a[max(i0 - 1, 0)]
    ref = d * stop + rules.s.STOP_BUFFER_ATR * a                    # flipped chart: the setup's low
    n, lo = EQUAL_SWING, max(i0 - EQUAL_LOOKBACK, EQUAL_SWING)
    near = []
    for j in range(lo, i0 - n):
        if L[j] < L[j - n:j].min() and L[j] <= L[j + 1:j + n + 1].min() and abs(L[j] - ref) <= EQUAL_ATR * a:
            near.append(j)
    if near:                                                        # the setup's own low: the lowest of them
        near.remove(min(near, key=lambda j: (L[j], -j)))
    t0 = rules.times[i0]
    return dict(tol=num(EQUAL_ATR * a, digits), lows=[dict(m=int((rules.times[j] - t0) / np.timedelta64(1, "m")),
                                                          p=num(d * L[j], digits)) for j in near])


def rel(ts, when):
    """Minutes from the decision to ts (None if unknown): the charts place zone boxes with it."""
    return None if ts is None or pd.isna(ts) else int((pd.Timestamp(ts) - when) / pd.Timedelta("1min"))


def tidy(res, digits):
    out = dict(res)
    for k in ("entry", "stop", "target"):
        out[k] = num(out[k], digits)
    out["R"] = round(out["R"], 2)
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--trades", help="bot trades CSV (default: the latest reports/round*/bot_trades_round*.csv)")
    p.add_argument("--prices", help="M1 prices (default data/XAUUSD_1m.csv)")
    p.add_argument("--n", type=int, default=300, help="number of cases (default 300)")
    p.add_argument("--cost", type=float, default=0.25, help="spread + commission per trade, in price (default 0.25)")
    p.add_argument("--max-depth-pct", type=float, default=1.5, help="deeper POIs at most this %% from the bot's POI")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--out", default=os.path.join(REPORTS, "review", "review_cases.html"))
    args = p.parse_args()

    path = args.trades or latest_trades()
    trades = pd.read_csv(path)
    for c in ("decided", "fill_time", "exit_time", "poi_touch", "poi_formed", "poi_known"):
        if c in trades:
            trades[c] = pd.to_datetime(trades[c], errors="coerce")
    df = load_prices(args.prices, start=None, end=None) if args.prices else load_prices(start=None, end=None)
    cases_src = pick(trades, args.n, args.seed)
    print(f"{path}: {len(trades)} orders -> {len(cases_src)} cases "
          f"({(cases_src['outcome'] == 'stop').sum()} stopped out); prices {df.index[0]} -> {df.index[-1]}")

    s = Settings()
    rules = Rules(df, s, args.cost)
    z = pois(df, tfs=POI_TFS, swing_n=s.SWING_N)
    z = z[z["type"].str.endswith(("_ob", "_fvg"))].reset_index(drop=True)
    times = df.index.to_numpy()
    frames = {k: (df if r is None else resample(df, r)) for k, r in RULES.items()}
    digits = max(0, 5 - int(math.log10(max(float(df["close"].median()), 1))))

    cases = []
    for k, r in enumerate(cases_src.to_dict("records")):
        d = 1 if r["dir"] == "long" else -1
        when = r["decided"]
        i0 = int(np.searchsorted(times, when.to_datetime64()))        # first candle after the decision
        if i0 >= len(df):
            continue
        entry, stop, target = float(r["entry"]), float(r["stop"]), float(r["target"])
        risk = abs(entry - stop)
        has_poi = pd.notna(r.get("poi_top")) and pd.notna(r.get("poi_bottom"))
        # B: the bot's own POI with the other entry (a sniper trade has a POI; a momentum trade has none)
        alt = None
        if r.get("type") == "sniper" and has_poi and pd.notna(r.get("poi_touch")) and pd.notna(r.get("hl")):
            near0 = r["poi_top"] if d == 1 else r["poi_bottom"]
            it = int(np.searchsorted(times, (r["poi_touch"] - pd.Timedelta("1min")).to_datetime64()))
            alt = tidy(rules.both(it, d, near0, r["hl"])["momentum"], digits)
        # 1 / 2 / 3: deeper POIs, both entries at each
        ref = (r["poi_top"] if d == 1 else r["poi_bottom"]) if has_poi else entry   # the bot's POI near edge
        live = z[(z["known"] <= when) & ~(z["used"] <= when) & (z["dir"] == d)]
        near = live["top"] if d == 1 else live["bottom"]
        far = live["bottom"] if d == 1 else live["top"]
        deeper = d * (ref - near)
        ok = (deeper >= MIN_DEEPER_R * risk) & (d * (entry - near) > 0) & (deeper <= args.max_depth_pct / 100 * entry)
        if has_poi:                                                    # not the bot's own POI again
            ok &= ~((live["top"] - r["poi_top"]).abs().lt(1e-9) & (live["bottom"] - r["poi_bottom"]).abs().lt(1e-9))
        cand = live[ok].assign(near=near[ok], far=far[ok], deeper=deeper[ok]).sort_values("deeper")
        options, levels = [], []
        for c in cand.itertuples(index=False):
            if any(abs(c.near - v) < SAME_LEVEL_R * risk for v in levels):
                continue                                              # the same level as a nearer option
            levels.append(c.near)
            res = rules.both(i0, d, c.near, c.far)
            options.append(dict(tf=TF_NAME.get(c.tf, c.tf), kind=c.type.split("_")[1].upper(),
                                top=num(c.top, digits), bottom=num(c.bottom, digits), formed=str(c.formed)[:16],
                                formed_min=rel(c.formed, when), known_min=rel(c.known, when), used_min=rel(c.used, when),
                                deeper_R=round(float(c.deeper / risk), 2),
                                sniper=tidy(res["sniper"], digits), momentum=tidy(res["momentum"], digits)))
            if len(options) == MAX_OPTIONS:
                break
        tf_m = re.search(r"\b(15min|30min|1h|4h)\b", str(r.get("rule", "")))
        cases.append(dict(
            case=k + 1, bot_id=int(r["id"]), decided=str(when)[:16], dir=r["dir"], type=r.get("type", ""),
            order=r.get("order", ""), rule=str(r.get("rule", "")), shot=num(r.get("shot"), 0),
            entry=num(entry, digits), stop=num(stop, digits), target=num(target, digits), risk=num(risk, digits),
            rr=num(abs(target - entry) / risk, 1), atr=num(rules.a[max(i0 - 1, 0)], digits),
            poi=dict(top=num(r["poi_top"], digits), bottom=num(r["poi_bottom"], digits),
                     tf=TF_NAME.get(tf_m.group(1), "") if tf_m else "", formed=str(r.get("poi_formed"))[:16],
                     formed_min=rel(r.get("poi_formed"), when), known_min=rel(r.get("poi_known"), when),
                     touch_min=rel(r.get("poi_touch"), when)) if has_poi else None,
            pause=dict(top=num(r.get("pause_top"), digits), bottom=num(r.get("pause_bottom"), digits))
            if pd.notna(r.get("pause_top")) else None,
            swept=num(r.get("swept"), digits),
            bot=dict(outcome=r["outcome"], R=round(float(r["R"]), 2), R_after_cost=round(float(r["R"]) - args.cost / risk, 2),
                     fill=str(r["fill_time"])[:16], exit=str(r.get("exit_time"))[:16]),
            alt=alt, options=options, eq=equal_lows(rules, i0, d, stop, digits),
            bars={k: candles(frames[k], when - pd.Timedelta(a), when + pd.Timedelta(b), when, digits)
                  for k, (a, b) in WINDOWS.items()}))
        if (k + 1) % 50 == 0:
            print(f"  {k + 1} cases")

    meta = dict(source=os.path.relpath(path, ROOT), made=str(pd.Timestamp.now())[:16], cost=args.cost, n=len(cases),
                digits=digits, key=f"review-v3-{os.path.basename(path)}-{args.seed}-{len(cases)}")
    page = open(TEMPLATE, encoding="utf-8").read()
    page = page.replace("/*__CASES__*/", json.dumps(cases, separators=(",", ":"))).replace("/*__META__*/", json.dumps(meta))
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(page)
    traded = ("stop", "target", "open")
    opts = [o for c in cases for o in c["options"]]
    print(f"equal lows at the setup: {sum(1 for c in cases if c['eq']['lows'])} of {len(cases)} cases")
    print(f"saved {args.out}: {len(cases)} cases, {len(opts)} deeper POIs; would have traded there: "
          f"sniper {sum(o['sniper']['status'] in traded for o in opts)}, momentum {sum(o['momentum']['status'] in traded for o in opts)}; "
          f"B (bot's POI, momentum) traded in {sum(1 for c in cases if c['alt'] and c['alt']['status'] in traded)} cases; "
          f"{len(page) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
