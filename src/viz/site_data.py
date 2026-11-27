"""
Data for the project website (site/), generated from the pipeline outputs.

The site reads the tracked lab lists, checks.json, amines_practical.csv, first_lab_round.csv and
the Chang 2013 DETA table directly. This script writes only what is not already in a tracked file:

    site/data/mixtures.csv    every mixture that passes the practical filter (20,475 rows), slim:
                              rank, saving, capacity, duty. Feeds the capacity-energy scatter.
    site/data/featured.csv    lab-list columns plus the cost split for the ~220 mixtures the site
                              shows in detail (lab lists, first lab round, references).
    site/data/site_data.json  counts, the DETA before/after curves from the old (structure-based)
                              and calibrated models, October's ranking against today's, and the
                              PZ heat stress test on a grid of extra heat.

Run after the practical stage:  python -m src.viz.site_data   (run_all.py does this)
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.screening.partners import build_model, build_pool
from src.screening.practical import (CORROSION_FLAG, KJ_PER_MOL_TO_GJ_PER_T, MAX_RICH_VISCOSITY, SCALARS,
                                     MIN_VENDORS, PZ_LIQUIDUS_WARN_C, SCENARIOS, amine_table,
                                     energy_check, load_availability, pz_heat_stress)
from src.screening.process import evaluate
from src.thermo.calibrated import load_core_models, load_partner_models
from src.thermo.equilibrium import compile_batch, solve
from src.viz.practical_lists import BOTH, load, table

ROOT = Path(__file__).resolve().parents[2]
SCREEN = ROOT / "data" / "processed" / "screening"
OUT = ROOT / "site" / "data"
OCTOBER = ROOT / "reports" / "results" / "archive" / "shortlist_top100_2026-10-15.csv"
COST_KEYS = ("energy", "makeup", "inventory", "corrosion", "viscosity")


def mixtures(ok: pd.DataFrame) -> pd.DataFrame:
    """Slim table of every practical mixture, for the scatter. Library partners keep their code
    (L0255 ...); the site names them from amines_practical.csv."""
    return pd.DataFrame({
        "mixture_id": ok["mixture_id"], "rank": ok["rank_practical"].astype(int), "group": ok["color"],
        "composition": ok["composition"], "saving_vs_mea": ok["saving_vs_mea"],
        "cyclic_cement_mol_per_kg": ok["cement_cyclic"], "q_reb_cement_gj_per_t": ok["cement_q_pilot_scale"],
        "capacity_energy_rank": ok["rank_both"],
    })


def featured(ok: pd.DataFrame, amines: pd.DataFrame) -> pd.DataFrame:
    """Lab-list columns plus the cost split (mean of scenarios) for every mixture the site shows in
    detail: the three lab lists, the first lab round and the four single-amine references."""
    ids = set(ok.nsmallest(100, "rank_practical")["mixture_id"])
    for color in ("yellow", "blue"):
        ids |= set(ok[ok["color"] == color].nsmallest(50, "rank_practical")["mixture_id"])
    ids |= set(ok[ok["color"] == "reference"]["mixture_id"])
    names = amines["chem_name"].dropna().to_dict()
    readable_ok = ok["composition"]
    for code, name in names.items():
        if code.startswith("L"):
            readable_ok = readable_ok.str.replace(code, name, regex=False)
    lab = pd.read_csv(ROOT / "reports" / "results" / "first_lab_round.csv")
    missing = set(lab["composition"]) - set(readable_ok)
    assert not missing, f"first_lab_round.csv names mixtures that are not in the results: {missing}"
    ids |= set(ok.loc[readable_ok.isin(lab["composition"]), "mixture_id"])
    sel = ok[ok["mixture_id"].isin(ids)]
    out = table(sel, amines)
    for k in COST_KEYS:
        out[f"cost_{k}"] = np.mean([sel[f"{s}_cost_{k}"].astype(float).to_numpy() for s in BOTH], axis=0)
    return out


def deta_story() -> dict:
    """Loading curves of DETA from the October model (structure priors) and the calibrated model,
    the error of each on Chang (2013), and the cyclic capacity each gives in the cement case."""
    core, _ = load_core_models()
    partners, _, _ = build_pool({k: v.smiles for k, v in core.items()}, verbose=False)
    old = build_model(next(p for p in partners if p.name == "DETA"))
    new = load_partner_models()["DETA"]
    data = pd.read_csv(ROOT / "data" / "interim" / "deta_chang2013.csv").query("amine == 'DETA'")

    def molality(w):
        return w / 103.17 * 1000.0 / (1.0 - w)

    p = np.logspace(-0.5, 3.0, 48)
    curves = []
    for w in (0.20, 0.30, 0.40):
        for T in (313.15, 353.15, 393.15):
            row = {"w": w, "T_C": round(T - 273.15), "p_kpa": p.round(4).tolist()}
            for tag, mdl in (("old", old), ("calibrated", new)):
                b = compile_batch([[(mdl, molality(w))] for _ in p])
                row[tag] = np.round(solve(b, np.full(len(p), T), p)["loading"], 4).tolist()
            curves.append(row)

    err = {}
    for tag, mdl in (("old", old), ("calibrated", new)):
        b = compile_batch([[(mdl, m)] for m in data["m_amine"]])
        pred = solve(b, data["T"].to_numpy(), data["pCO2_kPa"].to_numpy())["loading"]
        resid = pred - data["loading"].to_numpy()
        hot = np.isclose(data["T"].to_numpy(), 353.2, atol=0.5)
        err[tag] = {"mae": float(np.mean(np.abs(resid))), "mae_80C": float(np.mean(np.abs(resid[hot]))),
                    "max_abs_80C": float(np.max(np.abs(resid[hot])))}

    sc = SCENARIOS["cement"]
    cap = {}
    for tag, mdl in (("old", old), ("calibrated", new), ("MEA", core["MEA"])):
        mw = 103.17 if tag != "MEA" else core["MEA"].mw
        m = 0.30 / mw * 1000.0 / 0.70
        r = evaluate(compile_batch([[(mdl, m)]]), sc)
        cap[tag] = {"cyclic_mol_per_kg": float(r["cyclic_mol_per_kg"][0]),
                    "rich_loading": float(r["rich_loading"][0]), "lean_loading": float(r["lean_loading"][0])}
    return {"curves": curves, "error": err, "capacity_30wt_cement": cap,
            "scenario": {"T_abs_C": sc["T_abs"] - 273.15, "p_feed_kpa": sc["p_feed"],
                         "T_strip_C": sc["T_strip"] - 273.15, "p_lean_kpa": sc["p_lean"]},
            "n_points": int(len(data))}


def october_vs_now(df: pd.DataFrame) -> dict:
    """October's capacity + energy top 100 (before DETA, DEA and MPA had data), with today's ranks."""
    old = pd.read_csv(OCTOBER)
    now = df.set_index("composition")
    rows = []
    for r in old.head(100).itertuples():
        n = now.loc[r.composition] if r.composition in now.index else None
        rows.append({"composition": r.composition, "color": r.color, "rank_october": int(r.rank_both),
                     "rank_now": int(n["rank_both"]) if n is not None else None,
                     "rank_practical_now": (int(n["rank_practical"]) if n is not None
                                            and pd.notna(n["rank_practical"]) else None)})
    top_now = df.nsmallest(100, "rank_both")["composition"]
    return {"rows": rows,
            "deta_in_top100_october": int(old.head(100)["composition"].str.contains("DETA").sum()),
            "deta_in_top100_now": int(top_now.str.contains("DETA").sum()),
            "n_mixtures_now": int(len(df))}


def stress_grid(df_full: pd.DataFrame) -> dict:
    """The PZ heat stress test of practical.py on a grid of extra heat (nominal inputs)."""
    df = pd.read_csv(SCREEN / "mixtures_ranked.csv", keep_default_na=False, na_values=["", "nan"])
    df["partners"] = df["partners"].fillna("").astype(str)
    df["partner_wt"] = df["partner_wt"].fillna("").astype(str)
    t = amine_table(pd.read_csv(SCREEN / "partners.csv"), load_availability())
    mc = np.load(SCREEN / "mc_samples.npz")
    cap = {s: mc[f"{s}_cyclic"].astype(float) for s in SCENARIOS}
    q = {s: mc[f"{s}_q_reb"].astype(float) for s in SCENARIOS}
    mea_idx = int(np.flatnonzero((df["composition"] == "MEA 30%").to_numpy())[0])
    ok = df[["mixture_id"]].merge(df_full[["mixture_id", "practical_ok"]], how="left")["practical_ok"]
    ok = (ok.astype(str) == "True").to_numpy()

    energy = energy_check()
    core, _ = load_core_models()
    n_pz, n_amp = 13.0 / core["PZ"].mw, 27.0 / core["AMP"].mw
    f_pz = 2.0 * n_pz / (2.0 * n_pz + n_amp)
    m = energy["model"]["coal"]
    fit = json.loads((ROOT / "data" / "processed" / "thermo" / "calibrated_core_amines.json").read_text())
    full = -fit["fit_report"]["Hilliard2008_heats"]["bias_at_120C_vs_PZ_N_fraction"]["slope"]
    allowed = energy["pz_heat_uplift_allowed_by_benchmarks"]

    grid = sorted(set(np.round(np.arange(0.0, 26.0, 1.0), 2).tolist() + [round(allowed, 2), round(full, 2)]))
    pts = []
    for u in grid:
        r = pz_heat_stress(df, t, cap, q, mea_idx, ok, u)
        pts.append({"uplift": u, "pz30_saving": r["pz_30_saving"], "n_cheaper": r["n_cheaper_than_mea"],
                    "best_yellow": r["best"]["yellow"], "best_blue": r["best"]["blue"],
                    "kept_top20": r["kept_in_top_n"],
                    "cesar1_mea_ratio": (m["q_cesar1_gj_per_t"] + u * KJ_PER_MOL_TO_GJ_PER_T * f_pz)
                    / m["q_mea_gj_per_t"]})
        print(f"  extra PZ heat {u:5.2f} kJ/mol: PZ 30% saves {r['pz_30_saving']:+.2f} $/t, "
              f"{r['n_cheaper_than_mea']} cheaper than MEA")
    return {"points": pts, "allowed_by_benchmarks": allowed, "full_calorimetry": full,
            "published_ratio_range": [min(energy["measured_ratio"].values()),
                                      max(energy["measured_ratio"].values())],
            "n_cheaper_base": pts[0]["n_cheaper"]}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    df, amines = load()
    ok = df[df["practical_ok"].astype(str) == "True"].copy()
    ok["rank_practical"] = pd.to_numeric(ok["rank_practical"])
    ok = ok.sort_values("rank_practical")

    mix = mixtures(ok)
    mix.to_csv(OUT / "mixtures.csv", index=False, float_format="%.4g")
    feat = featured(ok, amines)
    feat.to_csv(OUT / "featured.csv", index=False, float_format="%.5g")

    mea = ok[ok["composition"] == "MEA 30%"].iloc[0]
    counts = {"n_screened": int(len(df)), "n_practical": int(len(ok)),
              "n_practical_by_color": ok["color"].value_counts().to_dict(),
              "n_cheaper_median": int((ok["saving_vs_mea"] > 0).sum()),
              "n_excluded_reactive": int(df["excluded_because"].str.contains("reactive").sum()),
              "n_excluded_vendors": int(df["excluded_because"].str.contains("purchasable").sum()),
              "mea_cost_usd_per_t": float(mea["cost_both"]),
              "mea_cyclic_cement": float(mea["cement_cyclic"]),
              "mea_q_reb_cement": float(mea["cement_q_pilot_scale"]),
              "mea_makeup_kg_per_t": float(mea["coal_makeup_kg_per_t"]),
              "mea_rank": int(mea["rank_practical"]),
              "n_score_lo90_beats_mea_both": int(((ok["cement_score_lo90"] > 0) & (ok["coal_score_lo90"] > 0)).sum()),
              "cost_lo90_positive": [{"composition": r.composition, "saving": float(r.saving_vs_mea),
                                      "saving_lo90": float(r.saving_lo90), "rank": int(r.rank_practical)}
                                     for r in ok[ok["saving_lo90"] > 0].sort_values("saving_lo90", ascending=False).itertuples()
                                     if r.composition != "MEA 30%"],
              "flag_liquidus_C": PZ_LIQUIDUS_WARN_C, "flag_corrosion_index": CORROSION_FLAG,
              "min_vendors": MIN_VENDORS, "max_rich_viscosity_mpas": MAX_RICH_VISCOSITY}
    print("DETA curves ...")
    deta = deta_story()
    print("October vs now ...")
    octo = october_vs_now(df)
    print("PZ heat stress grid ...")
    stress = stress_grid(df)
    data = {"counts": counts, "scalars": {k: list(v) for k, v in SCALARS.items()},
            "deta": deta, "october": octo, "pz_heat_stress": stress}
    (OUT / "site_data.json").write_text(json.dumps(data, separators=(",", ":")))
    print(f"site data -> {OUT.relative_to(ROOT)} ({len(mix)} mixtures)")


if __name__ == "__main__":
    main()
