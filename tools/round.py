"""
ONE ROUND, one command: backtest the bot, compare it with your labels on the development period,
explain every missed and every extra trade, and write the round's report.

    python tools/round.py --round 0

Writes reports/round<N>/: bot_trades_round<N>.csv, matched / missed / extra / duplicates _dev.csv,
why_not_dev.csv (missed: category + the failing condition), extra_why_dev.csv (extra: category + flags),
report_round<N>.md and report_round<N>.pdf (about 10 charts for each of the biggest categories).
A hand-written reports/round<N>/notes.md (what the bot does differently, the change tried) is put into
the report if it exists.

Only the development period is compared here. The holdout and late periods are for the final check:
    python tools/compare_labels.py --round <N> --periods dev holdout late
"""
import argparse
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import compare_labels  # noqa: E402
import explain_extra  # noqa: E402
import run_backtest  # noqa: E402
import why_not  # noqa: E402
from charts import Charter  # noqa: E402
from common import REPORTS, load_labels, load_prices  # noqa: E402

PER_CATEGORY = 10


def table(counts, total):
    lines = ["| category | trades | share |", "|---|---|---|"]
    lines += [f"| {k} | {v} | {v / max(total, 1):.0%} |" for k, v in counts.items()]
    return "\n".join(lines)


def examples(rows, k=PER_CATEGORY):
    if len(rows) <= k:
        return rows
    return rows.iloc[np.linspace(0, len(rows) - 1, k).astype(int)]


def write_report(round_no, out_dir, num_md, why, extra, notes):
    lines = [f"# Round {round_no}: the bot against your trades (development period 2024-01-05 -> 2024-07-31)", ""]
    if notes:
        lines += [notes.strip(), ""]
    lines += ["## The numbers", "", num_md, "",
              "Results are in R with no costs (the bot's default `COST = 0`). Your own R is not compared: "
              "your targets were drawn afterwards.", ""]
    lines += ["## Missed trades: why the bot didn't take yours", "",
              table(why["category"].value_counts(), len(why)), ""]
    lines += ["Each missed trade, its category, the condition that failed and the values: `why_not_dev.csv`.", ""]
    for cat in why["category"].value_counts().index[:4]:
        g = why[why["category"] == cat]
        lines += [f"**{cat}** ({len(g)}), e.g.:", ""]
        for r in g.head(3).itertuples():
            lines.append(f"- #{r.id} {r.start:%Y-%m-%d %H:%M} {r.dir} {r.order}: {r.condition}. {r.values}")
        lines.append("")
    lines += ["## Extra trades: why you wouldn't take the bot's", "",
              table(extra["category"].value_counts(), len(extra)), "",
              "A trade can have several reasons; the category is the first in the order of "
              "`tools/explain_extra.py`. All reasons, counted separately:", ""]
    flags = extra["flags"].fillna("").str.split(";").explode()
    lines += [table(flags[flags != ""].value_counts(), len(extra)), ""]
    with open(os.path.join(out_dir, f"report_round{round_no}.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def write_pdf(round_no, out_dir, df, marks, mine, why, extra, bot):
    path = os.path.join(out_dir, f"report_round{round_no}.pdf")
    mine_by_id = mine.set_index("id")
    with Charter(df, marks, path) as ch:
        ch.text_page([(16, "bold", f"Round {round_no}: example charts"),
                      (9, "normal", "For the biggest categories of missed and extra trades on the development period, "
                                    "about 10 charts each."),
                      (9, "normal", "Each page: H1 (top left), M15 (top right), M1 (bottom); purple = your trade, "
                                    "green = the bot's; your marks drawn on top."),
                      (9, "normal", "Missed: your trade the bot didn't take. Extra: the bot's trade that matches none of yours.")])
        for cat in why["category"].value_counts().index[:3]:
            for r in examples(why[why["category"] == cat]).itertuples():
                t = mine_by_id.loc[r.id]
                when = t["decision"] if pd.notna(t["decision"]) else t["fill_candle"]
                ch.page(when, f"MISSED #{r.id} ({t['dir']} {t['order']}, {t['subtype']}) {when:%Y-%m-%d %H:%M} UTC",
                        f"{cat}: {r.condition}. {str(r.values)[:420]}", mine=t.to_dict())
        for cat in extra["category"].value_counts().index[:3]:
            for r in examples(extra[extra["category"] == cat]).itertuples():
                b = bot.loc[bot["id"] == r.id].iloc[0].to_dict()
                ch.page(b["decided"], f"EXTRA bot #{r.id} ({b['dir']} {b['rule']}) {b['decided']:%Y-%m-%d %H:%M} UTC, "
                                      f"{b['outcome']} {b['R']:+.1f}R",
                        f"{cat}. Also: {r.flags}. {r.note}", bot=b)
    return path, ch.pages


def run(round_no, settings=None, pdf=True):
    t0 = time.time()
    out_dir = os.path.join(REPORTS, f"round{round_no}")
    os.makedirs(out_dir, exist_ok=True)
    df = load_prices()
    marks, mine, _ = load_labels()
    bot, _ = run_backtest.run(round_no, out_dir=out_dir, settings=settings, quiet=True)
    res = compare_labels.run(round_no, ("dev",), out_dir=out_dir, df=df, quiet=True)["dev"]
    missed = mine[mine["id"].isin(res["missed"]["id"])]
    why, _, _ = why_not.classify(missed, df, marks, settings)
    why.to_csv(os.path.join(out_dir, "why_not_dev.csv"), index=False)
    extra = explain_extra.run(round_no, "dev", df)
    notes_path = os.path.join(out_dir, "notes.md")
    notes = open(notes_path, encoding="utf-8").read() if os.path.exists(notes_path) else ""
    write_report(round_no, out_dir, res["md"], why, extra, notes)
    if pdf:
        bot = compare_labels.load_bot(os.path.join(out_dir, f"bot_trades_round{round_no}.csv"))
        write_pdf(round_no, out_dir, df, marks, mine, why, extra, bot)
    print(res["md"])
    print("\nmissed:", why["category"].value_counts().to_dict())
    print("extra:", extra["category"].value_counts().to_dict())
    print(f"round {round_no} done in {time.time() - t0:.0f}s -> {out_dir}")
    return res, why, extra


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--round", type=int, required=True)
    p.add_argument("--no-pdf", action="store_true")
    args = p.parse_args()
    run(args.round, pdf=not args.no_pdf)


if __name__ == "__main__":
    main()
