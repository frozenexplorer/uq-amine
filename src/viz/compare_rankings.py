"""
Before / after comparison of two screening runs (mixtures_ranked.csv), e.g. around a model
recalibration. Matches mixtures by composition and reports rank shifts overall and per colour.

Run:  python -m src.viz.compare_rankings <before.csv> [<after.csv>] [--out reports/results/x.md]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[2]
AFTER = ROOT / "data" / "processed" / "screening" / "mixtures_ranked.csv"
COLS = ["composition", "color", "rank_both", "rank_in_color", "score_both", "robust_score",
        "p_top100", "cement_cyclic", "cement_q_reb"]


def compare(before: pd.DataFrame, after: pd.DataFrame, top: int = 25) -> str:
    m = before[COLS].merge(after[COLS], on=["composition", "color"], suffixes=("_old", "_new"))
    m["d_rank"] = m["rank_both_old"] - m["rank_both_new"]          # + = moved up
    m["d_score"] = m["score_both_new"] - m["score_both_old"]
    lines = [f"Matched {len(m)} of {len(before)} / {len(after)} mixtures.",
             f"Spearman rank correlation (all): {spearmanr(m.rank_both_old, m.rank_both_new)[0]:.4f}",
             ""]
    for n in (50, 100):
        old = set(m.loc[m.rank_both_old <= n, "composition"])
        new = set(m.loc[m.rank_both_new <= n, "composition"])
        lines.append(f"Top {n} overlap: {len(old & new)}/{n}")
    lines.append("")
    for color, g in m.groupby("color"):
        lines.append(f"{color}: n={len(g)}  median score change {g.d_score.median():+.4f}  "
                     f"(in top 100: {int((g.rank_both_old <= 100).sum())} -> "
                     f"{int((g.rank_both_new <= 100).sum())})")
    def has(g, a):
        return g["composition"].str.contains(a)
    lines.append("")
    for a in ("MEA", "PZ", "MDEA", "AMP"):
        g = m[has(m, a)]
        lines.append(f"mixtures containing {a:4s}: median score change {g.d_score.median():+.4f}")
    for color in ("yellow", "blue"):
        g = m[m.color == color].sort_values("rank_in_color_new").head(top)
        lines += ["", f"### Top {top} {color} (new rank in colour | overall old -> new | score old -> new)", "",
                  "| # | composition | overall rank | score | P(top 100) |",
                  "|---|---|---|---|---|"]
        for r in g.itertuples():
            lines.append(f"| {r.rank_in_color_new} (was {r.rank_in_color_old}) | {r.composition} | "
                         f"{r.rank_both_old} -> {r.rank_both_new} | {r.score_both_old:.3f} -> "
                         f"{r.score_both_new:.3f} | {r.p_top100_old:.2f} -> {r.p_top100_new:.2f} |")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("before")
    ap.add_argument("after", nargs="?", default=str(AFTER))
    ap.add_argument("--out")
    ap.add_argument("--top", type=int, default=25)
    a = ap.parse_args()
    txt = compare(pd.read_csv(a.before), pd.read_csv(a.after), a.top)
    print(txt)
    if a.out:
        Path(a.out).write_text(txt + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
