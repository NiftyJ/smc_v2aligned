## Round 7: no change kept

The bot is the round-6 bot, so the numbers below are round 6's.

**Categories (round 6).**
- Extra: `no_htf_poi` 112 of 199.
- Missed: `no_detection:htf_poi` 20 (no bot POI armed in your window), `other` 16, `bias_d1` 13,
  `m5_bos` 12.

**What the trace shows (dev):**

1. **The 20 trades with no bot POI armed don't share one cause.** What your setup marked as the POI:

   | your POI | trades |
   |---|---|
   | an H4 FVG, formed 2–5 days earlier | 4 |
   | an H1 or M15 zone | 4 |
   | a D1 order block | 2 |
   | M5 structure only | 3 |
   | nothing | 7 |

   For #593 and #599, your entries (2341, 2325) sit well above the H4 FVG you marked (2296–2303).
2. **Where entries sit against the POI gap** (0 = the gap's far edge, 1 = its near edge):
   - The bot's dev sniper entries: median 2.2 gap-heights above the far edge, so mostly above the gap.
     The matched ones are higher still (median 3.7).
   - Your entries against the FVG you marked: 21% inside it, 57% above it.

   So a rule that the entry must be inside the POI has no support.
3. **Half of the bot's 8 matches (4) are re-tries after its tight stop was hit** (#549, #558, #612,
   #790). That is how the bot gets to your later, deeper entries, and why the wider stops in round 4
   lost matches.

**Attempts (development period only).** Both re-test earlier ideas, since rounds 5 and 6 changed which
zones count:

| attempt | rule | recall | precision | bot trades | result |
|---|---|---|---|---|---|
| round 6 | — | 8.2% | 3.86% | 207 | |
| a | H4 FVGs (half an ATR or more) are POIs too: your setups mark 5 H4 FVGs among 27 | 8.2% | 3.56% | 225 | rejected: precision fell |
| b | trade when 2 of the D1/H4/H1 trends point the trade's way (was all 3) | 9.3% | 2.42% | 372 | rejected: precision −1.4 is more than recall +1.0 |

Attempt b catches #70 (a short at 2024-01-16, in the D1 warm-up). It also nearly doubles the bot's
trades, to 12.5 a week, with 76 against your direction that week.

Both are settings only (`STAIR_TFS`, `TREND_NEED`), so there is no diff.
