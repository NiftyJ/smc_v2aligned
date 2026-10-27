"""
LIVE TRADING on MetaTrader 5 (Deriv or any MT5 broker) with the rules in strategy.py,
on many symbols at once.

Every time an M1 candle closes, for each symbol:
  1. read the last BARS closed M1 candles from MT5
  2. run strategy.live_orders() on them: the SAME code as the backtest, so it asks exactly
     "which limit orders would the backtest have working right now?"
  3. make MT5 match: place the new ones, move the ones whose price moved (the sniper's
     successive order block), cancel the ones the rules cancelled.
Step 2 runs in WORKERS processes side by side (one per CPU core).
Stop-loss and take-profit go on the order, so MT5 closes the trade even if this script stops.
Every order carries its own expiry (1 day), so a dead script never leaves orders hanging.

Symbols: names, or a whole folder of the Deriv symbol list:
  volatility = Volatility Indices (incl. the 1s ones), step = Step Indices, jump = Jump Indices,
  rangebreak = Range Break; also crashboom, crashboomflip, volcrashboom, hybrid, multistep,
  skewedstep, volswitch, spotvol, dex, drift, trek, expgrowth, ladder (Laddered Volatility).
Deriv synthetics ONLY: gold and stock indices are refused (they trade on IC Markets).

    python live_mt5.py                                   # dry run on the default list: prints, sends nothing
    python live_mt5.py --live                            # volatility, step, jump, range break, ladder,
                                                         # exp growth, drift, multi step; 0.25% a trade
    python live_mt5.py --symbols "Step Index" --risk 0.5 --live

Before --live: enable "Algo Trading" in the MT5 toolbar, and try it on a demo account first.
State (which orders this script placed) is kept in live_state.json next to this file.
"""
import argparse
import calendar
import hashlib
import json
import logging
import math
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from strategy import Settings, live_orders  # noqa: E402

try:
    import MetaTrader5 as mt5
except ImportError:
    sys.exit("pip install MetaTrader5")

HERE = os.path.dirname(os.path.abspath(__file__))
DERIV_TERMINAL = r"C:\Program Files\MetaTrader 5 Terminal\terminal64.exe"
GROUPS = {"volatility": "Volatility Indices\\", "step": "Step Indices\\", "jump": "Jump Indices\\",
          "rangebreak": "Range Break\\", "crashboom": "Crash Boom Indices\\",
          "crashboomflip": "Crash Boom Flip Indices\\", "volcrashboom": "Volatility Crash/Boom Indices\\",
          "hybrid": "Hybrid Indices\\", "multistep": "Multi Step Indices\\", "skewedstep": "Skewed Step\\",
          "volswitch": "Volatility Switch Indices\\", "spotvol": "Spot Volatility Indices\\",
          "dex": "DEX Indices\\", "drift": "Drift Switching Indices\\", "trek": "Trek Indices\\",
          "expgrowth": "Exponential Growth Indices\\", "ladder": "Laddered Volatility Indices\\"}
DEFAULT_SYMBOLS = ["volatility", "step", "jump", "rangebreak", "ladder", "expgrowth", "drift", "multistep"]
# This bot is Deriv synthetics only. Gold, ES35, UK100 and SA40 are traded on IC Markets by the
# other bot, so anything outside these folders (metals, stock indices, forex...) is refused.
SYNTHETIC_FOLDERS = tuple(GROUPS.values())
log = logging.getLogger("live")
_warned = set()


def warn_once(key, fmt, *arg):
    """A warning that would repeat every minute (same order, same reason) is logged once."""
    if (key, fmt) not in _warned:
        _warned.add((key, fmt))
        log.warning(fmt, *arg)


# ----------------------------------------------------------------------------- MT5 helpers
def connect(args):
    kw = dict(timeout=30000)
    if args.terminal:
        kw["path"] = args.terminal
    if args.login:
        kw.update(login=args.login, password=args.password, server=args.server)
    if not mt5.initialize(**kw):
        sys.exit(f"MT5 initialize failed: {mt5.last_error()}")
    a, t = mt5.account_info(), mt5.terminal_info()
    if args.server_check and args.server_check.lower() not in a.server.lower():
        mt5.shutdown()
        sys.exit(f"connected to {a.server} ({t.path}) but this bot only trades {args.server_check}: refusing")
    log.info("connected: %s | %s | login %s | %s account | balance %.2f %s",
             a.company, a.server, a.login, "DEMO" if a.trade_mode == 0 else "REAL", a.balance, a.currency)
    if args.live and not t.trade_allowed:
        log.warning("Algo Trading is OFF in the terminal: orders will be refused until you switch it on")


def resolve(names):
    """Symbol names, with the group words (volatility, step, jump) expanded from the symbol list."""
    every = mt5.symbols_get() or ()
    out = []
    for name in names:
        folder = GROUPS.get(name.lower())
        found = ([s.name for s in every if s.path.startswith(folder) and s.trade_mode == mt5.SYMBOL_TRADE_MODE_FULL]
                 if folder else [name])
        for sym in found:
            if sym in out:
                continue
            if not mt5.symbol_select(sym, True):
                log.error("symbol %r not found on this account, left out", sym)
                continue
            if not mt5.symbol_info(sym).path.startswith(SYNTHETIC_FOLDERS):
                log.error("symbol %r is not a Deriv synthetic (it belongs on IC Markets), left out", sym)
                continue
            out.append(sym)
    return out


def bars(symbol, count):
    """The last `count` CLOSED M1 candles (the one still forming is left out), server time."""
    for _ in range(30):                                   # the first call after start may be empty
        r = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 1, count)
        if r is not None and len(r) > 0:
            break
        time.sleep(2)
    else:
        raise RuntimeError(f"no M1 bars for {symbol}: {mt5.last_error()}")
    df = pd.DataFrame(r)
    df.index = pd.DatetimeIndex(pd.to_datetime(df["time"], unit="s"), name="time")
    df = df[["open", "high", "low", "close"]].astype(float)
    return df[df.index >= df.index[0].normalize() + pd.Timedelta("1D")]   # start on a whole day (D1 candles)


def last_bar_time(symbol):
    r = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 1, 1)
    return None if r is None or len(r) == 0 else int(r[0]["time"])


def epoch(ts):
    return calendar.timegm(pd.Timestamp(ts).timetuple())


def filling_modes(info):
    modes = []
    if info.filling_mode & 1:
        modes.append(mt5.ORDER_FILLING_FOK)
    if info.filling_mode & 2:
        modes.append(mt5.ORDER_FILLING_IOC)
    return modes + [mt5.ORDER_FILLING_RETURN]


def send(req):
    """order_send, trying each filling mode the symbol allows. Returns the result, None if refused."""
    info = mt5.symbol_info(req["symbol"])
    res = None
    for fm in filling_modes(info):
        req["type_filling"] = fm
        res = mt5.order_send(req)
        if res is None:
            log.error("  order_send failed: %s", mt5.last_error())
            return None
        if res.retcode != mt5.TRADE_RETCODE_INVALID_FILL:
            break
    ok = res.retcode in (mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_PLACED, mt5.TRADE_RETCODE_DONE_PARTIAL)
    (log.info if ok else log.error)("  -> retcode %s %s (order %s)", res.retcode, res.comment, res.order)
    return res if ok else None


# ----------------------------------------------------------------------------- orders
def key_of(o):
    """A name for one order that stays the same while the sniper moves it."""
    pre = "F" if o.get("flipped") else ""                # flipped orders never share a tag with normal ones
    if o["type"] == "sniper":
        return f"{pre}S|{o['direction']}|{o['tf']}|{o['poi_known']}|{o['shot']}"
    return f"{pre}M|{o['direction']}|{o['tf']}|{o['pause_start']}"


def flip(o):
    """The same order turned around: same entry, opposite side, the stop becomes the target and the
    target the stop. A buy limit below price becomes a sell stop there (and a sell limit a buy stop),
    so it triggers at the very moment the original would have filled."""
    return dict(o, direction=-o["direction"], stop=o["target"], target=o["stop"], flipped=True)


def tag(key):
    return "smc " + hashlib.sha1(key.encode()).hexdigest()[:10]   # MT5 comments are short


def side(o):
    return "BUY" if o["direction"] == 1 else "SELL"


def volume_for(o, info, args):
    if args.lots:
        v = args.lots
    else:
        kind = mt5.ORDER_TYPE_BUY if o["direction"] == 1 else mt5.ORDER_TYPE_SELL
        ref = 1000.0                                      # big, so cent rounding can't hide a cheap symbol's loss
        # flipped: sized on the target distance (the original stop), so the lots match the unflipped order
        far = o["target"] if o.get("flipped") else o["stop"]
        loss = mt5.order_calc_profit(kind, info.name, ref, o["entry"], far)
        loss = abs(loss) / ref if loss else abs(o["entry"] - far) / info.trade_tick_size * info.trade_tick_value
        if not loss > 0:
            log.error("%s: can't size %s (loss per lot %s)", info.name, key_of(o), loss)
            return 0.0
        v = mt5.account_info().balance * args.risk / 100 / loss
    step = info.volume_step
    v = math.floor(v / step + 1e-9) * step
    if v < info.volume_min:
        if not args.min_lot:
            warn_once((info.name, key_of(o)), "%s: %s %s needs %.4f lots for %.2f%% risk, under the minimum %.4f: "
                      "skipped (--min-lot trades the minimum)",
                      info.name, side(o), o["type"], v, args.risk, info.volume_min)
            return 0.0
        v = info.volume_min
    return round(min(v, info.volume_max, args.max_lots or np.inf), 8)


def rnd(x, info):
    return round(round(x / info.trade_tick_size) * info.trade_tick_size, info.digits)


def place(o, key, info, vol, args):
    """A limit order with its stop and target. Returns (result, filled at market?);
    result None = not placed (it is tried again on the next candle while the rules want it)."""
    d, tick = o["direction"], mt5.symbol_info_tick(info.name)
    s = -1 if o.get("flipped") else 1                     # flipped: a stop order on the limit's side of price
    entry, sl, tp = rnd(o["entry"], info), rnd(o["stop"], info), rnd(o["target"], info)
    gap = info.trade_stops_level * info.point             # the broker's minimum distance
    if s == 1:
        pending = mt5.ORDER_TYPE_BUY_LIMIT if d == 1 else mt5.ORDER_TYPE_SELL_LIMIT
    else:
        pending = mt5.ORDER_TYPE_BUY_STOP if d == 1 else mt5.ORDER_TYPE_SELL_STOP
    req = dict(action=mt5.TRADE_ACTION_PENDING, symbol=info.name, volume=vol, price=entry, sl=sl, tp=tp,
               magic=args.magic, comment=tag(key), deviation=args.deviation, type=pending,
               type_time=mt5.ORDER_TIME_GTC)
    if info.expiration_mode & 4:                          # SPECIFIED supported: expiry as a safety net
        req.update(type_time=mt5.ORDER_TIME_SPECIFIED, expiration=epoch(o["expires"]))
    market = tick.ask if d == 1 else tick.bid
    if s * d * (market - entry) <= 0:                     # price is already through the entry: it fills now
        req.update(action=mt5.TRADE_ACTION_DEAL, price=market,
                   type=mt5.ORDER_TYPE_BUY if d == 1 else mt5.ORDER_TYPE_SELL, type_time=mt5.ORDER_TIME_GTC)
        req.pop("expiration", None)
    elif s * d * (market - entry) < gap:
        warn_once((info.name, key), "%s: %s %s entry %s is closer to price than the broker allows (%s): "
                  "waiting", info.name, side(o), o["type"], entry, gap)
        return None, False
    if min(d * (req["price"] - sl), d * (tp - req["price"])) < gap:
        warn_once((info.name, key), "%s: %s %s stop/target is closer than the broker's minimum %s "
                  "(entry %s sl %s tp %s): skipped", info.name, side(o), o["type"], gap, req["price"], sl, tp)
        return None, False
    at_market = req["action"] == mt5.TRADE_ACTION_DEAL
    log.info("%s: PLACE %s %s%s %.4f lots  entry %s  sl %s  tp %s  (%s)", info.name, side(o), o["type"],
             " at market" if at_market else " stop" if s == -1 else " limit", vol, req["price"], sl, tp, o.get("target_type", ""))
    return send(req), at_market


def cancel(ticket, why, info):
    log.info("%s: CANCEL order %s (%s)", info.name, ticket, why)
    return send(dict(action=mt5.TRADE_ACTION_REMOVE, order=ticket, symbol=info.name))


_cut_tried = {}                                           # ticket -> time of the last close attempt


def cut_losers(args):
    """Close at market any of this script's positions whose floating loss is over --max-loss % of balance,
    whatever its stop says."""
    if not args.max_loss:
        return
    acc = mt5.account_info()
    if acc is None:
        return
    limit = acc.balance * args.max_loss / 100
    for p in mt5.positions_get() or ():
        loss = -(p.profit + p.swap)
        if p.magic != args.magic or loss <= limit or time.time() - _cut_tried.get(p.ticket, 0) < 10:
            continue
        _cut_tried[p.ticket] = time.time()
        buy = p.type == mt5.POSITION_TYPE_BUY
        tick = mt5.symbol_info_tick(p.symbol)
        log.warning("%s: CLOSE position %s: floating loss %.2f is over %.2f%% of balance %.2f (%.2f)",
                    p.symbol, p.ticket, loss, args.max_loss, acc.balance, limit)
        send(dict(action=mt5.TRADE_ACTION_DEAL, symbol=p.symbol, position=p.ticket, volume=p.volume,
                  type=mt5.ORDER_TYPE_SELL if buy else mt5.ORDER_TYPE_BUY, price=tick.bid if buy else tick.ask,
                  magic=args.magic, deviation=args.deviation, comment="smc max loss",
                  type_time=mt5.ORDER_TIME_GTC))


def modify(order, o, info):
    entry, sl, tp = rnd(o["entry"], info), rnd(o["stop"], info), rnd(o["target"], info)
    log.info("%s: MOVE order %s: entry %s -> %s  sl %s -> %s  tp %s -> %s", info.name, order.ticket,
             order.price_open, entry, order.sl, sl, order.tp, tp)
    req = dict(action=mt5.TRADE_ACTION_MODIFY, order=order.ticket, symbol=info.name, price=entry, sl=sl, tp=tp,
               type_time=order.type_time, expiration=order.time_expiration)
    if order.type_time == mt5.ORDER_TIME_SPECIFIED:
        req["expiration"] = epoch(o["expires"])
    return send(req)


# ----------------------------------------------------------------------------- per symbol
def compute(df, types, flipped=False):
    """Runs in a worker process: the orders the rules want working now, by key (turned around if flipped)."""
    t0 = time.time()
    orders = [o for o in live_orders(df, Settings()) if o["type"] in types]
    if flipped:
        orders = [flip(o) for o in orders]
    return {key_of(o): o for o in orders}, time.time() - t0


def dry_sync(sym, want, args, state):
    """Dry run: print the orders the rules want, when they change. Nothing is sent."""
    info = mt5.symbol_info(sym)
    for k, o in want.items():
        now = (rnd(o["entry"], info), rnd(o["stop"], info), rnd(o["target"], info))
        if state.get(k) != list(now):
            log.info("%s: WOULD %s %s %s %s %.4f lots  entry %s  sl %s  tp %s (%s)  expires %s", sym,
                     "PLACE" if k not in state else "MOVE", side(o), o["type"],
                     "stop" if o.get("flipped") else "limit", volume_for(o, info, args),
                     *now, o["target_type"], o["expires"])
            state[k] = list(now)
    for k in [k for k in state if k not in want]:
        log.info("%s: WOULD CANCEL %s (the rules cancelled it, or it filled)", sym, k)
        del state[k]


def sync(sym, want, args, state, last_candle):
    """Make MT5's pending orders for sym match `want`. state: this script's orders on sym, by key."""
    info = mt5.symbol_info(sym)
    mine = {o.comment: o for o in (mt5.orders_get(symbol=sym) or ()) if o.magic == args.magic}
    tags = {tag(k) for k in want}

    # 1. orders this script placed that are gone from MT5 without us cancelling them: filled (or expired)
    for k, rec in state.items():
        if rec.get("status") == "pending" and tag(k) not in mine:
            rec["status"] = "done"
            log.info("%s: order %s is no longer pending (filled or expired)", sym, rec.get("ticket"))

    # 2. orders the rules no longer want: cancel
    for c, order in mine.items():
        if c not in tags and cancel(order.ticket, "the rules cancelled it", info):
            for k in state:
                if tag(k) == c:
                    state[k]["status"] = "cancelled"

    # 3. orders the rules want: place or move
    for k, o in want.items():
        if state.get(k, {}).get("status") == "done":
            continue                                      # already filled once: never twice
        order = mine.get(tag(k))
        vol = volume_for(o, info, args)
        if vol <= 0:
            continue
        if order is None:
            res, at_market = place(o, k, info, vol, args)
            if res is not None:
                state[k] = dict(status="done" if at_market else "pending", ticket=res.order,
                                placed=str(o["placed"]), entry=o["entry"], stop=o["stop"], target=o["target"])
            continue
        same = all(abs(a - b) < info.trade_tick_size / 2 for a, b in
                   ((order.price_open, rnd(o["entry"], info)), (order.sl, rnd(o["stop"], info)),
                    (order.tp, rnd(o["target"], info))))
        if same:
            continue
        if abs(order.volume_current - vol) > info.volume_step / 2:    # new risk distance: new size
            if cancel(order.ticket, "moved, re-sizing", info):
                res, at_market = place(o, k, info, vol, args)
                state[k]["status"] = "cancelled" if res is None else "done" if at_market else "pending"
                if res is not None:
                    state[k].update(ticket=res.order, entry=o["entry"], stop=o["stop"], target=o["target"])
        elif modify(order, o, info):
            state[k].update(entry=o["entry"], stop=o["stop"], target=o["target"])

    # forget old records
    cutoff = last_candle - pd.Timedelta("7D")
    for k in [k for k, r in state.items() if pd.Timestamp(r.get("placed", last_candle)) < cutoff]:
        del state[k]


# ----------------------------------------------------------------------------- main
def load_state(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save_state(path, state):
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(state, fh, indent=1, default=str)
    os.replace(tmp, path)


def run_batch(due, args, state, pool):
    """One round: every symbol whose M1 candle just closed."""
    t0 = time.time()
    jobs = {}
    for sym, t in due:
        try:
            df = bars(sym, args.bars)
        except Exception as e:
            log.error("%s: %s", sym, e)
            continue
        if (df.index[-1] - df.index[0]) < pd.Timedelta("30D"):
            warn_once(sym, "%s: only %d days of M1 history (raise 'Max bars in chart'): the D1 bias may be "
                      "unreliable", sym, (df.index[-1] - df.index[0]).days)
        jobs[pool.submit(compute, df, args.types, args.flip)] = (sym, df.index[-1])
        del df
    n_want = 0
    for f in as_completed(jobs):
        sym, last_candle = jobs[f]
        try:
            want, _ = f.result()
            n_want += len(want)
            if args.live:
                sync(sym, want, args, state.setdefault(sym, {}), last_candle)
            else:
                dry_sync(sym, want, args, state.setdefault(sym, {}))
        except Exception:
            log.exception("%s: failed this candle; trying again on the next one", sym)
        if args.live:
            cut_losers(args)                              # a round takes ~30s: keep watching during it
    took = time.time() - t0
    log.info("candle %s | %d symbol(s) | %d order(s) wanted | %.1fs", max(v[1] for v in jobs.values()) if jobs
             else "-", len(jobs), n_want, took)
    if took > 55:
        log.warning("this round took longer than a candle: fewer symbols (or a faster machine) would keep up")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS,
                   help="names and/or groups (default: " + " ".join(DEFAULT_SYMBOLS) + ")")
    p.add_argument("--live", action="store_true", help="send orders (without it: dry run, nothing is sent)")
    p.add_argument("--risk", type=float, default=0.35, help="percent of balance risked per trade (default 0.35)")
    p.add_argument("--lots", type=float, default=None, help="fixed lot size instead of --risk")
    p.add_argument("--max-lots", type=float, default=None, help="never more than this many lots")
    p.add_argument("--min-lot", action="store_true", help="trade the minimum lot when --risk gives less")
    p.add_argument("--bars", type=int, default=90_000, help="M1 history per symbol (terminal max is "
                   "'Max bars in chart', usually 100000)")
    p.add_argument("--workers", type=int, default=os.cpu_count() or 1, help="processes running the strategy")
    p.add_argument("--magic", type=int, default=250_925)
    p.add_argument("--deviation", type=int, default=20)
    p.add_argument("--terminal", default=DERIV_TERMINAL,
                   help="path to terminal64.exe (default: the Deriv terminal on this machine)")
    p.add_argument("--server-check", default="Deriv",
                   help="refuse to run unless the account server contains this (default Deriv)")
    p.add_argument("--login", type=int, default=None)
    p.add_argument("--password", default=None)
    p.add_argument("--server", default=None, help="e.g. Deriv-Demo")
    p.add_argument("--once", action="store_true", help="run one round and exit")
    p.add_argument("--no-sniper", action="store_true", help="momentum orders only")
    p.add_argument("--no-momentum", action="store_true", help="sniper orders only")
    p.add_argument("--flip", action="store_true", help="trade every order turned around: same entry, "
                   "buy<->sell, stop<->target")
    p.add_argument("--max-loss", type=float, default=4.5, help="close a position at market once its floating "
                   "loss is over this percent of balance, whatever its stop (default 4.5, 0 = off)")
    args = p.parse_args()
    args.types = {t for t, off in (("sniper", args.no_sniper), ("momentum", args.no_momentum)) if not off}

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout),
                                  logging.FileHandler(os.path.join(HERE, "live.log"), encoding="utf-8")])
    log.info("=== %s | risk %s%s | max loss %s ===", "LIVE" if args.live else "DRY RUN (add --live to trade)",
             f"{args.lots} lots" if args.lots else f"{args.risk}% per trade", " | FLIPPED" if args.flip else "",
             f"{args.max_loss}% of balance" if args.max_loss else "off")
    connect(args)
    symbols = resolve(args.symbols)
    if not symbols:
        sys.exit("no symbols to trade")
    log.info("%d symbols: %s", len(symbols), ", ".join(symbols))
    state_path = os.path.join(HERE, "live_state.json")
    state = load_state(state_path) if args.live else {}

    last = {}
    pool = ProcessPoolExecutor(max_workers=args.workers)
    try:
        while True:
            if args.live:
                cut_losers(args)
            due = []
            for sym in symbols:
                t = last_bar_time(sym)
                if t is not None and t != last.get(sym):
                    due.append((sym, t))
                    last[sym] = t
            if due:
                run_batch(due, args, state, pool)
                if args.live:
                    save_state(state_path, state)
                if args.once:
                    break
            elif not mt5.terminal_info():
                log.warning("lost the terminal, reconnecting")
                mt5.shutdown()
                connect(args)
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("stopped (orders and positions stay in MT5 with their stop, target and expiry)")
    finally:
        pool.shutdown(cancel_futures=True)
        mt5.shutdown()


if __name__ == "__main__":
    main()
