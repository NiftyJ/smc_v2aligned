# Sanity check (brief 2d): are the prices and the labels on the same clock?

| check | passed | share |
|---|---|---|
| market + half: entry inside the clicked candle's M1 high-low (the brief's check) | 6 / 69 | 8.7% |
| market: entry inside the clicked candle's M1 high-low | 3 / 4 | 75.0% |
| half: the trigger close (`level`) = the close of the clicked candle (to 0.5 cent) | 65 / 65 | 100.0% |
| half: entry = (trigger close + stop) / 2, i.e. halfway back to the stop | 65 / 65 | 100.0% |
| filled limits: the entry was reached in the clicked candle | 47 / 133 | 35.3% |
| trades with M1 data at their candle | 235 / 235 | 100.0% |

The trigger close of every half order, with the labels moved by whole hours:

| shift | trigger close = clicked candle's close |
|---|---|
| -3 h | 0% |
| -2 h | 0% |
| -1 h | 0% |
| +0 h | 100% |
| +1 h | 0% |
| +2 h | 0% |
| +3 h | 0% |

Filled limit orders: when price first reached the entry, counted from the candle you clicked:

| first reached | trades |
|---|---|
| in the clicked candle | 46 (35%) |
| 1-15 min after it | 39 (29%) |
| 16-60 min after | 21 (16%) |
| 1-8 h after | 21 (16%) |
| more than 8 h after | 6 (5%) |
