"""
Example charts for a round's report (report_round<N>.pdf): one page per trade, H1 / M15 / M1 panels
around it, the bot's entry / stop / target (or yours, for a missed trade), YOUR marks drawn on top
(ranges, order blocks, FVGs, liquidity, sweeps, BOS), and a one-line caption.

    from charts import Charter
    with Charter(df, marks, "report_round0.pdf") as ch:
        ch.page(time, d, title, caption, bot=row_or_None, mine=row_or_None)
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch, Rectangle  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from smcml.bias import resample  # noqa: E402

INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
BULL, BEAR, RANGE, MINE, BOT_C = "#2a78d6", "#eb6834", "#8a8984", "#7a3fb0", "#0f8a5f"
PAGE = (11.69, 8.27)
PANELS = (("1h", "H1", pd.Timedelta("4D"), pd.Timedelta("16h")),
          ("15min", "M15", pd.Timedelta("26h"), pd.Timedelta("6h")),
          ("1min", "M1", pd.Timedelta("150min"), pd.Timedelta("60min")))
plt.rcParams.update({"font.size": 8, "text.color": INK, "axes.edgecolor": GRID, "xtick.color": INK2,
                     "ytick.color": INK2, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
                     "savefig.facecolor": SURFACE, "text.parse_math": False})


def candles(ax, bars):
    x = np.arange(len(bars))
    o, h, l, c = (bars[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    up = c >= o
    ax.vlines(x, l, h, color="#6b6a66", lw=0.5, zorder=3)
    body = np.maximum(np.abs(c - o), (h.max() - l.min()) * 0.002)
    for m, fc in ((up, "#ffffff"), (~up, "#3d3c39")):
        ax.bar(x[m], body[m], bottom=np.minimum(o, c)[m], width=0.65, color=fc, edgecolor="#3d3c39", lw=0.3, zorder=4)
    ax.set_xlim(-1, len(bars) + 1)
    ax.grid(color=GRID, lw=0.4)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ticks = np.linspace(0, len(bars) - 1, 5).astype(int)
    ax.set_xticks(ticks)
    ax.set_xticklabels([bars.index[i].strftime("%d %b\n%H:%M") for i in ticks], fontsize=6.5)


class Charter:
    def __init__(self, df, marks, path):
        self.df, self.marks, self.path = df, marks, path
        self.bars = {"1min": df, "15min": resample(df, "15min"), "1h": resample(df, "1h")}
        self.pdf = None
        self.pages = 0

    def __enter__(self):
        self.pdf = PdfPages(self.path)
        return self

    def __exit__(self, *exc):
        self.pdf.close()

    def text_page(self, lines):
        fig = plt.figure(figsize=PAGE)
        y = 0.93
        for size, weight, text in lines:
            fig.text(0.06, y, text, fontsize=size, fontweight=weight, va="top")
            y -= 0.03 if size < 12 else 0.045
        self.pdf.savefig(fig)
        plt.close(fig)

    def _pos(self, bars, t):
        return int(bars.index.searchsorted(pd.Timestamp(t), side="right")) - 1

    def _marks(self, ax, bars, a, b):
        m = self.marks
        end = m["end"].fillna(m["start"])
        m = m[(m["start"] <= b) & (end >= a) & (m["kind"] != "setup") & (m["kind"] != "reviewed")]
        lo, hi = ax.get_ylim()
        n = len(bars)
        for r in m.itertuples():
            x0 = max(self._pos(bars, r.start), 0) - 0.5
            x1 = (min(self._pos(bars, r.end), n - 1) + 0.5) if pd.notna(r.end) else n - 0.5
            col = BULL if r.dir in ("bull", "up", "low", "long") else BEAR if r.dir in ("bear", "down", "high", "short") else RANGE
            if r.kind == "trade":
                continue
            if r.kind in ("range", "ob", "fvg") and pd.notna(r.top) and pd.notna(r.bottom):
                if r.bottom > hi or r.top < lo:
                    continue
                ax.add_patch(Rectangle((x0, r.bottom), max(x1 - x0, 0.8), r.top - r.bottom, fill=r.kind != "range",
                                       fc=col, alpha=0.18 if r.kind != "range" else 1, ec=col if r.kind != "range" else RANGE,
                                       lw=0.9, ls="--" if r.kind == "range" else "-",
                                       hatch="////" if r.kind == "fvg" else None, zorder=2))
                ax.text(x0, r.top, f"{r.tf} {r.kind}{' ' + r.subtype if isinstance(r.subtype, str) else ''} #{r.id}",
                        fontsize=5.5, color=INK2, va="bottom", zorder=8, clip_on=True)
            elif pd.notna(r.level) and lo <= r.level <= hi:
                ls = {"liquidity": ":", "sweep": "-", "structure": "-", "reaction": "-."}.get(r.kind, "-")
                ax.plot([x0, x1], [r.level, r.level], color=col, lw=1.0, ls=ls, zorder=5)
                ax.text(x1, r.level, f" {r.tf} {'BOS' if r.kind == 'structure' else r.kind} #{r.id}", fontsize=5.5,
                        color=INK2, va="center", zorder=8, clip_on=True)

    def _levels(self, ax, bars, t0, entry, stop, target, color, label):
        n = len(bars)
        x0 = max(self._pos(bars, t0), 0)
        for y, ls, name in ((entry, "--", "entry"), (stop, "-", "stop"), (target, "-", "target")):
            if pd.isna(y):
                continue
            ax.plot([x0, n - 0.5], [y, y], color=color if name != "stop" else BEAR, lw=1.1, ls=ls, zorder=6)
            ax.text(n - 0.5, y, f" {label} {name} {y:.2f}", fontsize=6, va="center", color=color, zorder=9,
                    clip_on=False)
        ax.axvline(x0, color=color, lw=0.8, ls=":", zorder=1)

    def page(self, t, title, caption, bot=None, mine=None):
        t = pd.Timestamp(t)
        fig = plt.figure(figsize=PAGE)
        gs = fig.add_gridspec(2, 2, height_ratios=[1, 1.25], left=0.05, right=0.88, top=0.86, bottom=0.07,
                              hspace=0.32, wspace=0.18)
        axes = [fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1]), fig.add_subplot(gs[1, :])]
        fig.text(0.05, 0.95, title, fontsize=12.5, fontweight="bold")
        fig.text(0.05, 0.915, caption, fontsize=8.5, color=INK2, va="top", wrap=True)
        for ax, (tf, name, before, after) in zip(axes, PANELS):
            bars = self.bars[tf]
            a, b = t - before, t + after
            w = bars[(bars.index >= a) & (bars.index <= b)]
            if len(w) < 3:
                ax.set_axis_off()
                continue
            candles(ax, w)
            ys = [w["low"].min(), w["high"].max()]
            for row in (bot, mine):
                if row is not None:
                    ys += [v for v in (row.get("entry"), row.get("stop")) if pd.notna(v)]
                    if name == "M1" and pd.notna(row.get("target")) and abs(row["target"] - row["entry"]) < 4 * (ys[1] - ys[0]):
                        ys.append(row["target"])
            pad = (max(ys) - min(ys)) * 0.06
            ax.set_ylim(min(ys) - pad, max(ys) + pad)
            self._marks(ax, w, a, b)
            if mine is not None:
                when = mine.get("decision") if pd.notna(mine.get("decision", pd.NaT)) else mine.get("start")
                self._levels(ax, w, when, mine.get("entry"), mine.get("stop"), mine.get("target"), MINE, "your")
            if bot is not None:
                self._levels(ax, w, bot.get("decided"), bot.get("entry"), bot.get("stop"), bot.get("target"), BOT_C, "bot")
            ax.set_title(name, loc="left", fontsize=8.5, fontweight="bold")
        fig.legend(handles=[Line2D([], [], color=MINE, ls="--", label="your trade"),
                            Line2D([], [], color=BOT_C, ls="--", label="bot trade"),
                            Patch(fill=False, ec=RANGE, ls="--", label="your range"),
                            Patch(fc=BULL, alpha=0.3, label="your bullish OB / FVG / sell-side liq."),
                            Patch(fc=BEAR, alpha=0.3, label="your bearish OB / FVG / buy-side liq."),
                            Line2D([], [], color=INK2, label="your BOS / sweep line")],
                   loc="lower center", ncol=6, fontsize=6.5, frameon=False)
        self.pdf.savefig(fig)
        plt.close(fig)
        self.pages += 1
