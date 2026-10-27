# Brief: make the SMC v2 bot trade like my labelled trades

## Who I am and what I want

I trade SMC on XAUUSD by hand, profitably. This repo is my attempt to automate it, but **the bot loses
money**: its rules don't match what I actually do.

I have labelled my own trades by hand, in my labeller: about 235 trades, Jan 2024 → Mar 2025, with the
context I saw (ranges, POIs, BOS, sweeps, OBs, FVGs) drawn on the chart.

**Your job, in rounds:**
1. **Backtest** the bot on the same XAUUSD data and period as my labels.
2. **Compare** its trades with mine:
   - trades it **missed** (I took them, it didn't);
   - **bad trades** (it took them, I wouldn't);
   - trades we **both** took.
3. **Diagnose** why each disagreement happens, down to the rule or detector in the code.
4. **Change the code** so the bot follows my logic, then backtest and compare again.
5. **At the end:** a **zip of the improved repo**, with a report of every change and its effect.

**The goal is that the bot trades like me, not that it predicts profit.** My trades are the reference.
Profit is reported every round, as a check.

**Read the whole codebase before you change anything.** I don't know its current structure exactly.
Find:
- its data loading;
- its indicators and detectors (ranges, liquidity, sweeps, BOS/CHoCH, order blocks, FVGs, POIs, HTF
  bias, sessions);
- its entry logic, filters, stop and target placement;
- its risk rules;
- its backtester.

Work with what's there. Don't rewrite the bot from scratch.

---

## 0. Safety rules (read first)

- **The bot is running live on this VPS. Don't stop it, restart it, or touch its files or config.**
  Work in a **copy** of the repo, e.g. `~/smc_v2_align/`. Make a `git init` there if it isn't a git repo,
  and commit the untouched copy as `baseline`.
- **Don't deploy anything.** I will review the zip and deploy it myself.
- **Don't send my data anywhere.** Everything stays on this machine.
- **Don't delete anything outside your working copy.**

---

## 1. The inputs I give you

| file | what it is |
|---|---|
| `labels_XAUUSD_1m_15_linked.csv` | my labels: my trades and the context I drew, grouped into setups |
| `XAUUSD_M1_*.csv` | Dukascopy M1 prices (UTC), the ones my labels were made on |

If a file is missing, stop and ask me for it. Don't download other data instead: the comparison is only
valid on the same prices.

### The labels CSV

**Columns:** `id, setup, step, kind, tf, dir, subtype, start, end, top, bottom, level, entry, stop, target, order, outcome, R, note`

**Times:**
- All times are **UTC**.
- Dates may come in two formats (`2024-01-05 16:17:00` or `1/5/2024 16:17`), so parse with
  `pd.to_datetime(..., format="mixed")`.

**`kind` values:**

| `kind` | meaning |
|---|---|
| `trade` | **one of my trades.** `start` = the candle I clicked (see `order`), `tf` = its timeframe (`M1`, `M5` …), `dir` = `long`/`short`, `entry`, `stop`, `target` = prices, `outcome` = `target` / `stop` / `not filled` (replayed by the labeller), `R` = the result in R |
| `setup` | a group: my trade(s) plus their context marks share its `id` in their `setup` column. `subtype` = `trade` (I took it) or `no trade` (I marked it and passed) |
| `range` | a range box: `start`–`end`, `top`–`bottom`, on `tf` |
| `ob`, `fvg` | an order block / fair value gap zone: `start`, `top`, `bottom`, `tf`, `dir` |
| `liquidity` | a liquidity level: `level`, `tf`, `dir` (`high` = buy-side above, `low` = sell-side below) |
| `sweep` | a sweep of liquidity: `start`–`end`, `level`, `dir` |
| `structure` | a break of structure (BOS / CHoCH); `subtype` may be `breakout` |
| `reaction` | a reaction at a POI on `tf` |
| `reviewed` | a period I went through completely: `start`–`end` |

**`step`** names a mark's role in the setup: `htf_poi`, `htf_range`, `h1_poi`, `h1_reaction`,
`m15_poi`, `m15_reaction`, `m15_structure`, `breakout`, `m5_range`, `m1_range`, `m1_range_2`, `sweep`,
`m1_bos`, `m1_ob`, `m1_fvg`, `trade`.

**Notes:**
- Marks whose note contains `auto-linked (trade #…)` were linked to those trades by a script; they
  belong to those trades only.
- **Ignore any setup whose note starts with `SUGGESTED`,** and its trade. Those are unreviewed
  suggestions.

**`order` and what `start` means:**
- `market`: I enter at the close of the candle I clicked. The decision is at **`start` + one `tf`
  candle**.
- `half`: a limit at the 50% of the break candle, decided at the close of the candle I clicked.
- `limit`: a resting order (at an OB/FVG …). **I clicked the candle where it filled**, so the decision
  was earlier, up to about 8 hours before.

**The reviewed period is 2024-01-05 → 2024-11-08.** Inside it, days with no trade of mine are real "no
setup" days. My trades after 2024-11-08 are valid trades, but the days around them are not fully
reviewed.

---

## 2. Step 1: get a faithful backtest

### 2a. Run the bot as it is

- Run it over **2024-01-01 → 2025-03-31** on my Dukascopy M1 file. The first days only warm up its HTF
  indicators.
- **Use UTC.** If the bot uses broker time (MT5 is usually UTC+2/+3, with summer-time switches), convert
  either the data going in or the trades coming out. Say in the report which one you did.

### 2b. Turn off what would hide signals

**Account-level limits** decide whether to take a trade, not whether a setup exists. They would make
setups look missed when they were only blocked. For the comparison, **switch these off** (in the copy
only):
- one position at a time;
- max trades per day;
- daily or weekly loss limits;
- cooldowns after losses;
- session or news blackouts that aren't part of the SMC logic.

Keep a separate run with them **on** for the profit numbers. Write down which switches you changed.

### 2c. Export every trade the bot takes

Write `bot_trades_round<N>.csv`, one row per trade:

| column | meaning |
|---|---|
| `id` | unique |
| `decided` | when the bot decided (the close of the signal candle), UTC |
| `dir` | `long` / `short` |
| `order` | `market` / `limit` / `half` |
| `entry`, `stop`, `target` | prices |
| `fill_time` | for limits: when it filled, or blank |
| `rule` | which entry rule or path fired |
| `filters_passed` | the filters it passed, `;`-separated |
| `outcome`, `R` | the backtest result |

### 2d. Sanity check before comparing (required)

For each of my `market` and `half` trades, check that my `entry` lies within the high–low of the M1
candle(s) at my decision time in the price file.
- **Expect at least 95%.**
- **If it's much lower,** the time zone or the data is off. Fix that before anything else; it would
  break every match.

---

## 3. Step 2: compare the bot's trades with mine

### Matching

**A bot trade matches one of my trades when:**
- it is in the **same direction**;
- for my **market / half** trades: its `decided` is within **±15 minutes** of my decision;
- for my **limit** trades: its `decided` is between **8 hours before** my fill candle and my fill
  candle, **and** its `entry` is within **0.5 × my risk** (|my entry − my stop|) of my entry. If the bot
  has a `fill_time`, a fill within ±15 minutes of my fill candle (with the same entry tolerance) also
  counts.

**Rules for picking:**
- Each of my trades gets **at most one** bot trade: the nearest (in time, or by entry for limits).
- Each bot trade matches at most one of mine.
- Other bot trades that also fit one of my trades are **duplicates**: the same idea, entered twice.
  Count them separately.

### Three groups

| group | meaning |
|---|---|
| **both** | a match |
| **missed** | my trade, no bot trade matches |
| **extra** | a bot trade inside the reviewed period that matches none of mine, i.e. **a trade I wouldn't take** |

For **both**, also flag **placement** differences: the bot's stop more than 0.5R from mine, or its
entry more than 0.25R from mine. These are right idea, wrong levels.

### The numbers, every round

Compute on the **development period** (section 5), and report like this:

| | value |
|---|---|
| my trades | n |
| bot trades | n |
| **recall** = both ÷ my trades | % (the share of my trades it takes) |
| **precision** = both ÷ bot trades | % (the share of its trades that are mine) |
| duplicates | n |
| placement differences | n |
| bot trades per week, against mine | n / n |
| the bot's results (limits on): trades, win rate, mean R, total R, max drawdown in R | |
| the bot's results on **both** trades only | |
| the bot's results on **extra** trades only | |

**Note on my R:** my targets were drawn in hindsight, so my R is optimistic. Compare the bot's R
between its groups, not against my R.

---

## 4. Step 3: diagnose every disagreement

### 4a. Missed trades: why didn't the bot take mine?

**Instrument the code.** Add a "why not" trace: for a given time and direction, run the bot's entry
logic and record **every condition it checks and whether it passed**, from HTF bias down to the M1
trigger.
- It must be read-only logging, with no change in behaviour.
- Then run it at each missed trade's decision time (and ±15 minutes).

**Put each missed trade in one category:**

| category | meaning |
|---|---|
| `no_detection` | the bot's detector never found the structure I traded: no range, no sweep, no BOS, no OB/FVG there. Compare with my marks in that trade's setup (my range box, my sweep, my BOS …) and write which one it lacked |
| `blocked_by_filter:<name>` | everything was detected, but filter `<name>` said no (e.g. HTF bias, session, min RR, distance to POI). Write the values |
| `timing` | the bot entered the same idea, but more than 15 minutes from me, or it was later invalidated |
| `wrong_direction` | it traded the opposite way there |
| `entry_type` | I used a limit at an OB/FVG and the bot only does market entries, or the other way round |
| `other` | explain |

### 4b. Extra trades: why would I not take these?

For each extra trade, look at **my marks around it**, using the setups whose marks are near in time and
price, and at the market:

| category | meaning |
|---|---|
| `no_htf_poi` | not at any HTF/H1 POI I marked, or anywhere near one |
| `inside_range` | the entry is in the middle of a range, not at its edge after a sweep |
| `against_htf` | against the H4/D1 direction I was trading that week |
| `no_sweep` | no liquidity taken before the entry |
| `weak_break` | the M1 BOS is small or has no displacement, compared with my BOS marks |
| `chop_day` | a day where I took nothing, and the bot took several trades or lost several times. I stop trading in ranges |
| `duplicate` | a re-entry of the same idea |
| `other` | explain |

### 4c. Charts I can look at

For the top categories, render about 10 example charts each into `report_round<N>.pdf`:
- H1, M15 and M1 panels around the trade;
- the bot's entry, stop and target;
- **my marks** (ranges, zones, levels, BOS) drawn on top;
- a one-line caption: the category and the failing condition.

### 4d. The round's summary

Write `report_round<N>.md`:
- the numbers table (section 3);
- the categories, sorted by count, for missed and for extra;
- **in plain trading language, what the bot does differently from me.** For example: "it treats any
  M1 swing break as a BOS; you only take breaks with a displacement candle after a sweep of the M1
  range".

---

## 5. Step 4: change the code, without curve-fitting

### Split the data

| period | dates | use |
|---|---|---|
| **development** | 2024-01-05 → 2024-07-31 | diagnose and change things here only |
| **holdout** | 2024-08-01 → 2024-11-08 | **don't look at it** until the final check |
| **late check** | 2024-11-09 → 2025-03-12 | recall only (my trades there are valid, the days around them are not fully reviewed) |

### Each round

1. Take the **largest category** (missed or extra).
2. Find the code responsible.
3. Write the change **as a trading rule first**, in one sentence I would recognise, e.g. "a range must
   have at least two touches on each side" or "take the M1 BOS only after the range low was swept".
4. Implement it.
5. Backtest and compare again on the development period.

### Keep a change only if all of these hold

- **It is a general rule.** No date conditions, no special cases for single trades, and no thresholds
  tuned to catch a handful more matches. A number may change only if you can say why the new value
  is what a trader would use (e.g. "a sweep needs to take the level by at least 0.1R").
- **It improves recall or precision on development,** without dropping the other by more than it
  gains.
- **The bot's other behaviour still works:** its tests pass, and the backtest runs end to end.

Otherwise, revert it and note it as tried and rejected.

**One change per commit.** Each commit message is the trading rule.

### When to stop

- after **8 rounds**; or
- when two rounds in a row give no kept change; or
- at **recall ≥ 70% and precision ≥ 50%** on development.

**Expect imperfect matching.** I'm a human: some of my trades depend on things the bot can't see.
Don't chase the last 20%.

---

## 6. Step 5: the final check, once

With the final code, run the comparison **once** on the **holdout** and the **late check**. Report all
three periods side by side:

| | baseline: dev | final: dev | baseline: holdout | final: holdout | final: late (recall only) |
|---|---|---|---|---|---|
| recall | | | | | |
| precision | | | | | |
| bot trades / week (mine) | | | | | |
| win rate, mean R, total R, max DD (limits on) | | | | | |

**How to read it:**
- If holdout recall and precision improved **about as much** as development did, the changes are
  real.
- If development improved a lot and the holdout didn't, the changes were fitted to the development
  trades. **Say so plainly.** Don't tune on the holdout to fix it.

---

## 7. Deliverables

1. **`smc_v2_aligned_<YYYY-MM-DD>.zip`:** the improved repo.
   - **Leave out:** data files, virtual environments, caches, logs, `.git`, and any keys, secrets or
     account details.
   - **Put in:**
     - `CHANGES.md`: every kept change, as its trading rule, with the files touched and its effect on
       recall, precision and R;
     - the tried-and-rejected changes, with why.
2. **The comparison and "why not" tools**, inside the repo (e.g. `tools/compare_labels.py`,
   `tools/why_not.py`), runnable with one command each. I'll use them again after I label more trades.
3. **For every round:** `report_round<N>.md`, `report_round<N>.pdf`, and the matched / missed / extra
   CSVs.
4. **`FINAL_REPORT.md`:**
   - the table from section 6;
   - the 5 biggest differences between the bot and me that are **still** there, and what data or
     feature would be needed to fix each;
   - anything in the code you think is a bug, even if unrelated.
5. **The baseline** stays as a commit or tag in your working copy, so every change can be compared or
   undone.

---

## 8. Don't

- Don't touch the live bot or its files.
- Don't change the matching rules or the periods to make the numbers look better.
- Don't look at, or tune on, the holdout before the final check.
- Don't add conditions that only exist to catch or exclude specific dates or trades.
- Don't judge a change by profit alone. A change that makes more money while matching me less is not
  what I asked for. Report it as a finding instead.
- Don't use my `outcome` or `R` inside the bot's logic. They are results, not information the bot has
  live.
