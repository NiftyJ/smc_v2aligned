"""
THE BACKTEST REPORT: the bot on all of data/XAUUSD_1m.csv, checked for leaks first, in one PDF.

    python tools/backtest_report.py --compare "live code=<folder>[=what it is]" [--compare ...]
                                                   -> reports/backtest/backtest_report.pdf   (about 35 minutes)
    python tools/backtest_report.py --from-saved   -> the PDF again from the saved results (a minute)
    python tools/backtest_report.py --quick        -> the first 5 months only, to try it out

1. tools/leak_check.py: the data, the trend, the zones, the pause ranges and the whole bot replayed (see
   there). Its full run IS the backtest, so the bot runs once.
2. Every order and trade of that run (bot_orders_all.csv), results per period, after costs, by setup,
   by month; the trades again with buys filled on the ask (the file has bid prices); stops that gapped.
3. Optional: other versions of the bot (each a folder with its own strategy.py, e.g. the live code) on the
   same prices, each in its own process; nothing is written into those folders (python -B). The first
   is drawn beside this one; all are in a table.

Writes into reports/backtest/: backtest_report.pdf, backtest_report.md, bot_orders_all.csv,
compare_<n>.csv, leak_check.md / .csv, meta.json. R is per trade, before costs unless a cost is named.
Account limits: the backtest has none (every signal is taken, overlapping trades too), like strategy.py.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import leak_check  # noqa: E402
from common import PERIODS, PRICES, ROOT, load_prices, low_priority, orders_table  # noqa: E402
from strategy import Settings, walk  # noqa: E402

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402
from matplotlib.font_manager import FontProperties, findfont  # noqa: E402
from matplotlib.textpath import TextToPath  # noqa: E402

OUT = os.path.join(ROOT, "reports", "backtest")
SEGMENTS = [("development", *PERIODS["dev"], "the 5 alignment changes were chosen on this period"),
            ("holdout", *PERIODS["holdout"], "label matching checked once, at the end"),
            ("late", *PERIODS["late"], "label matching checked once; its profit was never looked at"),
            ("after the labels", PERIODS["late"][1], None, "never used for anything: the clean test")]
COSTS = (0.0, 0.10, 0.20, 0.30)              # $ per trade (spread + commission), taken off each trade's R
SPREADS = (0.20, 0.30)                       # $ between bid and ask, for the bid / ask fill model
SESSIONS = [("Asia 22-07", 22, 7), ("London 07-12", 7, 12), ("New York 12-17", 12, 17), ("17-22", 17, 22)]
CODE = ("strategy.py", "poi.py", "bias.py", "range_types.py", "smcml/bias.py", "smcml/detectors.py")

# ---- look (dataviz reference palette; series pair and cost ramp validated on white)
INK, INK2, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#ffffff"
BOT, OTHER = "#2a78d6", "#eb6834"                       # categorical slots 1, 2
RAMP = ("#86b6ef", "#3987e5", "#1c5cab", "#0d366b")     # ordinal blue: more cost = darker
GOOD, CRITICAL, BAND = "#0ca30c", "#d03b3b", "#f4f3ef"
W, H, M = 8.27, 11.69, 0.7                              # A4 portrait, margin (inches)


def _font():
    for name in ("Segoe UI", "DejaVu Sans"):
        try:
            findfont(name, fallback_to_default=False)
            return name
        except ValueError:
            continue
    return "DejaVu Sans"


FONT = _font()
plt.rcParams.update({"font.family": FONT, "pdf.fonttype": 42, "font.size": 8, "text.color": INK,
                     "axes.edgecolor": AXIS, "axes.linewidth": 0.6, "xtick.color": INK2, "ytick.color": INK2,
                     "xtick.major.width": 0.6, "ytick.major.width": 0.6, "xtick.major.size": 2.5,
                     "ytick.major.size": 0, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
                     "savefig.facecolor": SURFACE, "text.parse_math": False})
_TTP = TextToPath()


# ============================================================================= the numbers
def fingerprint(root=ROOT):
    h = hashlib.sha1()
    for f in CODE:
        if os.path.exists(os.path.join(root, f)):
            with open(os.path.join(root, f), "rb") as fh:
                h.update(fh.read())
    return h.hexdigest()[:10]


def n_of(n, one, many=None):
    return f"{n} {one if n == 1 else (many or one + 's')}"


def run_other(code_dir, df):
    """Another version of the bot (code_dir/strategy.py) on the same prices, in its own process; python -B
    writes no __pycache__ into that folder. Returns its backtest() table (filled trades + momentum orders)."""
    tmp = tempfile.mkdtemp(prefix="smc_compare_")
    try:
        prices, out = os.path.join(tmp, "prices.pkl"), os.path.join(tmp, "trades.pkl")
        df.to_pickle(prices)
        code = ("import sys, pandas as pd; sys.path.insert(0, sys.argv[1]); from strategy import backtest; "
                "backtest(pd.read_pickle(sys.argv[2])).to_pickle(sys.argv[3])")
        subprocess.run([sys.executable, "-B", "-c", code, os.path.abspath(code_dir), prices, out], check=True, cwd=tmp)
        return pd.read_pickle(out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def filled_of(t):
    """Filled trades, with the columns used here, from either bot_orders_all.csv or a backtest() table."""
    if "fill_time" in t:
        f = t[t["fill_time"].notna()].copy()
    else:
        f = t[t["filled"].notna()].rename(columns={"filled": "fill_time", "placed": "decided"}).copy()
    return f.sort_values("exit_time", kind="stable").reset_index(drop=True)


def stats(f, cost=0.0, weeks=None):
    """Filled trades -> trades, a week, win rate, mean R, total R, max drawdown, profit factor, longest run of
    losers, median stop ($). cost: $ per trade taken off each trade (R - cost / risk). Equity in exit order."""
    if not len(f):
        return dict(trades=0, per_week=0.0, win_rate=np.nan, mean_R=np.nan, total_R=0.0, max_dd=0.0, pf=np.nan,
                    streak=0, median_risk=np.nan, open=0, wins=0)
    R = (f["R"] - cost / f["risk"]).to_numpy(float)
    eq = np.r_[0.0, np.cumsum(R)]
    dd = float((np.maximum.accumulate(eq) - eq).max())
    streak = run = 0
    for r in R:
        run = run + 1 if r < 0 else 0
        streak = max(streak, run)
    closed = f["outcome"].isin(["target", "stop"]).to_numpy()
    wins = int((f["outcome"] == "target").sum())
    loss = -R[R < 0].sum()
    return dict(trades=len(f), per_week=len(f) / weeks if weeks else np.nan, win_rate=wins / max(closed.sum(), 1),
                mean_R=R.mean(), total_R=R.sum(), max_dd=dd, pf=R[R > 0].sum() / loss if loss > 0 else np.inf,
                streak=streak, median_risk=float(f["risk"].median()), open=int((f["outcome"] == "open").sum()), wins=wins)


def segments(f, end):
    """(name, start, end, note, trades decided in it, weeks) for each period, then all of it."""
    out = []
    for name, a, b, note in SEGMENTS:
        b = b if b is not None else end
        out.append((name, a, b, note, f[(f["decided"] >= a) & (f["decided"] < b)], (b - a) / pd.Timedelta("7D")))
    return out


def with_spread(f, df, spread):
    """Each filled trade again with buys on the ask (bid + spread); the file has BID prices. A buy limit (a
    long's entry, a short's target) needs the bid `spread` below its price; a buy stop (a short's stop)
    fires once the bid is `spread` below it. Sells are as backtested. From the backtest's fill candle, with
    strategy.walk() (stop first on a tie, no target on the fill candle). A long whose bid never got `spread`
    under the entry before its exit never fills (R 0). R per trade, nothing else taken off."""
    t, base = df.index, pd.Timedelta("1min")
    lo, hi = df["low"].to_numpy(float), df["high"].to_numpy(float)
    last = float(df["close"].iloc[-1])
    out = np.zeros(len(f))
    for i, r in enumerate(f.itertuples()):
        a = int(t.searchsorted(r.fill_time))
        x = int(t.searchsorted(r.exit_time - base)) if r.outcome != "open" else len(t) - 1
        d, e, s, g, risk = int(r.direction), r.entry, r.stop, r.target, r.risk
        if d == 1:
            hit = np.flatnonzero(lo[a:x + 1] <= e - spread)
            if not len(hit):
                continue
            j = a + int(hit[0])
            k, outcome = walk(lo, hi, j, 1, s, g, j + 1)
            exit_ = {"stop": s, "target": g}.get(outcome, last)
        else:
            k, outcome = walk(lo, hi, a, -1, s - spread, g - spread, a + 1)
            exit_ = {"stop": s, "target": g}.get(outcome, last + spread)
        out[i] = d * (exit_ - e) / risk
    return out


def stop_gaps(f, df):
    """Stopped trades whose exit candle OPENED beyond the stop (not the fill candle): the backtest exits at
    the stop, a real stop order near that open. Returns (count, R lost beyond -1R in total, the worst)."""
    t, base = df.index, pd.Timedelta("1min")
    op = df["open"].to_numpy(float)
    extra, worst, n = 0.0, 0.0, 0
    for r in f[f["outcome"] == "stop"].itertuples():
        x = int(t.searchsorted(r.exit_time - base))
        if x == int(t.searchsorted(r.fill_time)):
            continue
        d = int(r.direction)
        if (op[x] - r.stop) * d < 0:
            real = d * (op[x] - r.entry) / r.risk
            n, extra, worst = n + 1, extra + (real + 1), min(worst, real)
    return n, extra, worst


def touch_wins(f, df, spread):
    """Long winners whose bid never went `spread` below the entry before the target: on the ask they would
    not have filled. (count, their R)."""
    t, base = df.index, pd.Timedelta("1min")
    lo = df["low"].to_numpy(float)
    n, R = 0, 0.0
    for r in f[(f["outcome"] == "target") & (f["direction"] == 1)].itertuples():
        a, x = int(t.searchsorted(r.fill_time)), int(t.searchsorted(r.exit_time - base))
        if lo[a:x + 1].min() > r.entry - spread:
            n, R = n + 1, R + r.R
    return n, R


def setup_of(f):
    sniper = f["type"] == "sniper"
    shot = f["shot"].fillna(1).astype(int) if "shot" in f else pd.Series(1, index=f.index)
    return np.where(~sniper, "momentum", np.where(shot > 1, "sniper, re-try after a stop", "sniper, first try"))


def poi_tf_of(f):
    tf = f["rule"].astype(str).str.split(" | ", regex=False).str[1].str.split(" ").str[0]
    return np.where(f["type"] == "sniper", tf.map({"15min": "M15", "30min": "M30", "1h": "H1"}).fillna(tf), "momentum")


def session_of(times):
    h = pd.DatetimeIndex(times).hour
    out = np.full(len(h), "", dtype=object)
    for name, a, b in SESSIONS:
        out[((h >= a) & (h < b)) if a < b else ((h >= a) | (h < b))] = name
    return out


def compute(quick, compares, log=print):
    """Steps 1 and 3: the leak check (and with it the backtest) and the other versions; saves everything.
    compares: [(name, folder) or (name, folder, what it is)]."""
    os.makedirs(OUT, exist_ok=True)
    rows, ref, df = leak_check.run(quick=quick, with_self_test=not quick, log=log)
    s = Settings()
    tr = pd.concat([ref["sniper"], ref["momentum"]], ignore_index=True)
    tr = tr.sort_values(["placed", "type"], kind="stable").reset_index(drop=True)
    orders = orders_table(tr, ref["journal"], s)
    orders.to_csv(os.path.join(OUT, "bot_orders_all.csv"), index=False)
    others = []
    for i, (name, folder, *what) in enumerate(compares):
        log(f"another version: {name} ({folder})")
        t0 = time.time()
        o = run_other(folder, df)
        fn = f"compare_{i + 1}.csv"
        o.to_csv(os.path.join(OUT, fn), index=False)
        others.append(dict(name=name, dir=folder, what=what[0] if what else "", code=fingerprint(folder), file=fn,
                           trades=o))
        log(f"  {o['filled'].notna().sum()} filled, {time.time() - t0:.0f}s")
    meta = dict(compare=[{k: o[k] for k in ("name", "dir", "what", "code", "file")} for o in others], code=fingerprint(),
                quick=quick,
                made=pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"), first=str(df.index[0]), last=str(df.index[-1]))
    with open(os.path.join(OUT, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1)
    return df, orders, others, pd.DataFrame(rows), meta


def load_saved():
    with open(os.path.join(OUT, "meta.json"), encoding="utf-8") as fh:
        meta = json.load(fh)
    dates = ["decided", "fill_time", "exit_time", "first_placed", "poi_formed", "poi_known", "poi_touch",
             "sweep_time", "first_bos", "m1_ob_time", "pause_start"]
    orders = pd.read_csv(os.path.join(OUT, "bot_orders_all.csv"))
    for c in dates:
        if c in orders:
            orders[c] = pd.to_datetime(orders[c])
    others = []
    for c in meta.get("compare", []):
        o = pd.read_csv(os.path.join(OUT, c["file"]))
        for k in ("placed", "filled", "exit_time"):
            o[k] = pd.to_datetime(o[k])
        others.append(dict(c, trades=o))
    leak = pd.read_csv(os.path.join(OUT, "leak_check.csv"))
    leak["cut"] = pd.to_datetime(leak["cut"])
    df = load_prices(start=None, end=pd.Timestamp(meta["last"]) + pd.Timedelta("1min"))
    return df, orders, others, leak, meta


# ============================================================================= the page
def text_width(s, size, weight="normal"):
    w, _, _ = _TTP.get_text_width_height_descent(s, FontProperties(family=FONT, size=size, weight=weight), ismath=False)
    return w / 72.0


def wrap(s, size, width, weight="normal"):
    lines, cur = [], ""
    for word in s.split(" "):
        trial = f"{cur} {word}" if cur else word
        if cur and text_width(trial, size, weight) > width:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    return lines + [cur]


class Page:
    """One A4 page, filled top to bottom from a cursor (inches from the top edge)."""

    def __init__(self, doc, title):
        self.doc, self.fig, self.y = doc, plt.figure(figsize=(W, H)), M
        doc.n += 1
        self.fig.text(M / W, 0.35 / H, title, fontsize=7, color=MUTED)
        self.fig.text(1 - M / W, 0.35 / H, str(doc.n), fontsize=7, color=MUTED, ha="right")

    def fy(self, y):
        return 1 - y / H

    def text(self, s, size=9, weight="normal", color=INK, indent=0.0, gap=0.07, width=None):
        width = width or W - 2 * M - indent
        lines = wrap(s, size, width, weight)
        self.fig.text((M + indent) / W, self.fy(self.y), "\n".join(lines), fontsize=size, fontweight=weight,
                      color=color, va="top", linespacing=1.32)
        self.y += len(lines) * size * 1.32 / 72 + gap

    def h1(self, s):
        self.text(s, 17, "bold", gap=0.06)

    def h2(self, s):
        self.y += 0.1
        self.text(s, 11.5, "bold", gap=0.05)

    def bullets(self, items, size=9, gap=0.045):
        for it in items:
            self.fig.text((M + 0.05) / W, self.fy(self.y), "•", fontsize=size, color=INK2, va="top")
            self.text(it, size, indent=0.22, gap=gap)
        self.y += 0.04

    def table(self, cols, rows, widths, align=None, size=8, status_col=None, bold_first=False, gap=0.12, groups=None):
        """rows: lists of strings (\\n for a second line). align: 'l' / 'r' per column. status_col: the column
        whose PASS / FAIL gets a status dot beside it. groups: [(label, first column, last column)], a label
        above those columns' heads."""
        align = align or ["l"] + ["r"] * (len(cols) - 1)
        x = np.r_[0, np.cumsum(widths)] + M
        lh = size * 1.3 / 72
        pad = 0.05
        if groups:
            for label, c0, c1 in groups:
                self.fig.text((x[c0] + x[c1 + 1]) / 2 / W, self.fy(self.y + 0.035), label, fontsize=size,
                              fontweight="bold", color=INK2, va="top", ha="center")
            self.y += lh + 0.06
            for label, c0, c1 in groups:
                self.rule(x[c0] + pad, x[c1 + 1] - pad, AXIS)
            self.y += 0.01

        def line(cells, weight, color):
            n = max(str(c).count("\n") + 1 for c in cells)
            for i, c in enumerate(cells):
                c = str(c)
                left = x[i] + pad + (0.13 if i == status_col and c in ("PASS", "FAIL") else 0)
                xx = left if align[i] == "l" else x[i + 1] - pad
                w = weight if not (bold_first and i == 0) else "bold"
                self.fig.text(xx / W, self.fy(self.y + 0.035), c, fontsize=size, fontweight=w, color=color,
                              va="top", ha="left" if align[i] == "l" else "right", linespacing=1.3)
                if i == status_col and c in ("PASS", "FAIL"):
                    self.fig.patches.append(plt.Circle(((x[i] + pad + 0.045) / W, self.fy(self.y + 0.035 + lh * 0.42)),
                                                       0.032 / W, transform=self.fig.transFigure,
                                                       color=GOOD if c == "PASS" else CRITICAL))
            self.y += n * lh + 0.07

        line(cols, "bold", INK2)
        self.rule(x[0], x[-1], AXIS)
        for r in rows:
            line(r, "normal", INK)
            self.rule(x[0], x[-1], GRID)
        self.y += gap

    def rule(self, x0, x1, color):
        self.fig.add_artist(plt.Line2D([x0 / W, x1 / W], [self.fy(self.y)] * 2, color=color, lw=0.6,
                                       transform=self.fig.transFigure))

    def axes(self, height, left=0.55, right=0.75):
        ax = self.fig.add_axes([(M + left) / W, self.fy(self.y + height), (W - 2 * M - left - right) / W, height / H])
        self.y += height + 0.32
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        ax.grid(axis="y", color=GRID, lw=0.6)
        ax.set_axisbelow(True)
        ax.tick_params(labelsize=7.5)
        return ax

    def done(self):
        if self.y > H - 0.55:
            print(f"WARNING: page {self.doc.n} runs {self.y - (H - 0.55):.2f} in into the footer")
        self.doc.pdf.savefig(self.fig)
        if self.doc.png:
            self.fig.savefig(os.path.join(self.doc.png, f"page{self.doc.n}.png"), dpi=80)
        plt.close(self.fig)


class Doc:
    def __init__(self, path, png=None):
        self.pdf, self.n, self.png = PdfPages(path), 0, png

    def close(self):
        d = self.pdf.infodict()
        d["Title"], d["Author"] = "smc_v2 aligned: backtest on XAUUSD M1", "smc_v2_align tools/backtest_report.py"
        self.pdf.close()


# ============================================================================= the charts
def period_bands(ax, segs, top_label=True):
    for i, (name, a, b, *_rest) in enumerate(segs):
        if i % 2 == 0:
            ax.axvspan(a, b, color=BAND, lw=0, zorder=0)
        if top_label:
            ax.text(a + (b - a) / 2, 1.0, name, transform=ax.get_xaxis_transform(), ha="center", va="bottom",
                    fontsize=7, color=MUTED)


def date_axis(ax):
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=(1, 4, 7, 10)))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))


def steps(f, cost=0.0):
    R = (f["R"] - cost / f["risk"]).to_numpy(float)
    t = pd.DatetimeIndex(f["exit_time"])
    return t, np.cumsum(R)


def end_labels(ax, items, gap=9.5):
    """Direct labels at the ends of lines, [(t, y, text)], spread at least `gap` points apart around their lines.
    Call after everything is drawn and the limits are set."""
    lo, hi = ax.get_ylim()
    per = (hi - lo) / (ax.get_position().height * ax.figure.get_figheight() * 72)     # R per point
    order = sorted(range(len(items)), key=lambda i: items[i][1])
    ys = [items[i][1] for i in order]
    for k in range(1, len(ys)):
        ys[k] = max(ys[k], ys[k - 1] + gap * per)
    shift = np.mean([items[i][1] for i in order]) - np.mean(ys)
    for k, i in enumerate(order):
        t, y, s = items[i]
        ax.annotate(s, xy=(t, y), xytext=(5, (ys[k] + shift - y) / per), textcoords="offset points", fontsize=7.5,
                    color=INK2, va="center", annotation_clip=False)


# ============================================================================= the report
def fmt_r(x):
    return "" if pd.isna(x) else f"{x:+.1f}R"


def versions_rows(f, others, segs, end, weeks_all):
    """One row per version: trades, total R, after the labels, max DD, after $0.20 (all before costs but the last)."""
    rows = []
    for nm, t in [("aligned (this code)", f)] + [(o["name"], filled_of(o["trades"])) for o in others]:
        a = stats(t, 0, weeks_all)
        after = t[t["decided"] >= segs[-1][1]]
        rows.append([nm, a["trades"], fmt_r(a["total_R"]), fmt_r(after["R"].sum()), f"{a['max_dd']:.1f}R",
                     fmt_r(stats(t, 0.20, weeks_all)["total_R"])])
    return rows


def build(df, orders, others, leak, meta, pdf_path, png=None):
    f = filled_of(orders)
    f["setup"], f["poi_tf"], f["session"] = setup_of(f), poi_tf_of(f), session_of(f["decided"])
    main = others[0] if others else None
    g = filled_of(main["trades"]) if main else None
    name = main["name"] if main else "comparison"
    end = df.index[-1] + pd.Timedelta("1min")
    segs = segments(f, end)
    segs_o = segments(g, end) if g is not None else None
    start = df.index[0]
    weeks_all = (end - start) / pd.Timedelta("7D")
    allst = stats(f, 0, weeks_all)
    spread_R = {sp: with_spread(f, df, sp) for sp in SPREADS}
    gaps = stop_gaps(f, df)
    touch = {sp: touch_wins(f, df, sp) for sp in SPREADS}
    after = segs[-1]
    after_st = stats(after[4], 0, after[5])
    lk = leak[leak["test"] != "self-test (planted leaks)"]
    st = leak[leak["test"] == "self-test (planted leaks)"]
    leak_ok = (lk["result"] == "PASS").all()
    self_ok = len(st) > 0 and (st["result"] == "PASS").all()
    doc = Doc(pdf_path, png)
    foot = f"smc_v2 aligned backtest, XAUUSD M1 {start:%Y-%m-%d} to {df.index[-1]:%Y-%m-%d}, code {meta['code']}"

    # ------------------------------------------------------------------ page 1: the summary
    p = Page(doc, foot)
    p.h1("smc_v2 aligned: backtest on XAUUSD M1")
    p.text(f"Dukascopy M1 bid prices, {start:%d %b %Y} to {df.index[-1]:%d %b %Y} (UTC), {len(df):,} candles. "
           f"The bot in smc_v2_align (code {meta['code']}) with its own settings; made {meta['made']}."
           + (" QUICK RUN: the first 5 months only." if meta.get("quick") else ""), 8.5, color=INK2, gap=0.12)
    p.h2("In short")
    cost20 = stats(f, 0.20, weeks_all)["total_R"]
    items = [
        (f"Leak check: {'passed' if leak_ok else 'FAILED'}. {len(lk)} runs of 5 kinds of test, "
         f"{lk['compared'].sum():,} things compared, {lk['mismatches'].sum()} differences. "
         + ("The self-test's planted leaks were all caught, so the tests can fail." if self_ok else
            "The self-test did not run or missed a planted leak.")),
        ("Its first run found one look-ahead in the bot: the sniper's re-try after a stop-out (page 2). It is fixed "
         "in this code and every number here is after the fix. The live code has the same look-ahead."),
        (f"Over the {weeks_all:.0f} weeks the bot filled {allst['trades']} trades ({allst['per_week']:.1f} a week). "
         f"{allst['wins']} reached their target ({allst['win_rate']:.1%} of the closed ones), the rest were stopped "
         f"at -1R. Total {allst['total_R']:+.1f}R before costs, largest drawdown {allst['max_dd']:.1f}R, "
         f"longest run of losers {allst['streak']}."),
        (f"After the labels ({after[1]:%d %b %Y} on, never used for anything): {after_st['trades']} trades, "
         f"{after_st['total_R']:+.1f}R before costs, {stats(after[4], 0.20, after[5])['total_R']:+.1f}R after a "
         f"$0.20 cost per trade."),
        (f"Costs decide the result. The backtest has none. Taking $0.20 off every trade leaves "
         f"{cost20:+.1f}R; $0.30 leaves {stats(f, 0.30, weeks_all)['total_R']:+.1f}R. The median stop is "
         f"${allst['median_risk']:.2f}, so $0.20 is {0.20 / allst['median_risk']:.2f}R on a typical trade."),
    ]
    if g is not None:
        gst = stats(g, 0, weeks_all)
        items.append(f"The {name} on the same prices: {gst['trades']} trades, {gst['total_R']:+.1f}R before costs, "
                     f"drawdown {gst['max_dd']:.1f}R; after the labels {stats(segs_o[-1][4], 0, segs_o[-1][5])['total_R']:+.1f}R.")
    p.bullets(items)
    p.h2("Results by period (before costs)")
    cols = ["period", "trades", "a week", "win rate", "mean R", "total R", "max DD", "after $0.20"]
    widths = [1.75, 0.6, 0.6, 0.7, 0.7, 0.8, 0.75, 0.97]
    rows = []
    for nm, a, b, note, t, wk in segs + [("all", start, end, "", f, weeks_all)]:
        x = stats(t, 0, wk)
        rows.append([f"{nm}\n{a:%d %b %Y} - {(b - pd.Timedelta('1D')):%d %b %Y}", x["trades"], f"{x['per_week']:.1f}",
                     f"{x['win_rate']:.1%}" if x["trades"] else "", f"{x['mean_R']:+.2f}" if x["trades"] else "",
                     fmt_r(x["total_R"]), f"{x['max_dd']:.1f}R", fmt_r(stats(t, 0.20, wk)["total_R"])])
    p.table(cols, rows, widths)
    p.text("A trade belongs to the period it was decided in. Win rate = targets / (targets + stops); trades still open "
           f"at the end ({allst['open']}) count at the last price. Max DD = the largest fall of the running total "
           "within the period, in R. The bot can't trade before 13 Feb 2024: its D1 trend needs about 6 weeks of "
           "candles and the file starts on 2 Jan 2024.", 7.5, color=INK2)
    p.h2("What each period was used for")
    p.table(["period", "how it was used before this backtest"], [[s_[0], s_[3]] for s_ in SEGMENTS], [1.75, 5.12],
            align=["l", "l"])
    if g is not None:
        p.h2(f"Beside the {name} (same prices, before costs)")
        rows = []
        for (nm, a, b, note, t, wk), (_, _, _, _, t2, _) in zip(segs + [("all", start, end, "", f, weeks_all)],
                                                               segs_o + [("all", start, end, "", g, weeks_all)]):
            x, y = stats(t, 0, wk), stats(t2, 0, wk)
            rows.append([nm, x["trades"], fmt_r(x["total_R"]), f"{x['max_dd']:.1f}R", y["trades"], fmt_r(y["total_R"]),
                         f"{y['max_dd']:.1f}R"])
        p.table(["period", "trades", "total R", "max DD", "trades", "total R", "max DD"], rows,
                [1.75, 0.85, 0.85, 0.85, 0.85, 0.85, 0.87], groups=[("aligned (this code)", 1, 3), (name, 4, 6)])
    p.done()

    # ------------------------------------------------------------------ page 2: the leak check
    p = Page(doc, foot)
    p.h1("Leak check")
    p.text("A leak (look-ahead) is a decision on a candle that depends on a later candle. The backtest then knows part "
           "of the future and looks better than live trading can be. Every test passes only with zero differences.",
           9, gap=0.1)
    rows = []
    for test, gg in lk.groupby("test", sort=False):
        rows.append([test, len(gg), f"{gg['compared'].sum():,}", gg["mismatches"].sum(),
                     "PASS" if (gg["result"] == "PASS").all() else "FAIL"])
    p.table(["test", "runs", "compared", "differences", "result"], rows, [3.4, 0.6, 1.1, 0.95, 0.82], status_col=4)
    p.h2("What each test does")
    p.bullets([
        "The data: time stamps are candle OPEN times in UTC, as the bot assumes. US data releases at 12:30 and "
        "13:30 UTC put their spike in the candle stamped :30, not :31. The file's two downloads agree where they "
        "overlap, and every candle is read once and is possible.",
        "The trend (D1, H4, H1) and the zones (FVGs, order blocks and swing points from M15 to D1: the sniper's POIs "
        "and the targets), and the M5 pause ranges: every price from a cut on is moved $300 up, then $300 down. "
        "Nothing known before the cut may change. A trend or zone read from a candle that has not closed would.",
        "The whole bot replayed: run again on the prices up to a cut only, as live trading would have them. Up to that "
        "cut it must have placed, moved, cancelled and filled the same orders, closed the same trades with the same "
        "R, and hold the same orders waiting at the cut. The cuts sit on candles where the full run decided something, "
        "since a look-ahead of a few candles only shows on the last candle before the cut.",
    ], 8.5)
    if len(st):
        p.h2("Self-test: the tests can fail")
        p.text("One leak is planted per test, on the first 5 months, and the test must find it.", 9, gap=0.08)
        p.table(["planted leak", "differences found", "result"],
                [[r.what.replace("planted: ", ""), f"{r.mismatches:,}", r.result] for r in st.itertuples()],
                [4.6, 1.4, 0.87], status_col=2)
    p.h2("Read in the code")
    p.bullets([
        "Trend (bias.py): each M1 candle uses the last D1 / H4 / H1 candle closed by its own close. Swing points "
        "count 10 candles after they form, when they can be known.",
        "Zones (poi.py): known at the close of the candle that confirms them (an FVG's third candle, the break of "
        "structure for an order block, 5 candles after a swing point), and followed on M1 from the next candle.",
        "The FVG size rule (round 6) measures the gap against the ATR of its middle candle, closed before the FVG is known.",
        "Orders are decided at a candle's close and can fill from the next candle. On the fill candle only the stop "
        "counts, and a candle reaching both stop and target counts as a stop.",
        "A re-try after a stop-out takes the re-try slot on the candle after the stop (since the fix below). "
        "The bot never reads your labels.",
    ], 8.5)
    p.h2("Found and fixed: the re-try after a stop-out")
    p.text("After a stop-out the sniper may try the same zone again (up to 3 tries), through one re-try slot per "
           "direction. The code filled that slot when a trade FILLED, from the trade's future result, instead of when "
           "it was stopped. A trade that was going to be stopped later therefore threw away another zone's waiting "
           "re-try at its fill, which live trading could not know yet. The replay found it: on the prices up to 11 Mar "
           "2024 20:43 the bot placed a re-try on 8 Mar 17:18 that the full run did not, because a long filled on 8 Mar "
           "14:33 was stopped only after 11 Mar. Fixed in strategy.py (the slot is taken on the candle after the stop), "
           "with a test in tests/test_strategy.py. The live code has the same logic; it was not touched.", 8.5, gap=0.1)
    if others:
        p.table(["version, same prices", "trades", "total R", "after the labels", "max DD", "after $0.20"],
                versions_rows(f, others, segs, end, weeks_all), [2.67, 0.65, 0.85, 1.05, 0.75, 0.9], size=7.5, gap=0.04)
        p.text("; ".join(f"{o['name']}: {o['what']}" for o in others if o.get("what")) or
               "The other versions are listed on the last page.", 7.5, color=INK2)
    p.text("Not leaks, but they flatter the backtest too: no costs, bid prices only, stops filled at the stop. "
           "See page 4.", 8.5, gap=0.05)
    p.done()

    # ------------------------------------------------------------------ page 3: equity and drawdown
    p = Page(doc, foot)
    p.h1("The running total")
    p.text("Cumulative R of every filled trade, in the order they closed, before costs. Shaded: the periods.",
           9, color=INK2, gap=0.15)
    ax = p.axes(3.6, right=1.15)
    period_bands(ax, [(s_[0], s_[1], s_[2]) for s_ in segs])
    t, eq = steps(f)
    ax.step(np.r_[[start], t], np.r_[0, eq], where="post", color=BOT, lw=1.5, label="aligned (this code)")
    labels = [(t[-1], eq[-1], f"aligned {eq[-1]:+.0f}R")]
    if g is not None:
        t2, eq2 = steps(g)
        ax.step(np.r_[[start], t2], np.r_[0, eq2], where="post", color=OTHER, lw=1.5, label=name)
        labels.append((t2[-1], eq2[-1], f"{name.split(',')[0]} {eq2[-1]:+.0f}R"))
    ax.axhline(0, color=AXIS, lw=0.8)
    ax.set_ylabel("R", color=INK2, fontsize=8)
    ax.set_xlim(start, end)
    date_axis(ax)
    ax.legend(loc="upper left", frameon=False, fontsize=7.5)
    end_labels(ax, labels)
    p.text("Drawdown: how far the running total is below its best so far.", 9, color=INK2, gap=0.15)
    ax = p.axes(2.4, right=1.15)
    period_bands(ax, [(s_[0], s_[1], s_[2]) for s_ in segs], top_label=False)
    for ff, color, nm in ((f, BOT, "aligned (this code)"),) + (((g, OTHER, name),) if g is not None else ()):
        t, eq = steps(ff)
        full = np.r_[0, eq]
        dd = full - np.maximum.accumulate(full)
        ax.step(np.r_[[start], t], dd, where="post", color=color, lw=1.5, label=nm)
    ax.axhline(0, color=AXIS, lw=0.8)
    ax.set_ylabel("R below the best", color=INK2, fontsize=8)
    ax.set_xlim(start, end)
    date_axis(ax)
    ax.legend(loc="lower left", frameon=False, fontsize=7.5)
    sizes = f.groupby(f["decided"].dt.to_period("Q"))["risk"].median()
    p.text("The typical stop grew with gold's price and swings: median stop per quarter " +
           ", ".join(f"{q} ${v:.2f}" for q, v in sizes.items()) + ". A fixed $ cost weighs less on later trades.",
           8, color=INK2)
    p.done()

    # ------------------------------------------------------------------ page 4: costs
    p = Page(doc, foot)
    p.h1("After costs")
    p.text("The backtest charges nothing. A real account pays the spread (and on some accounts a commission) on every "
           "trade. Taking a fixed $ amount off each trade:", 9, gap=0.15)
    ax = p.axes(3.4, right=1.15)
    period_bands(ax, [(s_[0], s_[1], s_[2]) for s_ in segs])
    labels = []
    for c, color in zip(COSTS, RAMP):
        t, eq = steps(f, c)
        lab = "no cost" if c == 0 else f"${c:.2f} a trade"
        ax.step(np.r_[[start], t], np.r_[0, eq], where="post", color=color, lw=1.5, label=lab)
        labels.append((t[-1], eq[-1], f"{lab} {eq[-1]:+.0f}R"))
    ax.axhline(0, color=AXIS, lw=0.8)
    ax.set_ylabel("R", color=INK2, fontsize=8)
    ax.set_xlim(start, end)
    date_axis(ax)
    ax.legend(loc="upper left", frameon=False, fontsize=7.5)
    end_labels(ax, labels)
    cols = ["cost", *[s_[0] for s_ in segs], "all"]
    rows = []
    for c in COSTS:
        rows.append(["none" if c == 0 else f"${c:.2f} a trade"] + [fmt_r(stats(s_[4], c, s_[5])["total_R"]) for s_ in segs]
                    + [fmt_r(stats(f, c, weeks_all)["total_R"])])
    for sp in SPREADS:
        R = pd.Series(spread_R[sp], index=f.index)
        rows.append([f"bid / ask fills,\n${sp:.2f} spread"] + [fmt_r(R[s_[4].index].sum()) for s_ in segs] + [fmt_r(R.sum())])
    p.table(cols, rows, [1.55, 1.1, 0.95, 0.95, 1.25, 1.07])
    p.text("Bid / ask fills: instead of a charge per trade, buys are filled on the ask (the bid plus the spread), "
           "so a long's limit needs the bid that far under it and a short's stop fires that much sooner. Commission, "
           "if your account has one, comes on top. Spreads on XAUUSD are often $0.10 - $0.35, wider at night and "
           "around news; check your broker's.", 7.5, color=INK2)
    p.h2("Not a leak, but it flatters the backtest")
    sp20, sp30 = spread_R[0.20].sum(), spread_R[0.30].sum()
    tw = touch[0.20]
    p.bullets([
        f"No costs: ${COSTS[2]:.2f} a trade takes the total from {allst['total_R']:+.1f}R to {cost20:+.1f}R.",
        f"Bid prices only. A buy fills on the ask, a little above the bid. Done that way, the total is {sp20:+.1f}R "
        f"with a $0.20 spread and {sp30:+.1f}R with $0.30, instead of {allst['total_R']:+.1f}R. "
        + (f"Of the long winners, {tw[0]} ({tw[1]:+.1f}R) never traded $0.20 under the entry, so on the ask "
           f"{'it' if tw[0] == 1 else 'they'} would not have filled." if tw[0] else
           "Every long winner traded $0.20 under its entry, so it would have filled on the ask too."),
        (f"Stops are filled at the stop price. {n_of(gaps[0], 'stopped trade')} opened beyond the stop (a gap); "
         f"exiting at that open would cost {abs(gaps[1]):.1f}R more in total (worst trade {gaps[2]:.1f}R)."
         if gaps[0] else "Stops are filled at the stop price. No stopped trade opened beyond its stop (a gap), so "
                         "here that costs nothing."),
        "No account limits: every signal is taken, overlapping trades too, and there is no daily or weekly loss limit.",
    ], 8.5)
    p.done()

    # ------------------------------------------------------------------ page 5: months
    p = Page(doc, foot)
    p.h1("Month by month")
    p.text("R of the trades closed in each month, before costs.", 9, color=INK2, gap=0.15)
    mon = f.groupby(f["exit_time"].dt.to_period("M"))
    m = pd.DataFrame({"trades": mon.size(), "wins": mon.apply(lambda x: int((x["outcome"] == "target").sum())),
                      "R": mon["R"].sum(), "R20": mon.apply(lambda x: (x["R"] - 0.20 / x["risk"]).sum())})
    full_months = pd.period_range(f["exit_time"].min().to_period("M"), df.index[-1].to_period("M"), freq="M")
    m = m.reindex(full_months, fill_value=0)
    ax = p.axes(2.6, left=0.55, right=0.3)
    x = np.arange(len(m))
    ax.bar(x, m["R"], width=0.55, color=BOT, lw=0)
    ax.axhline(0, color=AXIS, lw=0.8)
    for i in (int(np.argmax(m["R"].to_numpy())), int(np.argmin(m["R"].to_numpy()))):
        v = m["R"].iloc[i]
        ax.annotate(f"{v:+.0f}R", (x[i], v), xytext=(0, 3 if v >= 0 else -3), textcoords="offset points",
                    ha="center", va="bottom" if v >= 0 else "top", fontsize=7, color=INK2)
    ax.set_xticks(x)
    ax.set_xticklabels([q.strftime("%b\n%Y") if q.month == 1 or i == 0 else q.strftime("%b") for i, q in enumerate(m.index)],
                       fontsize=6.5)
    ax.set_xlim(-0.7, len(m) - 0.3)
    ax.set_ylabel("R", color=INK2, fontsize=8)
    half = (len(m) + 1) // 2
    rows = []
    for i in range(half):
        r = [m.index[i].strftime("%b %Y"), m["trades"].iloc[i], m["wins"].iloc[i], fmt_r(m["R"].iloc[i]),
             fmt_r(m["R20"].iloc[i])]
        j = i + half
        r += [""] + ([m.index[j].strftime("%b %Y"), m["trades"].iloc[j], m["wins"].iloc[j], fmt_r(m["R"].iloc[j]),
                      fmt_r(m["R20"].iloc[j])] if j < len(m) else [""] * 5)
        rows.append(r)
    head = ["month", "trades", "wins", "R", "after $0.20"]
    p.table(head + [""] + head, rows, [0.75, 0.5, 0.45, 0.7, 0.8, 0.3] + [0.75, 0.5, 0.45, 0.7, 0.8], size=7.5,
            align=["l", "r", "r", "r", "r", "l"] + ["l", "r", "r", "r", "r"])
    pos = int((m["R"] > 0).sum())
    p.text(f"{pos} of {len(m)} months ended above zero before costs, {int((m['R20'] > 0).sum())} after $0.20 a trade.",
           8.5, color=INK2)
    p.done()

    # ------------------------------------------------------------------ page 6: where the R comes from
    p = Page(doc, foot)
    p.h1("Where the result comes from")
    p.text("All filled trades, whole period, before costs and after $0.20 a trade.", 9, color=INK2, gap=0.1)
    for title, key, order in (("Setup", "setup", ["sniper, first try", "sniper, re-try after a stop", "momentum"]),
                              ("Direction", "dir", ["long", "short"]),
                              ("The sniper's POI timeframe", "poi_tf", ["M15", "M30", "H1"]),
                              ("Session (decision time, UTC)", "session", [s_[0] for s_ in SESSIONS]),
                              ("Target", "target_kind", None)):
        if key == "target_kind":
            f["target_kind"] = np.where(f["target_type"].astype(str).str.endswith("R"), "fixed (12R sniper, 10R momentum)",
                                        "the nearest H1 / H4 / D1 zone (12R+)")
            order = sorted(f["target_kind"].unique())
        rows = []
        for k in order:
            t = f[f[key] == k]
            if not len(t):
                continue
            x = stats(t, 0, weeks_all)
            rows.append([k, x["trades"], f"{x['win_rate']:.1%}", f"{x['mean_R']:+.2f}", fmt_r(x["total_R"]),
                         fmt_r(stats(t, 0.20, weeks_all)["total_R"]), f"${x['median_risk']:.2f}"])
        p.text(title, 9.5, "bold", gap=0.02)
        p.table(["", "trades", "win rate", "mean R", "total R", "after $0.20", "median stop"], rows,
                [2.45, 0.6, 0.7, 0.7, 0.8, 0.85, 0.77], size=7.5, gap=0.08)
    p.text("Orders", 9.5, "bold", gap=0.02)
    nf = orders[orders["fill_time"].isna()]
    reasons = pd.Series(np.where(nf["type"] == "momentum", "not filled, momentum: the target came first or 1 day passed",
                                 "not filled, sniper " + nf["end_reason"].fillna("").astype(str)))
    od = [["placed", len(orders)], ["filled", int(orders["fill_time"].notna().sum())]]
    od += [[k, v] for k, v in reasons.value_counts().items()]
    p.table(["", "orders"], od, [4.0, 0.8], size=7.5, gap=0.05)
    p.text("A sniper limit at the M1 order block's high almost always fills: price must trade through it before it "
           "can close beyond the stop or the higher low. An order moved to a newer order block counts once.",
           7.5, color=INK2)
    p.done()

    # ------------------------------------------------------------------ page 7: how it was run
    p = Page(doc, foot)
    p.h1("How this was run")
    p.bullets([
        "The bot: strategy.py in smc_v2_align with its default Settings (FVG POIs on M15 / M30 / H1 of at least half "
        "an ATR, D1 + H4 + H1 trend, the M1 sweep and break, the limit at the M1 order block's high, up to 3 tries; "
        "momentum orders on M5 pauses). The code of the label rounds with one change, the re-try fix (page 2).",
        "Trades: a limit fills when a candle trades through its price, from the candle after the decision. Exit at the "
        "stop or the target, whichever comes first; the stop if one candle reaches both; on the fill candle only "
        "the stop. A trade open at the end counts at the last price.",
        "R = the trade's result divided by its risk (entry to stop). Before costs unless a cost is named.",
        f"Prices: data/XAUUSD_1m.csv (Dukascopy BID candles, UTC), read by tools/common.py load_prices. The file mixes "
        "two time formats and repeats 12,644 candles where two downloads overlap (17 - 28 Nov 2025); each is read once.",
        ("Other versions, on the same prices, each in its own process (python -B, nothing written into its folder): "
         + "; ".join(f"{o['name']}" + (f" = {o['what']}" if o.get("what") else "")
                     + f" (folder {os.path.basename(os.path.normpath(o['dir']))}, code {o.get('code') or '?'})"
                     for o in others) + "." if others else "No other version was run."),
    ], 8.5)
    p.h2("To run it again")
    p.text("python tools/backtest_report.py --compare \"live code=<folder>=what it is\"     (about 40 minutes)",
           8, color=INK2, gap=0.04)
    p.text("python tools/backtest_report.py --from-saved     (the PDF again from the saved results)", 8, color=INK2, gap=0.04)
    p.text("python tools/leak_check.py     (the leak check alone)", 8, color=INK2, gap=0.1)
    p.h2("Files (reports/backtest/)")
    p.bullets(["backtest_report.pdf: this report. backtest_report.md: its tables as text.",
               "bot_orders_all.csv: every order the bot placed, filled or not, one row each (the columns of the label "
               "rounds: decided, dir, order, entry, stop, target, fill_time, rule, outcome, R, ...).",
               "compare_<n>.csv: the other versions' trades. leak_check.md / .csv: every leak-check run.",
               "meta.json: when it was made, the code fingerprint, the data span."], 8.5)
    p.done()
    doc.close()
    return dict(all=allst, after=after_st, cost20=cost20, spread=dict((k, v.sum()) for k, v in spread_R.items()),
                gaps=gaps, touch=touch, leak_ok=leak_ok, self_ok=self_ok, segs=segs, f=f,
                versions=versions_rows(f, others, segs, end, weeks_all))


def write_md(res, meta, path):
    lines = ["# Backtest: smc_v2 aligned on XAUUSD M1", "",
             f"{meta['first']} -> {meta['last']} (UTC), code {meta['code']}, made {meta['made']}. "
             "The full report: backtest_report.pdf.", "",
             f"Leak check: {'PASS' if res['leak_ok'] else 'FAIL'}; self-test: {'PASS' if res['self_ok'] else 'not run / FAIL'}.",
             "", "| period | trades | a week | win rate | total R | max DD | after $0.20 | after $0.30 |",
             "|---|---|---|---|---|---|---|---|"]
    for nm, a, b, note, t, wk in res["segs"]:
        x = stats(t, 0, wk)
        lines.append(f"| {nm} | {x['trades']} | {x['per_week']:.1f} | {x['win_rate']:.1%} | {fmt_r(x['total_R'])} | "
                     f"{x['max_dd']:.1f}R | {fmt_r(stats(t, 0.2, wk)['total_R'])} | {fmt_r(stats(t, 0.3, wk)['total_R'])} |")
    a = res["all"]
    lines.append(f"| all | {a['trades']} | {a['per_week']:.1f} | {a['win_rate']:.1%} | {fmt_r(a['total_R'])} | "
                 f"{a['max_dd']:.1f}R | {fmt_r(res['cost20'])} | {fmt_r(stats(res['f'], 0.3, 1)['total_R'])} |")
    lines += ["", "Bid / ask fills (buys on the ask): " + ", ".join(f"${k:.2f} spread {fmt_r(v)}" for k, v in res["spread"].items()),
              f"Stops that gapped: {res['gaps'][0]} trades, {res['gaps'][1]:+.1f}R more if exited at the open."]
    lines += ["", "| version, same prices | trades | total R | after the labels | max DD | after $0.20 |",
              "|---|---|---|---|---|---|"] + ["| " + " | ".join(str(c) for c in r) + " |" for r in res["versions"]]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--compare", action="append", default=[], metavar="NAME=FOLDER[=WHAT]",
                   help="another version of the bot (a folder with its strategy.py), WHAT: what it is, for the "
                        "report; repeat for more")
    p.add_argument("--from-saved", action="store_true", help="only the PDF, from reports/backtest/")
    p.add_argument("--quick", action="store_true", help="the first 5 months only (to try the report)")
    p.add_argument("--png", help="also save each page as a PNG into this folder")
    args = p.parse_args()
    low_priority()
    t0 = time.time()
    if args.from_saved:
        df, orders, others, leak, meta = load_saved()
    else:
        compares = [tuple(c.split("=", 2)) for c in args.compare]
        df, orders, others, leak, meta = compute(args.quick, compares)
    path = os.path.join(OUT, "backtest_report.pdf")
    res = build(df, orders, others, leak, meta, path, args.png)
    write_md(res, meta, os.path.join(OUT, "backtest_report.md"))
    a = res["all"]
    print(f"{a['trades']} trades, {a['total_R']:+.1f}R before costs, {res['cost20']:+.1f}R after $0.20; "
          f"leak check {'PASS' if res['leak_ok'] else 'FAIL'}; {time.time() - t0:.0f}s -> {path}")


if __name__ == "__main__":
    main()
