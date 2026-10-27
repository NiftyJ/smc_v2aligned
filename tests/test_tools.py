"""
Checks for the comparison tools (tools/).

  * the read-only records (journal, why-not trace) change nothing in the backtest
  * the bot's trade list has the brief's columns and also lists the orders that never filled
  * the matching rules on a hand-made example: time window, entry tolerance, nearest first, duplicates
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from smcml.data import simulate  # noqa: E402
from strategy import backtest  # noqa: E402
from common import bot_trades  # noqa: E402
import compare_labels as cl  # noqa: E402

DF = simulate(60_000, mode="random", seed=5, bar_minutes=1, substeps=12, annual_vol=0.3)
BRIEF_COLUMNS = ["id", "decided", "dir", "order", "entry", "stop", "target", "fill_time", "rule", "filters_passed",
                 "outcome", "R"]


def test_journal_and_trace_change_nothing():
    plain = backtest(DF)
    journal = []
    trace = {"sniper": {"bars": set(range(0, len(DF), 7)), "out": []},
             "momentum": {"m5": set(range(0, len(DF) // 5, 3)), "out": []}}
    recorded = backtest(DF, journal=journal, trace=trace)
    pd.testing.assert_frame_equal(plain, recorded)
    assert journal and trace["sniper"]["out"] and trace["momentum"]["out"]


def test_bot_trades_lists_every_order():
    t = bot_trades(DF)
    assert list(t.columns[:len(BRIEF_COLUMNS)]) == BRIEF_COLUMNS
    journal = []
    filled = backtest(DF, journal=journal)
    ended = [j for j in journal if j["event"] != "filled"]             # sniper orders cancelled / still waiting
    assert len(t) == len(filled) + len(ended)
    assert t["fill_time"].notna().sum() == filled["filled"].notna().sum()
    assert t["end_reason"].str.startswith(("cancelled", "waiting")).sum() == len(ended)
    assert set(t["order"]) <= {"limit", "half"} and set(t["dir"]) <= {"long", "short"}
    assert (t.loc[t["outcome"] == "not filled", "R"] == 0).all()


def test_matching_rules():
    T0 = pd.Timestamp("2024-03-01 10:00")
    mine = pd.DataFrame([
        dict(id=1, d=1, order="half", decision=T0, fill_candle=pd.NaT, entry=100.0, risk=2.0, tf_td=pd.Timedelta("1min")),
        dict(id=2, d=1, order="limit", decision=pd.NaT, fill_candle=T0 + pd.Timedelta("6h"), entry=95.0, risk=2.0,
             tf_td=pd.Timedelta("1min")),
        dict(id=3, d=-1, order="market", decision=T0, fill_candle=pd.NaT, entry=100.0, risk=2.0, tf_td=pd.Timedelta("1min")),
    ])
    bot = pd.DataFrame([
        dict(d=1, decided=T0 + pd.Timedelta("10min"), entry=101.0, fill_time=pd.NaT),   # 0: fits #1 (10 min)
        dict(d=1, decided=T0 - pd.Timedelta("3min"), entry=101.0, fill_time=pd.NaT),    # 1: fits #1 nearer: taken
        dict(d=1, decided=T0 + pd.Timedelta("1h"), entry=95.8, fill_time=pd.NaT),       # 2: fits #2 (0.4 x risk)
        dict(d=1, decided=T0 - pd.Timedelta("3h"), entry=95.1, fill_time=pd.NaT),       # 3: too early for #2 (9 h)
        dict(d=1, decided=T0 + pd.Timedelta("2h"), entry=96.5, fill_time=pd.NaT),       # 4: entry 0.75 x risk away
        dict(d=1, decided=T0, entry=100.0, fill_time=pd.NaT),                           # 5: long, #3 is a short
    ])
    bot.index = range(10, 16)
    taken, dup = cl.match(mine, bot)
    pairs = dict(zip(mine.loc[taken["mine"], "id"], taken["bot"]))
    assert pairs[1] == 15 or pairs[1] == 11                             # nearest in time (0 or 3 min)
    assert pairs[2] == 12
    assert 3 not in pairs                                               # nothing the same way
    assert set(dup["bot"]) == {10, 11} - {pairs[1]}                     # fitted #1 but lost to a nearer one
    late = bot.loc[[13]].assign(fill_time=T0 + pd.Timedelta("6h5min"))   # filled within 15 min of #2's candle
    taken2, _ = cl.match(mine.iloc[[1]], late)
    assert list(taken2["bot"]) == [13]
