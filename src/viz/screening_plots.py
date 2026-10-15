"""
Figures + shortlist tables from data/processed/screening/mixtures_ranked.csv.

    reports/figures/screening/
        pareto_<scenario>.png        capacity vs reboiler duty, all mixtures, top-50 with 90% bars
        top50_scores.png             top-50 by combined score with 90% intervals
        yellow_composition_maps.png  score over MEA/MDEA/AMP/PZ composition (yellow only)
        scenario_agreement.png       cement rank vs coal rank
        robust_vs_speculative.png    median score vs P(top 50)
        best_partners.png            best blue mixture per partner amine
    reports/results/
        shortlist_top100.csv / .md

Colours: yellow #eda100 / blue #2a78d6 (validated CVD-safe pair) + neutral grey for
the single-amine references. Marker shape is the secondary encoding (circle = yellow,
square = blue, diamond = reference), because the yellow is below 3:1 on white.

Run:  python -m src.viz.screening_plots
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm

ROOT = Path(__file__).resolve().parents[2]
SCREEN = ROOT / "data" / "processed" / "screening"
FIG = ROOT / "reports" / "figures" / "screening"
RES = ROOT / "reports" / "results"

INK, INK2, MUTED, GRID = "#0b0b0b", "#52514e", "#8c8b86", "#e6e5e1"
STYLE = {
    "yellow": dict(color="#eda100", marker="o", label="Yellow: MEA/MDEA/PZ/AMP only"),
    "blue": dict(color="#2a78d6", marker="s", label="Blue: core + other amine"),
    "reference": dict(color="#8c8b86", marker="D", label="Single amine (30 wt%)"),
}
SCEN = {"cement": "Cement flue gas (20 kPa CO$_2$)", "coal": "Coal flue gas (13 kPa CO$_2$)"}
DIVERGING = LinearSegmentedColormap.from_list(
    "bluered", ["#e34948", "#f3b3ae", "#f0efec", "#9ec5f4", "#256abf"])

plt.rcParams.update({
    "font.size": 9, "axes.edgecolor": MUTED, "axes.labelcolor": INK2, "axes.linewidth": 0.6,
    "xtick.color": INK2, "ytick.color": INK2, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.6, "grid.linestyle": "-", "axes.axisbelow": True,
    "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False,
    "axes.titlesize": 10, "axes.titlecolor": INK, "axes.titleweight": "bold",
    "figure.facecolor": "white", "savefig.facecolor": "white",
})


def load():
    df = pd.read_csv(SCREEN / "mixtures_ranked.csv")
    df["partners"] = df["partners"].fillna("")
    return df


def pareto_front(x, y):
    """Indices of non-dominated points for max x, min y."""
    order = np.lexsort((y, -x))
    front, best_y = [], np.inf
    for i in order:
        if y[i] < best_y:
            front.append(i)
            best_y = y[i]
    return np.array(front)


def short(comp: str) -> str:
    return comp.replace(" + ", " / ")


# ---------------------------------------------------------------------------
def fig_pareto(df):
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.6), sharex=True, sharey=True)
    top = df.nsmallest(50, "rank_both")
    for ax, (s, title) in zip(axes, SCEN.items()):
        ok = np.isfinite(df[f"{s}_q_reb"])
        d = df[ok]
        for color in ("blue", "yellow"):
            g = d[d.color == color]
            st = STYLE[color]
            ax.scatter(g[f"{s}_cyclic"], g[f"{s}_q_reb"], s=9, c=st["color"], marker=st["marker"],
                       alpha=0.25 if color == "blue" else 0.55, linewidths=0, label=st["label"])
        x, y = d[f"{s}_cyclic"].to_numpy(), d[f"{s}_q_reb"].to_numpy()
        fr = pareto_front(x, y)
        fr = fr[np.argsort(x[fr])]
        ax.plot(x[fr], y[fr], color=INK2, lw=1.0, zorder=3, label="Pareto front (nominal)")
        t = top[np.isfinite(top[f"{s}_q_reb"])]
        for color in ("yellow", "blue"):
            g = t[t.color == color]
            st = STYLE[color]
            gi = g[g.rank_both <= 10]
            ax.errorbar(gi[f"{s}_cyclic"], gi[f"{s}_q_reb"],
                        xerr=[gi[f"{s}_cyclic"] - gi[f"{s}_cyclic_lo90"], gi[f"{s}_cyclic_hi90"] - gi[f"{s}_cyclic"]],
                        yerr=[gi[f"{s}_q_reb"] - gi[f"{s}_q_reb_lo90"], gi[f"{s}_q_reb_hi90"] - gi[f"{s}_q_reb"]],
                        fmt="none", ecolor=INK2, elinewidth=0.6, alpha=0.5, zorder=4)
            ax.scatter(g[f"{s}_cyclic"], g[f"{s}_q_reb"], s=42, c=st["color"], marker=st["marker"],
                       edgecolors="white", linewidths=1.2, zorder=5)
        ref = d[d.color == "reference"]
        st = STYLE["reference"]
        ax.scatter(ref[f"{s}_cyclic"], ref[f"{s}_q_reb"], s=60, c=st["color"], marker=st["marker"],
                   edgecolors=INK, linewidths=0.8, zorder=6, label=st["label"])
        for _, r in ref.iterrows():
            ax.annotate(r["composition"].split()[0], (r[f"{s}_cyclic"], r[f"{s}_q_reb"]),
                        xytext=(-8, 8), textcoords="offset points", fontsize=8, color=INK,
                        ha="right", fontweight="bold",
                        bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.85))
        key = []
        for k, (_, r) in enumerate(t.nsmallest(5, "rank_both").iterrows()):
            ax.annotate(f"#{r['rank_both']}", (r[f"{s}_cyclic"], r[f"{s}_q_reb"]),
                        xytext=(22 + 4 * k, -14 - 9 * k), textcoords="offset points",
                        fontsize=7, color=INK, fontweight="bold",
                        arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.5))
            key.append(f"#{r['rank_both']}  {short(r['composition'])}")
        ax.text(0.98, 0.97, "Top 5 overall\n" + "\n".join(key), transform=ax.transAxes,
                ha="right", va="top", fontsize=7.5, color=INK2, linespacing=1.5,
                bbox=dict(boxstyle="round,pad=0.5", fc="white", ec=GRID))
        ax.set_title(title, loc="left")
        ax.set_xlabel("cyclic capacity (mol CO$_2$ / kg solvent)  → better")
        ax.set_ylim(top=np.nanquantile(df[f"{s}_q_reb"], 0.98))
    axes[0].set_ylabel("reboiler duty (GJ / t CO$_2$)  ← lower is better")
    h, l = axes[0].get_legend_handles_labels()
    h.append(plt.Line2D([], [], marker="o", ls="none", mfc="white", mec=INK2, ms=7))
    l.append("Top 50 (large); 90% intervals on top 10")
    fig.legend(h, l, loc="lower center", ncol=5, fontsize=8, markerscale=1.5)
    fig.suptitle("Every screened mixture: capacity vs regeneration energy", x=0.01, ha="left",
                 fontweight="bold", color=INK)
    fig.tight_layout(rect=(0, 0.06, 1, 0.96))
    fig.savefig(FIG / "pareto_both_scenarios.png", dpi=170)
    plt.close(fig)


def fig_top50(df):
    top = df.nsmallest(50, "rank_both").iloc[::-1]
    lo = top[[f"{s}_score_lo90" for s in SCEN]].mean(axis=1)
    hi = top[[f"{s}_score_hi90" for s in SCEN]].mean(axis=1)
    fig, ax = plt.subplots(figsize=(9, 12))
    y = np.arange(len(top))
    for color in ("yellow", "blue", "reference"):
        mk = (top.color == color).to_numpy()
        if not mk.any():
            continue
        st = STYLE[color]
        ax.hlines(y[mk], lo[mk], hi[mk], color=st["color"], lw=2, alpha=0.45)
        ax.scatter(top.score_both[mk], y[mk], s=40, c=st["color"], marker=st["marker"],
                   edgecolors="white", linewidths=1.0, zorder=3, label=st["label"])
    ax.axvline(0, color=INK2, lw=0.8)
    ax.text(0, len(top) + 0.3, " 30 wt% MEA", color=INK2, fontsize=8, va="bottom")
    ax.set_yticks(y)
    ax.set_yticklabels([f"#{r} {short(c)}" for r, c in zip(top.rank_both, top.composition)], fontsize=7)
    ax.set_ylim(-1, len(top) + 1.2)
    ax.set_xlabel("score vs 30 wt% MEA (0.5 ln capacity ratio + 0.5 ln energy ratio), "
                  "mean of both scenarios\nbar = 90% interval (parameter Monte Carlo + conformal model margin)")
    ax.set_title("Top 50 mixtures (rank before cost)", loc="left")
    ax.legend(loc="upper left", bbox_to_anchor=(0.0, -0.06), ncol=3, fontsize=8)
    ax.grid(axis="y", visible=False)
    fig.tight_layout()
    fig.savefig(FIG / "top50_scores.png", dpi=170, bbox_inches="tight")
    plt.close(fig)


def fig_yellow_maps(df):
    y = df[df.color.isin(["yellow", "reference"]) & (df.partners == "")]
    pz_levels = [0, 5, 10, 15, 20]
    fig, axes = plt.subplots(1, len(pz_levels), figsize=(17, 4.2), sharey=True)
    fin = y.score_both[np.isfinite(y.score_both)]
    norm = TwoSlopeNorm(vcenter=0, vmin=min(fin.min(), -0.05), vmax=max(fin.max(), 0.05))
    for ax, pz in zip(axes, pz_levels):
        g = y[np.isclose(y.wt_PZ, pz)]
        rest = 30 - pz
        grid = np.full((int(rest / 2.5) + 1, int(rest / 2.5) + 1), np.nan)
        for _, r in g.iterrows():
            i, j = int(round(r.wt_MDEA / 2.5)), int(round(r.wt_MEA / 2.5))
            grid[i, j] = r.score_both
        im = ax.imshow(grid, origin="lower", cmap=DIVERGING, norm=norm, aspect="auto",
                       extent=(-1.25, rest + 1.25, -1.25, rest + 1.25))
        ax.set_xlim(-1.25, 31.25)
        ax.set_ylim(-1.25, 31.25)
        ax.set_xticks([0, 10, 20, 30])
        ax.set_title(f"PZ = {pz} wt%", loc="left")
        ax.set_xlabel("MEA wt%")
        ax.grid(False)
        ax.plot([0, rest], [rest, 0], color=MUTED, lw=0.6)
        ax.text(rest * 0.55, rest * 0.75, "AMP = rest", color=MUTED, fontsize=7, rotation=-45)
        best = g.nlargest(1, "score_both")
        if len(best):
            b = best.iloc[0]
            ax.plot(b.wt_MEA, b.wt_MDEA, marker="*", ms=12, mfc="white", mec=INK, zorder=3)
    axes[0].set_ylabel("MDEA wt%   (AMP = 30 − PZ − MEA − MDEA)")
    cb = fig.colorbar(im, ax=axes, shrink=0.85, pad=0.01)
    cb.set_ticks(sorted({round(norm.vmin, 2), round(norm.vmin / 2, 2), 0.0,
                         round(norm.vmax / 2, 3), round(norm.vmax, 3)}))
    cb.set_label("score vs 30 wt% MEA\n(blue better, red worse;\neach side stretched)")
    fig.suptitle("Yellow mixtures: where in MEA / MDEA / AMP / PZ composition space the score is high"
                 "  (★ = best per panel)", x=0.01, ha="left", fontweight="bold", color=INK)
    fig.savefig(FIG / "yellow_composition_maps.png", dpi=170, bbox_inches="tight")
    plt.close(fig)


def fig_scenario_agreement(df):
    d = df.nsmallest(300, "rank_both")
    fig, ax = plt.subplots(figsize=(6.4, 6))
    for color in ("blue", "yellow", "reference"):
        g = d[d.color == color]
        if len(g):
            st = STYLE[color]
            ax.scatter(g.cement_rank, g.coal_rank, s=16, c=st["color"], marker=st["marker"],
                       alpha=0.8, linewidths=0, label=st["label"])
    lim = max(d.cement_rank.max(), d.coal_rank.max())
    ax.plot([1, lim], [1, lim], color=MUTED, lw=0.8)
    ax.set_xscale("log"); ax.set_yscale("log")
    rho = d[["cement_rank", "coal_rank"]].corr(method="spearman").iloc[0, 1]
    ov = len(set(df.nsmallest(50, "cement_rank").composition) & set(df.nsmallest(50, "coal_rank").composition))
    ax.set_title(f"Cement vs coal ranking (top 300)\nSpearman ρ = {rho:.2f}; "
                 f"{ov}/50 shared in both top-50 lists", loc="left")
    ax.set_xlabel("rank, cement scenario")
    ax.set_ylabel("rank, coal scenario")
    ax.legend(fontsize=8, loc="upper left")
    fig.tight_layout()
    fig.savefig(FIG / "scenario_agreement.png", dpi=170)
    plt.close(fig)


def fig_robust(df):
    d = df.nsmallest(400, "rank_both")
    fig, ax = plt.subplots(figsize=(7.5, 5.4))
    for color in ("blue", "yellow", "reference"):
        g = d[d.color == color]
        if len(g):
            st = STYLE[color]
            ax.scatter(g.score_both, g.p_top50, s=18, c=st["color"], marker=st["marker"],
                       alpha=0.8, linewidths=0, label=st["label"])
    key = []
    for k, (_, r) in enumerate(d.nlargest(6, "p_top50").iterrows()):
        ax.annotate(f"#{r.rank_both}", (r.score_both, r.p_top50), xytext=(-10, -16 - 7 * (k % 2)),
                    textcoords="offset points", fontsize=7, color=INK, fontweight="bold",
                    ha="right", arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.5))
        key.append(f"#{r.rank_both}  {short(r.composition)}  (P = {r.p_top50:.2f})")
    ax.text(0.98, 0.04, "Most robust picks\n" + "\n".join(key), transform=ax.transAxes,
            ha="right", va="bottom", fontsize=7.5, color=INK2, linespacing=1.5,
            bbox=dict(boxstyle="round,pad=0.5", fc="white", ec=GRID))
    ax.set_xlabel("median score vs MEA (both scenarios)")
    ax.set_ylabel("P(in top 50) across Monte Carlo samples")
    ax.set_title("Robust picks (top right) vs speculative picks (high score, low certainty)",
                 loc="left")
    ax.legend(fontsize=8, loc="upper left")
    fig.tight_layout()
    fig.savefig(FIG / "robust_vs_speculative.png", dpi=170)
    plt.close(fig)


def fig_partners(df):
    pinfo = pd.read_csv(SCREEN / "partners.csv")
    b = df[df.color == "blue"].copy()
    b["partner_list"] = b.partners.str.split("|")
    b = b.explode("partner_list")
    best = b.groupby("partner_list")["score_both"].max().nlargest(30).iloc[::-1]
    info = pinfo.set_index("name")
    fig, ax = plt.subplots(figsize=(8, 8.5))
    ax.barh(range(len(best)), best.values, color=STYLE["blue"]["color"], height=0.6)
    labels = []
    for n in best.index:
        r = info.loc[n]
        tag = "literature" if r.origin == "curated" else "library"
        labels.append(f"{n}  ({tag}, {r.site_classes.replace(',', '+')})  {r.smiles}")
    ax.set_yticks(range(len(best)))
    ax.set_yticklabels(labels, fontsize=6.5)
    ax.axvline(0, color=INK2, lw=0.8)
    ax.set_xlabel("best score of any blue mixture containing this partner")
    ax.set_title("Which partner amines make the best blue mixtures", loc="left")
    ax.grid(axis="y", visible=False)
    fig.tight_layout()
    fig.savefig(FIG / "best_partners.png", dpi=170)
    plt.close(fig)


def shortlist_tables(df, n=100):
    cols = ["rank_both", "mixture_id", "color", "composition", "partner_origin",
            "score_both", "robust_score", "p_top50",
            "cement_cyclic", "cement_cyclic_lo90", "cement_cyclic_hi90",
            "cement_q_reb", "cement_q_reb_lo90", "cement_q_reb_hi90",
            "coal_cyclic", "coal_q_reb", "cement_rank", "coal_rank", "rank_robust"]
    t = df.nsmallest(n, "rank_both")[cols]
    t.to_csv(RES / f"shortlist_top{n}.csv", index=False)
    lines = [f"# Shortlist - top {n} mixtures (before cost)", "",
             "Score > 0 means better than 30 wt% MEA (0.5 ln capacity ratio + 0.5 ln energy ratio, "
             "mean of cement and coal scenarios). Intervals are 90 %.", "",
             "| # | group | composition (wt%, total 30) | score | P(top 50) | cyclic, cement (mol/kg) | Q_reb, cement (GJ/t) |",
             "|---|---|---|---|---|---|---|"]
    for r in t.itertuples():
        lines.append(f"| {r.rank_both} | {r.color} | {r.composition} | {r.score_both:+.3f} | "
                     f"{r.p_top50:.2f} | {r.cement_cyclic:.2f} [{r.cement_cyclic_lo90:.2f}, {r.cement_cyclic_hi90:.2f}] | "
                     f"{r.cement_q_reb:.2f} [{r.cement_q_reb_lo90:.2f}, {r.cement_q_reb_hi90:.2f}] |")
    (RES / f"shortlist_top{n}.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    FIG.mkdir(parents=True, exist_ok=True)
    RES.mkdir(parents=True, exist_ok=True)
    df = load()
    fig_pareto(df)
    fig_top50(df)
    fig_yellow_maps(df)
    fig_scenario_agreement(df)
    fig_robust(df)
    fig_partners(df)
    shortlist_tables(df, 100)
    print("figures ->", FIG.relative_to(ROOT), "| tables ->", RES.relative_to(ROOT))


if __name__ == "__main__":
    main()
