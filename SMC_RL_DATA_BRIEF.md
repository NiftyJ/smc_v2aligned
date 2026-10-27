# Brief: SMC bot to an RL training CSV, and the RL models to train on RunPod

You are a coding agent in the trader's SMC bot codebase ("smc v2"). The trader is the domain expert. **Do
not change, simplify or second-guess the SMC logic: find it and reuse it.** You have two jobs:

- **Part A: the dataset.** A backtest pass over MetaTrader 5 history (synthetic instruments) that writes
  one CSV row per decision. Each row holds the features this codebase computes at that moment, plus the
  replayed outcome (reward) of every action.
- **Part B: the RL models.** Training code for DQN, Double DQN, a Rainbow-style DQN, QR-DQN and PPO,
  on one shared environment and network, compared fairly on a RunPod GPU pod against simple
  baselines.

**Take-profits are structural, not fixed R.** The trader's targets are the next structure or HTF POI in
the trade's direction, so the R of a trade depends on where those sit:
- about **10R** when trading inside a range (target: the range's other side);
- about **20R** typically (target: the next H4 POI);
- **100R or more** on the big move after a range (target: D1 POIs or liquidity, or a runner).

The dataset replays each of these structural targets. The model chooses among them (or skips); it does
not choose a fixed R.

Work in this order:
1. **A1:** read the indicators.
2. **C1–C2:** find the trader's rules in the strategy and make each one checkable.
3. **A2–A6:** the dataset.
4. **B:** the models.
5. **C3:** use the rules in the models.

Part D lists every known way this can go wrong, with the automatic gate that proves it was handled.
**Nothing is exported for live trading until every gate in Part D passes.** Stop and write down any
question you can't answer from the code (sections A1 and C1) instead of guessing.

---

# Part A: the dataset

## A0. Rules

1. **Reuse the codebase.** Every SMC concept (structure, order blocks, FVGs, liquidity, sweeps, POIs,
   ranges, bias, sessions, whatever it has) comes from the existing code. Don't write a second version.
   If something must be adapted for a historical pass, wrap it; don't rewrite it.
2. **No look-ahead.** A feature for a decision at time t may only use candles that had **closed** by t.
   For an HTF candle that starts at s, that means s + tf ≤ t. This is the most important rule (A1 lists
   the usual leaks).
3. **One code path.** The backtest must compute features with the same functions, on the same amount of
   history, as the live bot will. Otherwise the model sees different inputs live.
4. **UTC everywhere.** Detect the MT5 server's offset (last tick time against real UTC, rounded to the
   hour), store it, and subtract it.
5. **Column prefixes:**
   - `meta_`: ids, times, prices;
   - `f_`: features, known at the decision;
   - `y_`: outcomes or labels, the future, never inputs.

   Training must select inputs by `startswith("f_")` only.
6. **Units for any distance you add:** R (÷ the entry-to-stop risk) or a share of the structure it
   belongs to (the leg, the range box, the window's high-to-low). Don't add ATR-scaled features; the
   trader doesn't want them. Keep the codebase's own indicators as they are.
7. **Deterministic:** the same data and settings give a byte-identical CSV. Write every setting and the
   git commit to `data/rl/settings.json`.

## A1. Inventory the codebase first (deliverable: `docs/FEATURE_INVENTORY.md`)

Read the whole repo before writing code. Search for at least these terms:
- order block, ob, fvg, fair value gap, imbalance;
- bos, choch, mss, break of structure, market structure, swing, pivot, fractal;
- liquidity, sweep, inducement, idm, equal highs, equal lows;
- poi, mitigation, breaker, premium, discount, equilibrium;
- range, wyckoff, accumulation, distribution, consolidation;
- bias, htf, mtf, ltf, session, killzone;
- MT5 code: `MetaTrader5`, `copy_rates`, `order_send`, `TIMEFRAME_`;
- strategy and backtest code: entry, stop, take profit, risk, lot.

Write a table with one line per indicator or signal:

| name | file:function | timeframe(s) | inputs | output (type, range) | when it is known | can it repaint? | used by the bot's entries? |
|---|---|---|---|---|---|---|---|

For "can it repaint", check each item for these usual leaks:
- swing or pivot points confirmed by candles to their **right** (only usable after the confirming candle
  closes);
- FVG or order-block code that reads candle i+1 or later;
- the **forming** HTF candle used as if closed;
- pandas `shift(-k)`, `rolling(center=True)`, `iloc[-1]` inside a historical loop, `resample()` label or
  closed defaults that move candle times;
- zigzag-style indicators;
- anything that reads the whole data frame at once.

Also write down:
- **The take-profit logic in detail:** how the bot picks its target. Which POIs and liquidity count, on
  which timeframes, how "unmitigated" is decided, any minimum R, any trailing, break-even or partial
  rules. Part A4 replays these.
- **The live loop:** how often it decides, and how much history it loads.
- **The strategy's rules** (setup detection, every filter, the trigger, orders, risk rules) go in their
  own file, `docs/RULES_INVENTORY.md`. Do that next, in Part C1, before building the dataset.
- **Questions you couldn't settle from the code**, each with the causal choice you made.

## A2. Export from MT5 (`rl/mt5_export.py`)

```python
import MetaTrader5 as mt5, pandas as pd, datetime as dt
mt5.initialize()                                     # terminal open and logged in
names = [s.name for s in mt5.symbols_get()]          # match the trader's list against the broker's names
mt5.symbol_select(name, True)
r = mt5.copy_rates_range(name, mt5.TIMEFRAME_M1, start_utc, end_utc)   # monthly chunks
df = pd.DataFrame(r)                                 # time, open, high, low, close, tick_volume, spread, real_volume
df["time"] = pd.to_datetime(df["time"], unit="s") - pd.Timedelta(hours=offset)
info = mt5.symbol_info(name)                         # point, digits, volume_min, volume_step, contract size
```

- Write `data/raw/<symbol>_M1.csv` with the columns `time, open, high, low, close, spread, tick_volume`.
  Keep `spread` (in points, converted with `info.point`); costs depend on it.
- If MT5 caps the history, set Tools → Options → Charts → Max bars to unlimited, or download in chunks.
- Report gaps longer than 5 minutes; synthetic instruments trade 24/7.
- Export at least 2 to 3 years per symbol if available (section B6 explains why).

## A3. Decision points: what one row is

1. Use **the trader's rules from the strategy** (found and wrapped in Part C1–C2) to emit candidates.
   Emit one every time the setup detection fires, **before** the filters, so the RL sees setups the rules
   took and ones they rejected. Part C3 says exactly which rows to keep.
2. Record each rule condition's state as a feature (Part C3):
   - `f_rule_<name>`: 0/1, one per condition;
   - `f_rule_all`: all of them pass, i.e. the bot would trade;
   - `f_rule_failed`: how many failed.
3. If the bot's triggers are rare (fewer than ~50 per symbol per month), add looser triggers built from
   the **same** indicators. For example, every BOS/CHoCH on the entry timeframes, with entries at the
   resulting order block or at market. Mark each row with `meta_source`: `bot` (passes every rule),
   `near_miss` (one or two rule conditions failed) or `loose`.
4. Each row is **one setup**. If a setup offers several entry types (e.g. OB limit, ½ momentum, market),
   keep them in the same row with outcome columns per type (A4). The RL chooses among them.

The `meta_` columns:
- `meta_id`, `meta_symbol`, `meta_setup_tf`, `meta_dir` (+1 / −1), `meta_decided` (UTC, the close of
  the trigger candle), `meta_source`
- For each entry type e: `meta_<e>_entry`, `meta_<e>_stop`, `meta_<e>_risk` (price; NaN if the type
  isn't offered)
- For each structural target k (A4): `meta_tp_<k>`, its price (NaN if there is none)

## A4. Outcomes / labels (`y_`): replay on M1

Use exactly these rules, the trader's backtest conventions:
- **Limit:** fills on the first M1 candle after the decision that trades at the entry. It is cancelled by
  the bot's own cancel rule if it has one. Otherwise it is cancelled after `WAIT = 240` minutes, or if
  price first runs **+5R** away from the entry without filling (the move was missed). Use this **one**
  cancel rule for all targets, so whether an order fills never depends on the target chosen. The fill
  candle can only stop the trade, not reach its target.
- **Market:** filled at the decision price, counted from the next candle.
- **Exit:** the stop or the target, whichever comes first. **If one candle reaches both, the stop wins.**
- **Holding limit:** `MAX_HOLD = 10 days`, then close at that candle's close (`y_..._open = 1`).
- **Costs:** subtract the spread at the fill as R: `y_<e>_cost_R = spread / risk`, once per filled
  trade. Prices are BID, so a long fills at ask = bid + spread.

**Structural targets.** Price every target k at the decision, from closed candles only. A POI or
liquidity level counts only if it existed, and was still unmitigated, at that moment (by the codebase's
own definition of mitigated). Use the codebase's own POI, liquidity and range code; A1 found it.

| k | target | the trader's typical R |
|---|---|---|
| `range` | the other side of the range the setup trades in, from the bot's range detection on M15 / H1 / H4. NaN if price isn't in a range | ~10R |
| `h1` | the nearest unmitigated opposing H1 POI or liquidity level, at least the bot's minimum R away (3R if it has none) | |
| `h4` | the nearest unmitigated opposing H4 POI or liquidity level, at the same minimum | ~20R, the usual one |
| `d1` | the nearest unmitigated opposing D1 POI or liquidity level (weekly too, if the code has it) | |
| `runner` | no fixed target, for the big move after a range: see below | 100R+ |
| `bot` | exactly the bot's own take-profit logic | |

**The runner.** If the bot has its own trailing or trade-management rules, replay those. Otherwise:
- once price reaches the `h4` target (or +10R if there is none), move the stop to the latest **confirmed**
  H1 swing low (high, for shorts);
- trail it to each newly confirmed H1 swing after that, using closed candles only;
- exit at the trailed stop, or at `MAX_HOLD`.

**Columns per entry type e:**

| column | meaning |
|---|---|
| `y_<e>_filled`, `y_<e>_fill_time` | the fill (a missed limit earns 0R) |
| `y_<e>_mfe_R` | the best excursion in R over the candles **before** the one that hits the stop (from the candle after a limit's fill). Any target at R distance T was reached exactly when `mfe ≥ T`. It also gives fixed-R results for analysis (T if `mfe ≥ T`, else −1) without storing them |
| `y_<e>_cost_R` | spread ÷ risk |

**Columns per entry type e and target k:**

| column | meaning |
|---|---|
| `y_<e>_<k>_R` | R after costs with take-profit k: its R distance if reached, −1 if stopped, the closing R at `MAX_HOLD` |
| `y_<e>_<k>_exit` | exit time, UTC (the environment in Part B needs it) |
| `y_<e>_<k>_open` | 1 if it was still open at `MAX_HOLD` |

`y_open_at_end` = 1 if any outcome is unresolved when the data ends. **Exclude those rows from
training.**

Write the replay as a pure function
`replay(m1, row, entry_type, target_price | trail_rule) -> (filled, fill_time, exit_time, R)`. Unit-test
it on hand-built candles (A6).

## A5. Features (`f_`)

**From the inventory (A1):** every indicator's state at `meta_decided`, encoded **relative to the
trade's direction**. Mirror prices for shorts, so +1 always means "with the trade". Use:
- booleans as 0/1;
- distances in R or structure units;
- timeframes as ordinal codes;
- ages as candles or hours since.

Include every timeframe the bot reads (the D1 / H4 / H1 / M30 / M15 / M5 / M1 stack, or whatever it
uses).

**Add these if the codebase doesn't already have them.** They encode the trader's two hypotheses:

**H1: losses cluster in ranges.** More than 3 stops in a day means a range day; about 3 losing days in a
row on an instrument means a range.
- Compute these from the **replayed outcomes of earlier rows on the same symbol whose exit time is before
  `meta_decided`**, at the bot's take-profit (or 10R if there is none).
- They describe the market, not any agent's choices:
  - `f_stops_today`, `f_wins_today`, `f_net_R_today` (UTC day)
  - `f_stop_rate_24h`, `f_stop_rate_72h`
  - `f_losing_days_3`: of the last 3 days, how many had a negative net R
  - `f_hours_since_win`
  - `f_open_now`: earlier rows still unresolved, since losses arrive in bunches

**H2: the biggest winners (100R+) come after large H4 / D1 ranges.** For tf in H4 and D1:
- `f_<tf>_in_range`
- `f_<tf>_range_bars`: how long the box has held
- `f_<tf>_range_R`: its height ÷ this setup's risk
- `f_<tf>_range_pos`: 0 = bottom, 1 = top, flipped for shorts
- `f_<tf>_touches`
- `f_<tf>_false_breaks`
- `f_<tf>_compression`: the high-to-low of the last 5 candles ÷ that of the last 30
- `f_<tf>_breakout_age`: signed, in candles since a close outside a box of at least 10 candles
- `f_<tf>_bars_since_bos`

If the codebase has its own range detector, use it to define the box. Otherwise, the box is the
high-low of the longest run (at least 6 candles) with no close outside it.

**The targets** (known at the decision; the model's main clue for which target to pick):
- `f_<e>_tp_<k>_R`: the R distance to each structural target k, per entry type. NaN, plus an
  `f_tp_<k>_none` flag, when there is no such target.
- `f_tp_beyond_range`: 1 if the `h4` target lies beyond the current range's far side, i.e. reaching it
  needs a breakout.
- `f_tp_<k>_age`: how old that POI is (in candles of its timeframe), and `f_tp_<k>_touched`: whether it
  was touched before.

**Also add:**
- `f_cost_R` (spread at the decision ÷ risk) for each entry type
- `f_hour_sin`, `f_hour_cos`, `f_weekday`
- `f_symbol_id`: an integer per symbol, for the model's embedding

**Candle windows for the deep encoder (Part B).** Don't put these in the CSV.
- Save the per-timeframe M1-derived bar arrays (`data/rl/bars_<symbol>_<tf>.npy`: open, high, low,
  close, time).
- For each row, store the index of the last **closed** bar per timeframe (`meta_idx_<tf>`).
- The trainer cuts the windows itself on the GPU (B3). No look-ahead, no giant files.

Write `data/rl/<symbol>.csv`, `data/rl/all.csv`, and the same as Parquet (float32). Write
`data/rl/schema.md` with one line per column: name, meaning, unit, when it is known.

## A6. Checks (must pass) and `data/rl/summary.md`

**Tests**
1. **No peeking:**
   - Rebuild the features with prices cut 1 minute after 200 random decisions, the rest replaced by a 50%
     crash.
   - Every `f_` value of rows decided before the cut must be identical.
   - Also check that each row's `meta_idx_<tf>` points at a bar closed by `meta_decided`.
2. **Replay:**
   - hand-built candles for a limit fill, a limit miss (target first), the fill candle only able to stop,
     the stop winning a tie, a market entry, and the holding limit;
   - for every fixed target k, `y_<e>_<k>_R == (its R distance) − cost` exactly when `mfe ≥` that R
     distance;
   - the runner's trail moves only on confirmed swings from closed candles.
3. **Causal H1 features:** shuffle the outcomes of rows that close after each decision. Those features
   must not change.
4. **Live parity:** for 100 random rows, compute the features the way the live loop will (its history
   length) and assert they're equal to the CSV.
5. **Schema:**
   - every column is documented;
   - no unexpected NaN;
   - prefixes are correct;
   - rebuilding gives a byte-identical file.

**summary.md**
- **Counts:** rows per symbol and month, the fill rate per entry type, and the share of `f_rule_all = 1`.
- **Win rate and mean R:** per target and entry type, for all rows and for the bot's rows.
- **H1:** the share of stops on days with 3 or more stops. Then the mean R when `f_stops_today ≥ 3`
  against < 3, and when `f_losing_days_3 = 3` against fewer.
- **H2:** the frequency of `mfe ≥ 50` and `≥ 100` by H4 / D1 range state (inside a box, recent breakout,
  neither), bucketed by `range_bars` and `range_R`.
- **The trader's target rule of thumb.** A table of mean R, win rate and median R distance per target k
  (`range`, `h1`, `h4`, `d1`, `runner`, `bot`), split by regime (inside an HTF range / just after a range
  breakout / neither). The trader expects:
  - `range` (~10R) to work best inside ranges;
  - `runner` or `d1` (100R+) right after a range;
  - `h4` (~20R) otherwise.

---

# Part B: the RL models for RunPod (build all of these, compare them fairly)

## B1. What to build

Build **one environment, one network trunk, one evaluation**, and train these algorithms on them. Then
pick a winner by **validation** results, never by test results:

| # | algorithm | why it is in the line-up |
|---|---|---|
| 1 | **DQN** (target network, Huber loss, masks) | the plain value-learning reference |
| 2 | **Double DQN (DDQN)** | plain DQN overrates actions whose noisy value estimates came out high by luck. With rare 10R–100R rewards that bias is large. DDQN picks the action with the online network and scores it with the target network |
| 3 | **Dueling DDQN + prioritized replay + 3-step returns** ("Rainbow-lite") | dueling learns "is this setup worth anything" apart from "which target". Prioritized replay replays the rare big winners and losers more often |
| 4 | **QR-DQN** (distributional, with the Double DQN target) | learns the whole spread of outcomes per action, not only the average: a natural fit for heavy-tailed R. Its median and tails also go in the report |
| 5 | **Masked PPO** | policy-gradient reference |
| 6 | **Supervised EV policy** (B5) | not RL. It is cheap and strong, and every RL algorithm must beat it |

Why this works:
- Every action's outcome is already known from A4, so the environment is an exact replay. No market
  model is needed.
- Every algorithm also trains the **auxiliary heads** on those known outcomes for **all** actions, not
  just the one taken. This keeps learning stable when rewards are rare and heavy-tailed.

## B2. Environment (`rl/env.py`, gymnasium API, numpy-vectorised)

**Episodes**
- One symbol, 7 consecutive days of rows, taken from the **training** period only.
- Start at a random day; pick the symbol at random, weighted by row count.

**Observation** = `[f_ features (normalised)] + [own state]`. The own state is:
- open positions, and open risk in R;
- today's realised R;
- today's stops (own trades);
- trades today, and placed orders left this week;
- own losing days in a row;
- hours since the last own trade.

**Action:** Discrete(1 + E·K). 0 = skip; otherwise (entry type e, structural target k) with
k ∈ {range, h1, h4, d1, runner, bot} (K = 6). The R of a trade comes from where that target sits
(`f_<e>_tp_<k>_R`), not from a fixed number.

**Masks:** forbid
- entry types the setup doesn't offer, and targets it doesn't have (`f_tp_<k>_none`, e.g. no range, no
  H4 POI ahead);
- a second open position on the same symbol;
- anything once the weekly order budget is spent (default 10 orders a week);
- **hard risk rules** (the trader's, enforced in code, configurable):
  - after 3 own stops in a day, only skip until the next UTC day;
  - after 3 losing days in a row on the symbol, only skip until an H4 or D1 close outside its range box
    in either direction (from `f_<tf>_breakout_age`).

**Reward** (given at the decision, because the outcome is already known):
- `r = y_<e>_<k>_R / 10` if filled;
- `0` if the limit is missed;
- minus `0.005` (= 0.05R) for every order placed, so orders that rarely fill aren't free (they also use
  up the weekly budget);
- **no log or other non-linear transform** of R (section B4 explains why).

**Clock:**
- Step to the next row's `meta_decided`.
- Close own trades whose `y_..._exit` time has passed. Update the own-state counters as they close
  (today's stops count only **closed** stops; open risk counts open trades).
- At each UTC midnight, update the losing-day streak.

**Randomisation:** for robustness, during training only:
- spread × U(1.0, 1.5) (re-cost the reward with it);
- drop 10% of rows at random;
- add 5 minutes of fill delay to market entries 20% of the time.

**Speed:** step all N environments in one numpy call. **No** Python object per environment, **no**
SubprocVecEnv.

## B3. Network (`rl/model.py`, PyTorch)

**Inputs**
- **Tabular:** the `f_` vector, F dimensions.
- **Symbol:** an embedding of `f_symbol_id`, 16 dimensions.
- **Own state:** about 8 dimensions.
- **Candle windows (optional, v2):**
  - gather on the GPU from `bars_*` using `meta_idx_<tf>`: M1 120, M5 96, M15 64, H1 64, H4 48, D1 30;
  - scale each window like a chart: (x − window low) / (window high − window low);
  - channels: open, high, low, close, high − low, valid flag;
  - mirror for shorts.

**Encoders**
- **Tabular:** Linear(F→256) → LayerNorm → GELU → Dropout 0.1 → Linear(256→256) → GELU.
- **Each window timeframe:**
  - Conv1d(6→48, kernel 5) → GELU;
  - Conv1d(48→48, kernel 5, stride 2) → GELU;
  - Conv1d(48→48, kernel 3, stride 2) → GELU;
  - then [mean, last] → 96, concatenated over 6 timeframes (576), then Linear(576→256).
- **Trunk:** concat(tabular, symbol, own state, windows) → Linear(→256) → GELU → Linear(256→256) →
  GELU.

**Heads, per algorithm** (A = 1 + E·K actions; masked actions get −1e9 before any max, argmax or softmax)
- **PPO:** policy Linear(256→A), value Linear(256→1).
- **DQN, Double DQN:** Q head Linear(256→A).
- **Dueling:**
  - V head Linear(256→1), advantage head Linear(256→A);
  - Q = V + (Adv − mean of Adv over the **valid** actions).
- **QR-DQN:** Linear(256→A·N) with N = 32 quantiles per action; the action value is the quantiles' mean.
- **Auxiliary, the same for every algorithm** (supervised, trained on every row with known outcomes,
  whatever action was taken):
  - `P_fill[e]`: E logits, binary cross-entropy against `y_<e>_filled`.
  - **A reach curve, which serves every structural target at once.**
    - `S[e, j] = P(mfe ≥ x_j before the stop | filled)` on a fixed R grid
      x = {1, 2, 3, 5, 7, 10, 15, 20, 30, 50, 75, 100, 150, 200}: E·J logits.
    - Parameterise them so S never rises with x: logit_j = logit_1 − cumsum(softplus(Δ)).
    - Train with binary cross-entropy against `1[y_<e>_mfe_R ≥ x_j]`.
    - The chance of reaching a target that sits T R away is S interpolated, in log R, at T. The model
      learns where price tends to get to, and the structure says where each target is.
  - **Runner:** `Huber` regression of `y_<e>_runner_R`. Add quantiles 0.1 / 0.5 / 0.9 (pinball loss) for
    the report.

## B4. Training (`rl/dqn.py`, `rl/ppo.py`, `rl/train.py`, a YAML config per algorithm)

**Shared by every algorithm** (so the comparison is fair):
- **Implementation:** single-file CleanRL-style code that you own: `rl/dqn.py`, with flags `--double`
  `--dueling` `--per` `--nstep N` `--qr`, and `rl/ppo.py`. Library versions (sb3) can't add the
  auxiliary losses or mask the bootstrapped targets.
- **Pretraining:** the trunk and the auxiliary heads, supervised, on all training rows. Use 5 epochs,
  batch 4096, AdamW at lr 1e-3, and early stopping on validation log-loss. Every algorithm starts from
  this same checkpoint.
- **Auxiliary loss** added to every algorithm's loss: weight `c_aux` 0.5 → 0.1 (linear).
- **Reward and discount:**
  - reward = R / 10, **not clipped** (unlike Atari DQN's ±1 clipping, which would erase the difference
    between a 10R and a 100R trade);
  - **no** log or square-root transform (see below);
  - γ = 0.99, with an ablation run at 0.95.
- **Observation normalisation:** statistics from the training rows only, frozen for evaluation.
- **Curriculum:** the first 10% of steps allow only {skip, any entry type with the `bot` target}. Then
  unlock `range`, `h1`, `h4`, `d1` and `runner`.
- **Early stopping:** validate every 1M environment steps; stop after 10M without improvement. Report
  the steps and GPU-hours used.
- **Seeds:** 5 per algorithm in the final round.

**Masks in Q-learning.** Store the next state's action mask in the replay buffer:
- **Acting:** argmax over valid actions only. Exploration samples uniformly among **valid** actions.
- **DQN target:** `y = r + γ(1 − done)·max over valid a' of Q_target(s', a')`.
- **Double DQN target:** `a* = argmax over valid a' of Q_online(s', a')`, then
  `y = r + γ(1 − done)·Q_target(s', a*)`.
- **QR-DQN:** the same, on quantiles. Choose a* by the mean of the online quantiles; the loss is the
  quantile Huber loss (κ = 1) against the target quantiles.

**DQN-family starting points**

| setting | value |
|---|---|
| parallel environments | 64 |
| replay buffer | 2M transitions, kept as GPU tensors (obs, action, reward, next obs, done, next mask) |
| batch | 512, one gradient step per environment step of all 64 envs (replay ratio 8) |
| learning starts | 100k transitions |
| optimiser | Adam, lr 1e-4, grad-norm clip 10 |
| loss | Huber (smooth L1); quantile Huber for QR-DQN |
| target network | soft update, τ = 0.005 per gradient step |
| exploration (ε-greedy over valid actions) | 1.0 → 0.05 over the first 10% of steps, then 0.05 → 0.01 by 50% |
| prioritized replay (#3) | α = 0.6, β 0.4 → 1.0 over training, priority = abs(TD error) + 1e-3 |
| n-step returns (#3) | n = 3 |
| QR-DQN quantiles | N = 32 |
| max environment steps | 50M per walk-forward fold |

**PPO starting points**

| setting | value |
|---|---|
| parallel environments | 256 |
| steps per rollout | 128 (batch 32,768) |
| minibatches | 8 |
| update epochs | 4 |
| learning rate | 2.5e-4, linear decay |
| GAE λ | 0.95 |
| clip | 0.2 |
| entropy coefficient | 0.01 → 0.002 (linear) |
| value loss | Huber, weight 0.5 |
| max grad norm | 0.5 |
| advantage normalisation | on |
| max environment steps | 200M per walk-forward fold |

**Budget:** each algorithm also gets the same cap of **GPU-hours per fold** (default 2). The comparison
is then fair in cost, not only in steps.

**Run it in two rounds (keeps RunPod costs down):**
1. **Screening:** all 5 RL algorithms × 2 seeds, on the 2 most recent walk-forward folds.
2. **Final:** the best 2 by **validation** mean R per trade (drawdown breaks ties) × 5 seeds × all folds.

**Why no reward transform or clipping:** log or square-root compression of R, or clipping it, makes
high-RR trades look worse than they are. For example, a 10R trade that wins 13.6% of the time is worth
+0.5R, but negative after log1p. The policy would learn to avoid the trades the trader cares about. Keep
R linear; Huber losses, advantage normalisation and the reward scale of 1/10 handle the size.

**Logging** (TensorBoard, or Weights & Biases if a key is set), per run:
- episode R, trades a week, fill rate, mask hit rates;
- DQN family: mean Q of the chosen action against the realised R (a widening gap means overestimation),
  TD error, ε, and PER weights;
- PPO: entropy, approx KL, clip fraction, value loss;
- auxiliary AUC at each R grid level, and the runner's error;
- validation mean R per trade.

## B5. Baselines every algorithm must beat (on the same test months)

1. **The bot:** `f_rule_all = 1` rows, entered at the bot's entry with the `bot` target, under the same
   masks and budget.
2. **The trader's rule of thumb:** the same `f_rule_all = 1` setups, with the target picked by regime:
   - inside an H4 / D1 range → `range` (~10R);
   - within 10 H4 candles after an H4 / D1 range breakout in the trade's direction → `runner` (100R+);
   - otherwise → `h4` (~20R).
3. **Supervised EV policy:** the pretrained auxiliary heads only:
   - `EV(e, k) = P_fill·(S(T_k)·T_k − (1 − S(T_k)) − cost)`, where T_k is the R distance to target k;
   - for the runner, `P_fill·(predicted runner R) − cost`;
   - take the argmax if EV ≥ a threshold tuned on validation.
4. **Random:** the same number of trades at random, 1000 repeats; the policy must beat 95% of them.
5. **Always skip:** 0R.

If no RL algorithm beats baselines 2 and 3 on the test months, ship the better of those two and say so.

## B6. Evaluation (`rl/evaluate.py`, `rl/compare.py`)

- **Walk-forward by quarter:**
  - train on everything before the quarter;
  - validate on its first month (early stopping, thresholds, choosing the algorithm);
  - test on the remaining two months;
  - roll forward.

  Test months only go in the report. Never shuffle across time; overlapping trades leak.
- **Choosing:** pick the algorithm and settings by **validation** results only. Run the **final
  holdout** (the last 15% of the timeline) **once**, on the chosen model.
- **Placebo:** retrain the chosen algorithm with the `y_` columns shuffled within each symbol and month.
  Test R must be about 0, or the pipeline is leaking.
- **Robustness:**
  - test R with the top 1% and the top 5% of winning trades removed;
  - results per symbol;
  - spread × 1.5;
  - market fills delayed one candle.
- **Portfolio test:** run all symbols together through the test months, with a cap on total open risk
  across symbols (default 3R) and the same masks. Report the combined equity curve and its drawdown,
  since losses on several instruments can land at once.
- **`results/compare.md`:** one row per algorithm and baseline, mean ± standard deviation over seeds, test
  months only:
  - total R, mean R a trade, trades a week, fill rate;
  - max drawdown in R, longest losing streak, % of months positive;
  - steps and GPU-hours used.

  Plus the same per symbol.
- **Per algorithm** (`report_<algo>.md` plus `test_trades_<algo>.csv`):
  - win rate and mean R per target type, next to its typical R distance;
  - action distribution: which targets it picks, split by regime (inside an HTF range / after a breakout
    / neither);
  - how often the H1 / H2 masks fired;
  - for QR-DQN, the predicted median and 10% / 90% quantiles against the realised R.

## B7. RunPod

- **Pod:**
  - one RTX 4090, A5000 or L40S (24 GB is enough, including the 2M-transition replay buffer on the GPU);
  - **16 or more vCPUs, 64 GB RAM** for the environment and data loading;
  - a network volume at `/workspace` for data, checkpoints and logs;
  - the PyTorch template (CUDA 12.x).
- **`runpod.sh`:** pip install the pinned `requirements.txt` (torch, numpy, pandas, pyarrow, gymnasium,
  pyyaml, tensorboard), check the data hash, then
  `python -m rl.sweep --round screening` and later `python -m rl.sweep --round final`. The sweep runs the
  algorithm × seed × fold grid, one run at a time per GPU (or 2 at once if memory allows), and writes
  `results/compare.md`.
- **Checkpoints:** save every 10 minutes and at each run's best validation to `/workspace/runs/<run>/`.
  `--resume` continues after a restart, so cheaper spot pods are safe. Name each run with the algorithm,
  seed, fold, config hash and git commit.
- **Export for live:** `rl/export.py` writes, for the chosen model:
  - `policy.pt`: TorchScript, CPU. For the DQN family, argmax of Q over valid actions; for QR-DQN, of
    the quantiles' mean; for PPO, the argmax of the policy.
  - `norm.json` (observation statistics), `actions.json` (the action table), `features.txt` (the exact
    `f_` order).

  The live bot on the MT5 machine runs it on the CPU with the same feature code and masks, and logs
  every decision.

## B8. Deliverables

`docs/FEATURE_INVENTORY.md`, `rl/mt5_export.py`, `rl/build_dataset.py`, `rl/replay.py`, `rl/env.py`,
`rl/model.py`, `rl/dqn.py`, `rl/ppo.py`, `rl/train.py`, `rl/sweep.py`, `rl/evaluate.py`, `rl/compare.py`,
`rl/export.py`, `rl/rules.py`, `rl/rules_policy.py` (Part C), `rl/gates.py` (Part D),
`docs/RULES_INVENTORY.md` (Part C1),
`configs/{dqn,ddqn,rainbow_lite,qrdqn,ppo,gates}.yaml`, `runpod.sh`, `requirements.txt`, `tests/`,
`docs/RISKS.md` (Part D), `data/rl/schema.md`, `data/rl/summary.md`, `results/gates.md`.

`tests/` holds the A6 tests, plus:
- an environment test: masks, clock and counters on a hand-built stream;
- a Q-target test: masked actions never enter the max or argmax; the Double DQN target uses the online
  argmax.

**Done means:**
- the A6 tests pass;
- every algorithm trains end to end on a small slice on the CPU, with and without the rule warm start;
- `results/compare.md` and `results/gates.md` exist.

**Ready for live means:** every gate in Part D says PASS, or the trader has signed off each INCONCLUSIVE
gate in `results/signoff.txt`.

---

# Part C: the trader's rules from the strategy

The bot has hard-coded entry rules in its strategy code. On their own they don't make money; the RL's
job is to **improve** them. Include them as below.

The replay environment already knows the outcome of every action, so the rules are not needed for
exploration. They are the scaffold (where to look, what to look at) and the starting point.

## C1. Find the rules (do this right after the indicator inventory in A1)

Read the strategy, backtest and live code. Write `docs/RULES_INVENTORY.md` with:
- **Setup detection:** what makes a setup exist (the first condition that must be true). File, function
  and the exact condition.
- **Every filter condition**, one line each:
  - a short name (this becomes `f_rule_<name>`);
  - file:function;
  - the exact condition in plain words;
  - the timeframe(s) it reads;
  - when it is known.

  Examples of what to look for: bias agreement across timeframes, being at or inside a POI, a sweep
  first, a break of structure, a range type, session or time windows, distance or R limits.
- **The trigger:** what makes the bot place the order.
- **Orders:** entry types, stop placement, take-profit logic, cancellation or expiry, re-entries.
- **Risk rules:** daily loss limits, maximum positions, cool-downs. These become masks, not features.
- **Evaluation order:** the order the bot checks things in, and where it **short-circuits** (stops at the
  first failed condition). Near-misses need every condition evaluated, so this matters.
- **Questions** the code doesn't answer, each with the causal choice you made.

## C2. Make every rule checkable on its own (`rl/rules.py`)

Wrap the strategy's **own** functions; don't re-implement them.
- `setups(history) -> list`: every setup the detection finds, in time order.
- `conditions(history, setup) -> {name: 0/1}`: **every** condition, each evaluated even when an earlier
  one fails (wrap the bot's short-circuiting so each check can run alone). Closed candles only.
- `bot_decision(history, setup) -> action`: exactly what the bot would do (skip, or the entry type and
  the bot's take-profit).

**Parity test (gate G22):** on at least one full month, `bot_decision` must reproduce the bot's own
backtest trades **exactly**: the same entries, decision times, entry prices, stops and take-profits.
Fix the wrapper until it does. Everything below depends on it.

## C3. Use the rules in five places

1. **Where to look: the rows.** The rules' setup detection decides which moments become rows. Keep:
   - every setup that passes all conditions (`meta_source = bot`);
   - **near-misses:** setups where one or two conditions failed (`meta_source = near_miss`);
   - **looser triggers** built from the same indicators (A3), so the RL isn't limited to vetoing the
     bot's signals (`meta_source = loose`).
2. **What it sees: the features.** Every rule condition becomes a 0/1 input:
   - `f_rule_<name>` for each condition;
   - `f_rule_all` = 1 when the bot would trade;
   - `f_rule_failed` = how many conditions failed.

   The RL learns which conditions matter, and in which situation (in a range, after a breakout, which
   symbol).
3. **Where it starts: the head start from trajectories.**
   - `rl/rules_policy.py` runs the rules through the replay environment: take, with the bot's entry and
     take-profit, when `f_rule_all = 1`, otherwise skip. It records the trajectories (state, rule
     action, reward, next state).
   - **PPO** first copies them: behaviour cloning of the actor on the trajectories (cross-entropy, 3
     epochs, after the supervised pretraining). During PPO, a KL penalty towards the rule policy, weight
     1.0, fades linearly to 0.
   - **The DQN family** learns from them as demonstrations (DQfD):
     - a separate demonstration buffer, 25% of each batch at first, decaying to 5%;
     - the large-margin loss `max_a [Q(s,a) + m·1(a ≠ a_rule)] − Q(s, a_rule)`, with m = 0.1 (= 1R).
       Its weight of 1.0 fades to 0.
   - Their influence **fades to zero over the first 20% of training**. The rules lose money on their own,
     so they are a starting point, not a teacher.
   - Every algorithm is **also trained without this head start**. Keep whichever does better on
     **validation**.
4. **Two modes, both trained and compared:**
   - **Filter mode:** the RL sees only the rules' own signals (`meta_source = bot`). It can only skip
     them or choose the target (one of the structural targets in A4). This is the exact "rules improved
     by RL" idea, and the safest first version to run live.
   - **Full mode:** all rows (bot, near_miss, loose), so the RL can also find trades the rules miss.
5. **The yardstick.** In filter mode, the RL must beat the bot **on the same trades**: the bot's signals,
   the same test months, the same masks and costs. The bot (baseline 1 in B5) also appears in every
   comparison table. Report how many of the bot's signals the RL skipped, and the R of the skipped ones
   against the kept ones.

The trader's **risk** rules (C1) stay hard-coded masks in every mode. They are safety rules, not entry
logic, and the RL never overrides them.

---

# Part D: every known problem is a gate

For each problem below, build the guard into the code, and make `rl/gates.py` check it automatically.
`rl/gates.py` runs after every final-round sweep and writes `results/gates.md`: one line per gate, with
PASS / FAIL / INCONCLUSIVE and the numbers behind it. Also write `docs/RISKS.md`: for each row, the file
and function that implement the guard, and the test that checks it.

**Rules for the gates**
- **Export refuses:** `rl/export.py` refuses to export unless every gate passes, or the trader has
  signed off each INCONCLUSIVE gate in `results/signoff.txt`.
- **Thresholds belong to the trader:** they live in `configs/gates.yaml`. **Never loosen a threshold to
  make a gate pass**; only the trader changes them.
- **If a gate fails, stop and report** what failed, with the evidence. Fixing a **bug** is fine. Fixing a
  modelling choice is fine only if the choice is made on **validation** data. Re-tuning until the test
  months look good is overfitting the test.
- **The final holdout is single-use.** `holdout.lock` records the model hash and the date. A second run
  needs `--unlock-holdout`, and it is reported in `gates.md`.

| gate | problem | guard built in | automatic check (PASS when) |
|---|---|---|---|
| G1 | features use future candles (repainting swings, unclosed HTF candles, `shift(-k)`, whole-data scaling) | closed-candle-only features (A0.2); normalisation fitted on training rows only | truncation test (A6.1): every `f_` value identical when the future is replaced |
| G2 | targets or POIs use the future (a POI "unmitigated" only because later candles were ignored or used) | targets priced from POIs valid at the decision (A4) | the same truncation test on `meta_tp_*` and `f_*_tp_*`: identical |
| G3 | live features differ from training | one code path, the same history length, UTC (A0.3, A0.4) | live-parity test (A6.4): 100 rows equal to 1e-9 |
| G4 | replay bugs (points vs price, time zone, fill rules) | a pure `replay()` with unit tests (A4) | the A6.2 tests pass; target consistency 100%; 20 random trades charted to `results/trade_charts/` for the trader (signed off in `signoff.txt`) |
| G5 | a leak somewhere in the pipeline | — | placebo (shuffled `y_`): test mean R within ±2 standard errors of 0 |
| G6 | the result is luck | — | test total R above the 95th percentile of random policies with the same trade count |
| G7 | it's no better than simple rules | the B5 baselines | test mean R a trade above the bot, the rule of thumb and the supervised EV policy, and the bootstrap 5th percentile of the policy's test mean R above 0 |
| G8 | a few huge winners carry everything | the R reach curve; no reward clipping or transform | still positive with the top 1% of winners removed (top 5% reported) |
| G9 | it games the simulator (orders that never fill, always skip, one action only) | P_fill head, placement cost, weekly budget, masks (B2) | trades a week between 1 and 20; fill rate ≥ 50% of the bot's; no single (entry, target) over 80% of trades unless a baseline does the same; trades in ≥ 50% of test weeks |
| G10 | training is unstable or collapsed (entropy to 0, diverging Q) | pretraining, auxiliary heads, Huber losses, entropy schedule, curriculum | across 5 seeds, the standard deviation of test mean R is below its mean; PPO entropy above 0.1 at 10% of training |
| G11 | DQN overrates its own actions | Double DQN target, target network, logging predicted Q against realised R | on validation, the mean predicted value of taken actions is within ±0.2R of their realised mean R. For QR-DQN, realised R falls below its predicted 10% quantile 5–15% of the time |
| G12 | masked actions leak into learning | next-state masks stored in the buffer (B4) | the Q-target unit test passes: masked actions never enter a max or argmax |
| G13 | reward clipping or transforms | linear R ÷ 10 (B2) | config check, and a unit test: a 100R trade yields reward 10.0 and a 10R trade 1.0 |
| G14 | it worked once, then faded (the market changed) | walk-forward, retraining per fold | ≥ 60% of test quarters positive, and no single quarter more than 50% of the total profit |
| G15 | one symbol carries everything | per-symbol results | with 3 or more symbols, no symbol more than 60% of the test profit |
| G16 | backtest vs live execution | spread costs, the one cancel rule, fill-delay randomisation | still positive at spread × 1.5 with market fills 1 candle late |
| G17 | losses on several instruments at once | the portfolio cap on open risk (B6) | the combined test drawdown is within `max_portfolio_dd_R` (the trader sets it; default 25R) |
| G18 | too little evidence for big targets | — | the test months hold at least 30 trades that reached the policy's typical target (e.g. 20R for `h4`, 100R for `runner`); otherwise INCONCLUSIVE: more history needed |
| G19 | the trader's risk rules didn't apply | hard masks (B2) | every mask fired whenever its condition occurred; open risk never exceeded its cap |
| G20 | engineering (pod restarts, version drift, wrong data) | checkpoints, `--resume`, data hash, pinned versions | a run killed at 50% and resumed ends within 1% of an uninterrupted run; the data hash matches; TorchScript CPU outputs equal the training model's on 1000 rows |
| G21 | the discount factor is too short for the weekly budget | budget usage logged | if the weekly budget runs out in more than 50% of weeks, the γ = 0.995 ablation has been run and reported |
| G22 | the rules wrapper doesn't match the bot | `rl/rules.py` wraps the strategy's own functions (C2) | parity test: on at least a full month, `bot_decision` reproduces the bot's backtest trades exactly (entries, times, prices, stops, take-profits) |
| G23 | near-miss rows are labelled wrong | every condition evaluated on its own (C2) | for 50 random near-miss rows, exactly the conditions they list as failed fail when the bot's own code checks them |
| G24 | filter mode doesn't actually improve the rules | the yardstick (C3.5) | in filter mode, test mean R a trade on the bot's signals is above the bot's own, with the bootstrap 5th percentile of the difference above 0 |
