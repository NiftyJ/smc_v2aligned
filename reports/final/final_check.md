# Final check: baseline (round 0) against final (round 8)

dev 2024-01-05 -> 2024-07-31, holdout 2024-08-01 -> 2024-11-08, late 2024-11-09 -> 2025-03-12. Results are in R with no costs; the late period is recall only.

| | baseline: dev | final: dev | baseline: holdout | final: holdout | final: late |
|---|---|---|---|---|---|
| recall | 3.1% (3/97) | 8.2% (8/97) | 6.1% (3/49) | 4.1% (2/49) | 4.4% (3/68) |
| precision | 1.3% (3/232) | 3.9% (8/207) | 1.8% (3/166) | 2.1% (2/94) | — |
| bot trades / week (mine) | 7.8 (3.3) | 6.9 (3.3) | 11.7 (3.5) | 6.6 (3.5) | — |
| win rate, mean R, total R, max DD (limits on = the same run) | 10.5%, +0.64R, +147.7R, 52.0R | 9.8%, +0.47R, +95.5R, 49.0R | 7.4%, +0.03R, +4.8R, 35.0R | 7.6%, +0.04R, +3.4R, 28.0R | — |
