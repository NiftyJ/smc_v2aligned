"""
Checks for live_orders() (what live_mt5.py sends to MT5): cut the data just before a backtest
trade filled, and the order that filled must be waiting there with the same entry, stop and target.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from smcml.data import simulate  # noqa: E402
from strategy import backtest, live_orders  # noqa: E402

DF = simulate(60_000, mode="random", seed=5, bar_minutes=1, substeps=12, annual_vol=0.3)
TR = backtest(DF)


def test_the_order_that_fills_is_waiting_just_before():
    checked = 0
    for kind in ("sniper", "momentum"):
        filled = TR[(TR["type"] == kind) & TR["filled"].notna()]
        for r in filled.iloc[np.linspace(0, len(filled) - 1, 4).astype(int)].itertuples():
            T = DF.index.get_loc(r.filled)                  # data up to the candle before the fill
            live = live_orders(DF.iloc[:T])
            same = [o for o in live if o["type"] == kind and o["direction"] == r.direction
                    and np.isclose(o["entry"], r.entry) and np.isclose(o["stop"], r.stop)
                    and np.isclose(o["target"], r.target)]
            assert len(same) == 1, (kind, r.filled)
            assert same[0]["placed"] == r.placed and same[0]["expires"] > DF.index[T - 1]
            checked += 1
    assert checked == 8


def test_nothing_waits_that_the_backtest_never_placed():
    T = len(DF) - 3000
    end = DF.index[T - 1] + pd.Timedelta("1min")
    for o in live_orders(DF.iloc[:T]):
        assert o["placed"] <= end < o["expires"]
        assert o["direction"] * (o["entry"] - o["stop"]) > 0 and o["direction"] * (o["target"] - o["entry"]) > 0
        if o["type"] == "momentum":                         # its row in the full backtest, not filled by then
            row = TR[(TR["type"] == "momentum") & (TR["placed"] == o["placed"]) & (TR["direction"] == o["direction"])]
            assert len(row) == 1 and np.isclose(row["entry"].iat[0], o["entry"])
            assert not (row["filled"].iat[0] < end)
