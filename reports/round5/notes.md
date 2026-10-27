## Round 5: the POI is a fair value gap

**Category (round 4).** The largest is still extra `no_htf_poi` (202 of 364): the bot traded where
you had marked no zone.

**What's behind it.** Splitting the bot's dev trades by the POI that armed them:

| bot POI | extra | matched |
|---|---|---|
| M15 FVG | 83 | 4 |
| M30 FVG | 70 | 2 |
| H1 FVG | 56 | 0 |
| M15 order block | 58 | 0 |
| M30 order block | 42 | 0 |
| H1 order block | 21 | 0 |
| (momentum) | 34 | 2 |

None of the bot's 121 trades from order-block POIs matched one of yours. Your own marks point the
same way:
- 36 of your 44 zone marks on M15 or higher are FVGs, and 8 are order blocks.
- In your sniper setups: 19 FVGs and 6 order blocks.
- 12 setups mark only FVGs, 5 only order blocks, 1 both.

**Attempts (development period only):**

| attempt | rule | recall | precision | bot trades | result |
|---|---|---|---|---|---|
| round 4 | — | 8.2% | 2.14% | 373 | |
| a | the sweep must take a low made at the POI (after price reached it), not a low left on the way into it | 4.1% | 1.22% | 329 | rejected: both fell. The trades that matched yours were the quick ones: the sweep on the way into the POI. |
| **b** | **the sniper's POI is a fair value gap on M15/M30/H1; order blocks no longer arm it** | **8.2%** | **2.90%** | **276** | **kept** |

**The rule kept:** the sniper trades the first touch of the latest fair value gap of its direction on
M15, M30 or H1. Order blocks are no longer POIs on their own. Setting `POI_KINDS = ("ob", "fvg")` brings
them back.

**Effect on dev:**

| | round 4 | round 5 |
|---|---|---|
| recall | 8.2% | 8.2% (all 8 matches kept) |
| precision | 2.14% | 2.90% |
| bot trades | 373 | 276 |
| trades per week (yours: 3.3) | 12.5 | 9.3 |
| extras against your direction that week | 73 | 49 |
| duplicates | 1 | 0 |
| extra `no_htf_poi` | 202 | 148 |
| win rate | 10.5% | 11.4% |
| mean R | +0.57R | +0.70R |
| total R | +210.6R | +190.6R |
| max drawdown | 66R | 51R |

**The cost.** Your setups built on an order block (5 of 18 with a zone mark) now get no POI from the
bot. None of them was matched before. Two missed categories grow, as trades move into them from
`other` and `one_setup_per_poi`:
- `no_detection:htf_poi`: 3 → 6
- `no_detection:m1_bos`: 8 → 13

Your journal describes the order block as the POI, but your labels mark FVGs. If some order blocks are
POIs for you (for example, only an order block that left an FVG), say which, and that can come back
as its own rule.

Files: `strategy.py` (`Settings.POI_KINDS` and the module docstring). Rejected attempt:
`reports/rejected/round5a_sweep_of_a_low_made_at_the_poi.diff`.
