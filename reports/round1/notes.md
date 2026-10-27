## Round 1: where the bot trades from

**Largest category (round 0):** extra `no_htf_poi`, 123 of the 228 extra trades (54%). The bot traded
where you had marked no POI on M15 or higher.

**What's behind it.** The bot's POI was always an order block (M15, M30 or H1). 55 of the 70 zones you
marked on M15 or higher are fair value gaps, so the bot was trading from a different kind of zone than you.
Part of the category isn't about zones at all: 73 of the 171 extra trades with this flag came when you had
no live POI mark in that direction anywhere. You weren't looking for a trade then. A POI rule can't
reproduce that on its own, and later rounds deal with direction and frequency.

**Attempts (development period only):**

| attempt | rule | recall | precision | bot trades | result |
|---|---|---|---|---|---|
| baseline | — | 3.1% | 1.3% | 232 | |
| a | an M15/M30/H1 POI counts only if it sits inside an H1/H4 order block or FVG of its direction | 2.1% | 1.2% | 160 | rejected: both fell |
| b | POIs are H1/H4 order blocks only | 2.1% | 2.1% | 94 | rejected: recall fell 1.0 pt, more than precision gained (0.8 pt) |
| **c** | **an FVG is a POI too: the latest M15/M30/H1 FVG of the trade's direction, from its first touch** | **8.2%** | **1.7%** | 473 | **kept** |
| d | as c, but the POIs are on H1/H4 | 3.1% | 1.3% | 230 | not kept: no change |

**The rule kept:** an FVG counts as a POI as well as an order block. On M15, M30 and H1, the most recent
fair value gap of the trade's direction arms the M1 entry from the first time price trades into it. A newer
FVG replaces it, and a close beyond its far edge (an FVG's "higher low") ends it. Everything after the touch
is unchanged: M1 sweep, M1 break, limit at the M1 order block, one setup per touch, up to 3 tries.

**Effect on dev:** recall 3.1% → 8.2%. Your sniper trades matched went from 1 to 6, and the bot's momentum
trades still match 2 of your sniper trades. Precision 1.3% → 1.7%. The cost is frequency: the bot now
trades 15.9 times a week against your 3.3, twice as often as before. Its extra trades not at one of your
POIs fell from 54% to 50% of extras. The 8 matched trades made +19.0R; all bot trades made +238.5R
(was +147.7R), with max drawdown 64.8R (was 52.0R).

Files: `strategy.py` (FVG POIs, setting `POI_KINDS`), `live_mt5.py` (an FVG POI's order gets its own
name, so the "never send twice" check keeps it apart from an order block known at the same candle),
`tools/common.py` and `tools/why_not.py` (show OB or FVG), and `tests/test_strategy.py` (tries are counted
per POI, not per touch time).
