"""
Lab lists and figures from data/processed/screening/mixtures_practical.csv.

    reports/results/
        lab_list_combined.csv / .md   top 100, yellow and blue together
        lab_list_yellow.csv / .md     top 50 yellow
        lab_list_blue.csv / .md       top 50 blue
    reports/figures/practical/
        cost_breakdown.png            what each leading mixture's $/t is made of
        saving_vs_mea.png             saving against 30 wt% MEA with 90 % intervals
        cost_vs_technical.png         practical cost against the capacity + energy score
        deta_calibration.png          measured DETA loadings against the old and new model

All lists are ordered by the saving against 30 wt% MEA in $ per tonne CO2 (cement and coal
averaged, paired sample by sample). Only mixtures that pass the practical filter are listed.

Run:  python -m src.viz.practical_lists
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.screening.partners import build_model, build_pool
from src.thermo.calibrated import load_core_models, load_partner_models
from src.thermo.equilibrium import compile_batch, solve
from src.viz.screening_plots import INK, INK2, MUTED, STYLE

ROOT = Path(__file__).resolve().parents[2]
SCREEN = ROOT / "data" / "processed" / "screening"
FIG = ROOT / "reports" / "figures" / "practical"
RES = ROOT / "reports" / "results"

N_COMBINED, N_COLOR = 100, 50
# Fixed order, one hue per cost component (reference categorical palette, slots 1-5).
COST_PARTS = [("energy", "Energy", "#2a78d6"), ("makeup", "Amine make-up", "#eb6834"),
              ("corrosion", "Corrosion", "#1baf7a"), ("viscosity", "Viscosity", "#e87ba4"),
              ("inventory", "First fill", "#6250d6")]
BOTH = ("cement", "coal")
CALIBRATED = set(load_partner_models())


def load() -> tuple:
    df = pd.read_csv(SCREEN / "mixtures_practical.csv", keep_default_na=False,
                     na_values=["", "nan"], low_memory=False)
    df["partners"] = df["partners"].fillna("").astype(str)
    df["warnings"] = df["warnings"].fillna("")
    df["excluded_because"] = df["excluded_because"].fillna("")
    return df, pd.read_csv(SCREEN / "amines_practical.csv").set_index("name")


def data_basis(partners: str) -> str:
    """How much of the mixture rests on measured CO2 data."""
    return "partner estimated" if set(p for p in partners.split("|") if p) - CALIBRATED else "measured"


def readable(composition: str, amines: pd.DataFrame) -> str:
    out = composition
    for code in amines.index:
        if code.startswith("L") and code in out:
            name = amines.loc[code, "chem_name"]
            if isinstance(name, str):
                out = out.replace(code, name)
    return out


def amine_set(row) -> str:
    names = [n for n in ("MEA", "MDEA", "AMP", "PZ") if row[f"wt_{n}"] > 0]
    return "+".join(sorted(names + [p for p in row["partners"].split("|") if p]))


def table(df: pd.DataFrame, amines: pd.DataFrame) -> pd.DataFrame:
    t = pd.DataFrame({
        "rank": df["rank_practical"].astype(int), "group": df["color"],
        "composition": df["composition"].map(lambda c: readable(c, amines)),
        "cost_usd_per_t": df["cost_both"], "cost_lo90": df["cost_lo90"], "cost_hi90": df["cost_hi90"],
        "saving_vs_mea": df["saving_vs_mea"], "saving_lo90": df["saving_lo90"],
        "saving_hi90": df["saving_hi90"], "p_cheaper_than_mea": df["p_cheaper_than_mea"],
        "cyclic_cement_mol_per_kg": df["cement_cyclic"], "cyclic_coal_mol_per_kg": df["coal_cyclic"],
        "q_reb_cement_gj_per_t": df["cement_q_pilot_scale"], "q_reb_coal_gj_per_t": df["coal_q_pilot_scale"],
        "makeup_kg_per_t": df["coal_makeup_kg_per_t"], "amine_price_usd_per_kg": df["price_per_kg_amine"],
        "rich_viscosity_mpas": df["mu_rich_mpas"], "corrosion_index": df["corrosion_index"],
        "oxidation_index": df["oxidation_index"], "volatility_index": df["volatility_index"],
        "pz_liquidus_C": df["pz_liquidus_C"],
        "capacity_energy_rank": df["rank_both"],
        "data_basis": df["partners"].map(data_basis),
        # first two proportions of each amine combination, so a lab can skip near-duplicates
        "diverse_pick": df.groupby(df.apply(amine_set, axis=1)).cumcount() < 2,
        "warnings": df["warnings"], "mixture_id": df["mixture_id"],
    })
    return t


def write_list(t: pd.DataFrame, stem: str, title: str, intro: str, rank_col: str = "rank"):
    t.to_csv(RES / f"{stem}.csv", index=False)
    lines = [f"# {title}", "", intro, "",
             "| # | group | composition (wt%, total 30) | cost $/t | saving vs MEA $/t [90 %] | P(cheaper) | "
             "cyclic mol/kg (cement) | Q GJ/t (cement) | make-up kg/t | corrosion | data | pick | notes |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(t.itertuples(), 1):
        lines.append(f"| {i} | {r.group} | {r.composition} | {r.cost_usd_per_t:.1f} | "
                     f"{r.saving_vs_mea:+.1f} [{r.saving_lo90:+.1f}, {r.saving_hi90:+.1f}] | "
                     f"{r.p_cheaper_than_mea:.2f} | {r.cyclic_cement_mol_per_kg:.2f} | "
                     f"{r.q_reb_cement_gj_per_t:.2f} | {r.makeup_kg_per_t:.2f} | "
                     f"{r.corrosion_index:.1f} | {r.data_basis} | {'yes' if r.diverse_pick else ''} | "
                     f"{r.warnings} |")
    (RES / f"{stem}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def fig_breakdown(df, mea):
    rows = pd.concat([df[df.color == "yellow"].nlargest(6, "saving_vs_mea"),
                      df[df.color == "blue"].nlargest(6, "saving_vs_mea"), mea.to_frame().T])
    rows = rows.iloc[::-1]
    fig, ax = plt.subplots(figsize=(9.6, 5.4))
    y = np.arange(len(rows))
    left = np.zeros(len(rows))
    for key, label, color in COST_PARTS:
        v = np.mean([rows[f"{s}_cost_{key}"].astype(float).to_numpy() for s in BOTH], axis=0)
        v = np.maximum(v, 0.0)
        ax.barh(y, v, left=left, height=0.62, color=color, edgecolor="white", linewidth=1.2, label=label)
        left += v
    ax.set_yticks(y)
    ax.set_yticklabels([f"{c}" for c in rows["composition"]], fontsize=7.5)
    ax.set_xlabel(r"running cost, \$ per tonne CO$_2$ (mean of cement and coal, all inputs at median)")
    ax.set_title("Energy is most of the running cost", loc="left")
    ax.grid(axis="y", visible=False)
    ax.legend(ncol=5, loc="upper center", bbox_to_anchor=(0.45, -0.11), fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG / "cost_breakdown.png", dpi=170)
    plt.close(fig)


def fig_saving(df):
    fig, axes = plt.subplots(1, 2, figsize=(11, 5.2), sharex=True)
    for ax, color, title in zip(axes, ("yellow", "blue"), ("Best yellow mixtures", "Best blue mixtures")):
        g = df[df.color == color].nlargest(15, "saving_vs_mea").iloc[::-1]
        y = np.arange(len(g))
        st = STYLE[color]
        ax.hlines(y, g["saving_lo90"], g["saving_hi90"], color=st["color"], lw=1.6, alpha=0.55)
        ax.scatter(g["saving_vs_mea"], y, color=st["color"], marker=st["marker"], s=34, zorder=3,
                   edgecolor="white", linewidth=0.8)
        ax.axvline(0, color=INK2, lw=0.8)
        ax.set_yticks(y)
        ax.set_yticklabels(g["composition"], fontsize=7)
        ax.set_title(title, loc="left")
        ax.grid(axis="y", visible=False)
    fig.supxlabel(r"saving against 30 wt% MEA, \$ per tonne CO$_2$ (dot = median, bar = 90 % interval)",
                  fontsize=9, color=INK2)
    fig.tight_layout()
    fig.savefig(FIG / "saving_vs_mea.png", dpi=170)
    plt.close(fig)


def fig_scatter(df):
    fig, ax = plt.subplots(figsize=(7.6, 5.0))
    for color in ("blue", "yellow", "reference"):
        g = df[df.color == color]
        st = STYLE[color]
        ax.scatter(g["score_both"], g["cost_both"], s=9 if color != "reference" else 48,
                   color=st["color"], marker=st["marker"], alpha=0.25 if color == "blue" else 1.0,
                   linewidth=0, label=st["label"], zorder=3 if color == "reference" else 2)
    offsets = {"MEA": (0, 9), "PZ": (8, -11), "AMP": (-8, 10), "MDEA": (0, 9)}
    for r in df[df.color == "reference"].itertuples():
        name = r.composition.split()[0]
        ax.annotate(name, (r.score_both, r.cost_both), xytext=offsets[name], ha="center",
                    textcoords="offset points", fontsize=8, color=INK)
    ax.set_ylim(df["cost_both"].min() - 1, df["cost_both"].min() + 14)
    ax.set_xlim(-0.40, df["score_both"].max() + 0.04)
    ax.set_xlabel("capacity + energy score (> 0 beats MEA)")
    ax.set_ylabel(r"running cost, \$ per tonne CO$_2$")
    ax.set_title("Good chemistry is not always the cheap choice", loc="left")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=3, fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG / "cost_vs_technical.png", dpi=170)
    plt.close(fig)


def fig_deta():
    data = pd.read_csv(ROOT / "data" / "interim" / "deta_chang2013.csv").query("amine == 'DETA'")
    data = data[data["w_amine"].round(2) == 0.30]
    core, _ = load_core_models()
    partners, _, _ = build_pool({k: v.smiles for k, v in core.items()}, verbose=False)
    old = build_model(next(p for p in partners if p.name == "DETA"))
    new = load_partner_models()["DETA"]
    m = 0.30 / 103.17 * 1000.0 / 0.70
    p = np.logspace(0, 3, 60)
    fig, ax = plt.subplots(figsize=(7.2, 4.8))
    for T, color, label in ((313.2, "#2a78d6", "40 °C"), (353.2, "#eb6834", "80 °C")):
        for mdl, ls in ((old, ":"), (new, "-")):
            b = compile_batch([[(mdl, m)] for _ in p])
            ax.plot(p, solve(b, np.full(len(p), T), p)["loading"], ls=ls, lw=2, color=color)
        g = data[np.isclose(data["T"], T)]
        ax.scatter(g["pCO2_kPa"], g["loading"], s=34, color=color, edgecolor="white", linewidth=0.8,
                   zorder=3, label=f"{label}, measured (Chang 2013)")
    ax.plot([], [], color=MUTED, lw=2, ls=":", label="old model (structure priors)")
    ax.plot([], [], color=MUTED, lw=2, ls="-", label="calibrated model")
    ax.set_xscale("log")
    ax.set_xlabel("CO$_2$ partial pressure, kPa")
    ax.set_ylabel("loading, mol CO$_2$ / mol DETA")
    ax.set_title("30 wt% DETA: hot solvent holds far more CO$_2$ than the old model assumed", loc="left")
    ax.legend(fontsize=8, loc="lower right")
    fig.tight_layout()
    fig.savefig(FIG / "deta_calibration.png", dpi=170)
    plt.close(fig)


def main():
    FIG.mkdir(parents=True, exist_ok=True)
    RES.mkdir(parents=True, exist_ok=True)
    df, amines = load()
    ok = df[df["practical_ok"].astype(str) == "True"].copy()
    ok["rank_practical"] = pd.to_numeric(ok["rank_practical"])
    ok = ok.sort_values("rank_practical")
    mea = df[df["composition"] == "MEA 30%"].iloc[0]
    intro = (f"Ordered by saving against 30 wt% MEA. Running cost in $ per tonne CO2 = energy + "
             f"amine make-up + first fill + corrosion + viscosity, mean of the cement and coal "
             f"scenarios; 30 wt% MEA costs ${mea.cost_both:.1f}/t on this basis. Saving > 0 means "
             f"cheaper than MEA; intervals are 90 %. Corrosion index: MEA = 1. Data: 'measured' = "
             f"every amine is calibrated on CO2 data; 'partner estimated' = a partner amine uses "
             f"structure-based estimates. Pick: the first two proportions of each amine combination, "
             f"to skip near-duplicates.")
    write_list(table(ok.head(N_COMBINED), amines), "lab_list_combined",
               f"Lab list - combined top {N_COMBINED}", intro)
    for color, stem in (("yellow", "lab_list_yellow"), ("blue", "lab_list_blue")):
        g = ok[ok.color == color].head(N_COLOR)
        write_list(table(g, amines), stem, f"Lab list - top {N_COLOR} {color}", intro)
    fig_breakdown(ok, mea)
    fig_saving(ok)
    fig_scatter(ok)
    fig_deta()
    print(f"lists -> {RES.relative_to(ROOT)} | figures -> {FIG.relative_to(ROOT)}")
    print(json.dumps(ok.head(N_COMBINED)["color"].value_counts().to_dict()))


if __name__ == "__main__":
    main()
