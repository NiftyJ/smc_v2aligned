## Round 8: no change kept (the last round)

The bot is the round-6 bot, so the numbers below are round 6's.

**Category (round 7).** The largest missed category is `no_detection:htf_poi` (20): in your window the
bot had no POI armed. One cause is the bot's timer: a POI arms the M1 entry for only one day after
its first touch. Several of your entries came at zones touched days earlier.

**Attempt (development period only):**

| attempt | rule | recall | precision | bot trades | result |
|---|---|---|---|---|---|
| round 7 | — | 8.2% | 3.86% | 207 | |
| a | a POI stays armed until price closes beyond its far edge or a newer one replaces it, not for one day after the touch | 8.2% | 3.81% | 210 | rejected: no gain. 3 more bot trades, none a match. |

It is a settings value only (`SNIPER_WINDOW`), so there is no diff. With the round-5 and round-6 POIs
(big FVGs), a newer gap of the same kind almost always replaces the old one within a day, so the
timer rarely matters. Your entries at old zones are at H4 FVGs and D1 order blocks, which the bot
doesn't arm. Adding H4 was tried in rounds 4 and 7.

**Stop.** Rounds 7 and 8 kept no change, and round 8 is the last round the brief allows. The final
check follows: `FINAL_REPORT.md`.
