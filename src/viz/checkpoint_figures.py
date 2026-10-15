"""
Figures for the checkpoint report (reports/figures/checkpoint/):

    fig1_pipeline.png         data -> calibration -> uncertainty -> screening -> ranked list
    fig2_mea_isotherm.png     7 m MEA at 40 C: measured data vs model vs Xu's empirical fit
    fig3_capacity_vs_mea.png  like-for-like capacity relative to 7 m MEA (Dugas 2009)
    fig4_top_mixtures.png     top blue + yellow mixtures, score vs 30 wt% MEA with 90 % intervals

Run after the pipeline:  python -m src.viz.checkpoint_figures
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import FancyBboxPatch
from scipy.optimize import brentq

from src.thermo.calibrated import load_core_models
from src.thermo.equilibrium import compile_batch, solve

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports" / "figures" / "checkpoint"
INTERIM = ROOT / "data" / "interim"

INK, INK2, MUTED, GRID, AXIS = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BLUE, ORANGE, YELLOW = "#2a78d6", "#eb6834", "#eda100"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": AXIS, "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
    "axes.titlesize": 10.5, "axes.titleweight": "bold", "axes.titlecolor": INK, "axes.titlelocation": "left",
    "legend.frameon": False, "savefig.dpi": 220, "savefig.bbox": "tight", "figure.facecolor": "white",
})


def fig_pipeline():
    fig, ax = plt.subplots(figsize=(6.6, 2.7))
    ax.set_xlim(0, 100); ax.set_ylim(0, 40); ax.axis("off")
    boxes = [
        (0.5, "VLE data", "8 sources\n~510 points fitted"),
        (20.9, "Calibration", "equilibrium model\nregularised fit"),
        (41.3, "Uncertainty", "parameter spread\n+ blend margin"),
        (61.7, "Screening", "23,075 mixtures\n48 MC x 2 cases"),
        (82.1, "Ranked list", "yellow / blue\nvs 30 wt% MEA"),
    ]
    w, h, y = 17.4, 15, 21
    for i, (x, name, body) in enumerate(boxes):
        last = i == len(boxes) - 1
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=1.6",
                                    fc=BLUE if last else "white", alpha=0.12 if last else 1,
                                    ec=BLUE if last else AXIS, lw=1.6 if last else 1.0))
        if last:
            ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=1.6",
                                        fc="none", ec=BLUE, lw=1.6))
        ax.text(x + w / 2, y + h - 4, name, ha="center", va="center", fontsize=8.2, weight="bold", color=INK)
        ax.text(x + w / 2, y + 5.2, body, ha="center", va="center", fontsize=6.1, color=INK2, linespacing=1.3)
        if not last:
            ax.annotate("", xy=(x + w + 2.8, y + h / 2), xytext=(x + w + 0.2, y + h / 2),
                        arrowprops=dict(arrowstyle="-|>", color=MUTED, lw=1))
    ax.add_patch(FancyBboxPatch((26, 2), 48, 12, boxstyle="round,pad=0,rounding_size=1.6",
                                fc="#f0efec", ec=AXIS, lw=1.0, ls="--"))
    ax.text(50, 10.5, "Held-out checks (never fitted)", ha="center", fontsize=8, weight="bold", color=INK)
    ax.text(50, 5.6, "AMP+PZ (Dash) | MEA, PZ, MEA+PZ (Dugas)\nMDEA+PZ (Xu, leave-one-blend-out)",
            ha="center", va="center", fontsize=6.8, color=INK2, linespacing=1.3)
    ax.annotate("", xy=(50, y - 0.3), xytext=(50, 14.3), arrowprops=dict(arrowstyle="-|>", color=MUTED, lw=1))
    ax.text(0, 39.5, "From measured solubility data to a ranked mixture list", fontsize=10.5,
            weight="bold", color=INK, va="top")
    fig.savefig(OUT / "fig1_pipeline.png")
    plt.close(fig)


def _xu_alpha(p_kpa, T=313.15):
    """Xu (2011) Table 2-10 MEA correlation, loading per mol MEA."""
    f = lambda a: 38.6 - 12379 / T - 16.0 * a ** 2 + 3556 * a / T + 8702 * a ** 2 / T - np.log(p_kpa * 1000)
    return brentq(f, 0.01, 0.9)


def fig_mea_isotherm(models):
    ar = pd.read_csv(INTERIM / "mea_aronu2011.csv")
    ar = ar[(ar.w_amine_pct == 30) & np.isclose(ar["T"], 313.15)]
    wg = pd.read_csv(INTERIM / "mea_mdea_vle_thermoml.csv")
    wg = wg[(wg.amine == "MEA") & (wg["T"] < 315) & wg.m_amine.between(6.8, 7.2) & (wg.pCO2_kPa < 60)]
    dg = pd.read_csv(INTERIM / "dugas2009_wwc.csv")
    dg = dg[(dg.system == "MEA") & (dg.m_MEA == 7) & np.isclose(dg["T"], 313.15)]
    p = np.logspace(np.log10(0.05), np.log10(40), 120)
    b = compile_batch([[(models["MEA"], 7.0)]] * len(p))
    model = solve(b, 313.15, p)["loading"]
    xu = np.array([_xu_alpha(pi) for pi in p])

    fig, ax = plt.subplots(figsize=(6.6, 3.9))
    ax.axvspan(0.5, 5, color="#f0efec", zorder=0)
    ax.text(1.58, 0.612, "capacity window 0.5–5 kPa\nmeasured 7 m MEA: 0.30–0.33 mol/kg",
            ha="center", va="top", fontsize=7.3, color=INK2)
    ax.plot(p, xu, "--", color=ORANGE, lw=2, label="Xu (2011) empirical fit: capacity 0.50 mol/kg")
    ax.plot(p, model, "-", color=BLUE, lw=2, label="this model (calibrated): 0.34 mol/kg")
    for d, x, y, m, lab in ((ar, "pCO2_kPa", "loading", "o", "Aronu 2011 (30 wt%)"),
                            (wg, "pCO2_kPa", "loading", "s", "Wagner 2013 (~7 m)"),
                            (dg, "pCO2_kPa", "loading", "^", "Dugas 2009 (7 m, held out)")):
        ax.plot(d[x], d[y], m, ms=6, mfc="white" if m != "o" else INK, mec=INK, mew=1.1, ls="none", label=lab)
    ax.set_xscale("log")
    ax.set_xlim(0.05, 40); ax.set_ylim(0.32, 0.62)
    ax.set_xlabel("equilibrium CO$_2$ partial pressure at 40 °C (kPa, log scale)")
    ax.set_ylabel("loading (mol CO$_2$ / mol MEA)")
    ax.set_title("Three measured datasets follow the model, not Xu's steeper empirical fit")
    ax.legend(loc="lower right", fontsize=7.3, handlelength=2.2)
    fig.savefig(OUT / "fig2_mea_isotherm.png")
    plt.close(fig)


def fig_capacity(payload):
    cap = pd.DataFrame(payload["fit_report"]["Dugas2009_heldout"]["capacity_benchmark"])
    cap = cap[cap.solvent != "7 m MEA"].iloc[::-1].reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(6.6, 2.9))
    y = np.arange(len(cap))
    for i, r in cap.iterrows():
        ax.plot([r.dugas_vs_MEA, r.model_vs_MEA], [i, i], color=AXIS, lw=2, zorder=1)
    ax.plot(cap.dugas_vs_MEA, y, "o", ms=8, color=INK, label="measured (Dugas 2009, same apparatus)", zorder=3)
    ax.plot(cap.model_vs_MEA, y, "D", ms=7, color=BLUE, label="this model", zorder=3)
    pz = cap.index[cap.solvent == "8 m PZ"][0]
    ax.plot([1.70], [pz], "o", ms=8, mfc="white", mec=ORANGE, mew=1.6, zorder=3,
            label="Xu (2011) empirical fit (basis of the old caveat)")
    for i, r in cap.iterrows():
        ax.text(max(r.dugas_vs_MEA, r.model_vs_MEA) + 0.06, i,
                f"{r.model_vs_MEA:.2f} vs {r.dugas_vs_MEA:.2f}", va="center", fontsize=7.5, color=INK2)
    ax.axvline(1, color=AXIS, lw=1)
    ax.set_yticks(y); ax.set_yticklabels(cap.solvent)
    ax.grid(axis="y", visible=False)
    ax.set_xlim(0.9, 3.0); ax.set_ylim(-0.6, len(cap) - 0.4)
    ax.set_xlabel("cyclic capacity relative to 7 m MEA (40 °C, 0.5 → 5 kPa)")
    ax.set_title("PZ is valued within 4% of measurement relative to MEA")
    ax.legend(loc="lower right", fontsize=7.2)
    fig.savefig(OUT / "fig3_capacity_vs_mea.png")
    plt.close(fig)


def fig_top(df):
    lo = df[["cement_score_lo90", "coal_score_lo90"]].mean(axis=1)
    hi = df[["cement_score_hi90", "coal_score_hi90"]].mean(axis=1)
    df = df.assign(lo=lo, hi=hi)
    blue = df[df.color == "blue"].nsmallest(15, "rank_both")
    yel = df[df.color == "yellow"].nsmallest(8, "rank_both")
    rows = pd.concat([blue, yel]).reset_index(drop=True)
    pz = df.loc[df.composition == "PZ 30%", "score_both"].iloc[0]
    fig, ax = plt.subplots(figsize=(6.6, 6.6))
    y = np.arange(len(rows))[::-1].astype(float)
    y[len(blue):] -= 0.8
    for yi, r in zip(y, rows.itertuples()):
        c = BLUE if r.color == "blue" else YELLOW
        ax.plot([r.lo, r.hi], [yi, yi], color=c, lw=1.6, alpha=0.45, solid_capstyle="round")
        ax.plot(r.score_both, yi, "o", ms=6.5, color=c, mec="white", mew=1.2)
    ax.axvline(0, color=INK2, lw=1)
    ax.axvline(pz, color=MUTED, lw=1, ls=":")
    ax.text(-0.006, y[0] + 1.1, "30 wt% MEA", ha="right", fontsize=7.5, color=INK2)
    ax.text(pz + 0.006, y[0] + 1.1, "PZ alone (30 wt%)", ha="left", fontsize=7.5, color=INK2)
    ax.set_yticks(y)
    ax.set_yticklabels([f"{c}   #{k}" for c, k in zip(rows.composition, rows.rank_both)], fontsize=7.6)
    ax.grid(axis="y", visible=False)
    ax.set_ylim(y[-1] - 0.8, y[0] + 1.8); ax.set_xlim(-0.24, 0.48)
    ax.set_xlabel("score vs 30 wt% MEA (median, 90% interval; mean of cement and coal)")
    ax.set_title("DETA blends lead; the best yellow mixtures match PZ alone", pad=14)
    ax.plot([], [], "o", color=BLUE, label="blue (core + other amine), top 15")
    ax.plot([], [], "o", color=YELLOW, label="yellow (MEA/MDEA/PZ/AMP only), top 8")
    ax.legend(loc="upper center", bbox_to_anchor=(0.4, -0.08), ncol=2, fontsize=7.5)
    ax.text(-0.25, y[0] + 1.1, "mixture   overall rank", ha="right", fontsize=7, color=MUTED)
    fig.savefig(OUT / "fig4_top_mixtures.png")
    plt.close(fig)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    models, _ = load_core_models()
    payload = json.loads((ROOT / "data" / "processed" / "thermo" / "calibrated_core_amines.json").read_text())
    df = pd.read_csv(ROOT / "data" / "processed" / "screening" / "mixtures_ranked.csv")
    fig_pipeline()
    fig_mea_isotherm(models)
    fig_capacity(payload)
    fig_top(df)
    print("figures ->", OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
