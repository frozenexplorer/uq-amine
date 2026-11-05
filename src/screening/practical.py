"""
Practical stage: turn the screened mixtures into a running cost in $ per tonne CO2.

Capacity and regeneration energy (from run_screen.py) are combined with amine price and the
physical factors, all on one scale, so a mixture can be compared directly with 30 wt% MEA:

    cost = energy + make-up + inventory + corrosion + viscosity            [$ / t CO2]

    energy     Q_reb x heat price. Q_reb is the screening value scaled so that 30 wt% MEA
               equals the pilot-plant duty (the short-cut model reads about 40 % low in
               absolute terms; the scale keeps the ratios between solvents).
    make-up    amine lost per t CO2 x price, per component:
                 (FLOOR + OX_MEA x oxidation index) x (w_i / 30) x (C_MEA / C)
                 + vapour loss after the water wash.
               The floor and the oxidation term are set so that MEA = 1.5 kg/t and CESAR1
               (index 0.11) = 0.43 kg/t, against 0.45 kg/t measured over 400 days.
               Solvent circulation carries oxygen, hence the C_MEA / C factor.
    inventory  first fill, annualised. Small, kept for completeness.
    corrosion  CORROSION_MEA x mass-weighted corrosion index (MEA = 1).
    viscosity  VISCOSITY_BASE x ((mu_rich / mu_MEA)^0.35 - 1): thicker solvent needs more
               packing and heat-exchanger area.

Every amine-level input carries a low / median / high range and every scalar a range, sampled
with the same common-random-number idea as the screen: an amine keeps its draw across all
mixtures in a sample, so differences between mixtures stay meaningful.

Practical filter (a mixture leaves the list, with the reason recorded):
    * contains a chemically unsuitable partner (reactive group; see REACTIVE_SMARTS)
    * contains a partner with fewer than MIN_VENDORS vendors on PubChem
    * rich viscosity above MAX_RICH_VISCOSITY

Inputs:  data/processed/screening/{mixtures_ranked.csv, partners.csv, mc_samples.npz}
         data/processed/practical/{amine_inputs.csv, partner_availability.csv, viscosity_fit.json}
Outputs: data/processed/screening/{mixtures_practical.csv, amines_practical.csv}
         data/processed/practical/checks.json   energy benchmark + sensitivity of the lists
Run:     python -m src.screening.practical
"""

from __future__ import annotations

import json
import zlib
from pathlib import Path

import numpy as np
import pandas as pd
from rdkit import Chem
from scipy.stats import norm

from src.thermo.calibrated import load_core_models
from src.thermo.chemistry import CORE_NAMES, MW_CO2, core_amines
from src.thermo.equilibrium import compile_batch

from .process import KJ_PER_MOL_TO_GJ_PER_T, SCENARIOS, evaluate

ROOT = Path(__file__).resolve().parents[2]
SCREEN = ROOT / "data" / "processed" / "screening"
INPUTS = ROOT / "data" / "processed" / "practical"

SEED = 2026
TOTAL_WT = 30.0
MIN_VENDORS = 5
MAX_RICH_VISCOSITY = 30.0   # mPa s at 40 C, the limit used in published solvent screening
PZ_LIQUIDUS_WARN_C = 25.0   # unloaded solvent that solidifies above room temperature is flagged
CORROSION_FLAG = 2.0        # index above which carbon steel needs inhibitor or stainless

# (low, median, high) = 90 % range. $ and kg per tonne CO2 unless stated.
SCALARS = {
    "q_mea_pilot": (3.5, 3.7, 4.1),        # GJ/t, 30 wt% MEA, pilot and simulation literature
    "heat_cement": (2.0, 6.0, 10.0),       # $/GJ: waste heat to gas boiler (assumption)
    "heat_coal": (2.5, 3.4, 5.0),          # $/GJ: LLNL lost-generation value of the steam
    "makeup_floor": (0.2, 0.3, 0.5),       # kg/t, losses that do not depend on oxidation
    "makeup_ox_mea": (0.5, 1.2, 2.7),      # kg/t, oxidative and thermal loss of MEA
    "vapour_mea_coal": (0.005, 0.02, 0.1),  # kg/t after a 98 % water wash, 13 kPa flue gas; from
                                            # 0.0056 kPa over lean 7 m MEA at 40 C (Hilliard 2008)
    "corrosion_mea": (0.3, 1.0, 3.0),      # $/t (assumption)
    "viscosity_base": (1.0, 3.0, 6.0),     # $/t (assumption)
}
VISCOSITY_EXPONENT = 0.35
INVENTORY_HOLDUP_H = 1.0     # solvent inventory, hours of circulation
CAPITAL_CHARGE = 0.10        # per year
OPERATING_H = 7000.0
TONNE_MOL = 1e6 / MW_CO2

# Groups that hydrolyse, polymerise or react with amines and CO2 in a hot stripper.
REACTIVE_SMARTS = {
    "epoxide": "[OX2r3]1[#6r3][#6r3]1",
    "aziridine": "[NX3r3]1[#6r3][#6r3]1",
    "nitrile": "[CX2]#N",
    "aldehyde": "[CX3H1](=O)[#6]",
    "ester": "[CX3](=O)[OX2H0][#6]",
    "acetal/ketal": "[CX4]([OX2])([OX2])",
    "alkyne": "C#C",
    "vinyl": "[CX3]=[CX3]",
}


def reactive_group(smiles: str) -> str | None:
    mol = Chem.MolFromSmiles(smiles)
    for name, sma in REACTIVE_SMARTS.items():
        if mol.HasSubstructMatch(Chem.MolFromSmarts(sma)):
            return name
    return None


def load_availability() -> pd.DataFrame:
    path = INPUTS / "partner_availability.csv"
    if path.exists():
        return pd.read_csv(path).drop_duplicates("smiles").set_index("smiles")
    return pd.DataFrame(columns=["cid", "title", "iupac_name", "n_vendors"])


def purchasable(smiles: str, avail: pd.DataFrame) -> bool:
    """True when the partner is chemically suitable and on enough vendor catalogues."""
    if reactive_group(smiles) is not None:
        return False
    if len(avail) == 0:
        return True                  # no lookup yet: do not filter
    return smiles in avail.index and avail.loc[smiles, "n_vendors"] >= MIN_VENDORS


def _draw(key: str, low, med, high, k: int) -> np.ndarray:
    """Two-piece lognormal with the given median and 90 % range. Stratified (one draw per
    equal-probability slice, shuffled per key), so 48 samples reproduce the median and range
    instead of drifting with the luck of the draw. Sample 0 is the nominal case, as in the
    screen."""
    d = np.full(k, float(med))
    if k > 1 and high > low:
        rng = np.random.default_rng([SEED, zlib.crc32(key.encode())])
        z = norm.ppf((rng.permutation(k - 1) + 0.5) / (k - 1))
        sd = np.where(z > 0, np.log(high / med), np.log(med / low)) / 1.645
        d[1:] = med * np.exp(sd * z)
    return d


def amine_class(sites: str) -> str:
    classes = sites.split(",")
    if len(classes) >= 2 and any(c.startswith("primary") for c in classes):
        return "polyamine"
    first = classes[0]
    if first.startswith("primary"):
        return "primary"
    if first == "secondary_ring":
        return "secondary_ring"
    return "secondary" if first.startswith("secondary") else "tertiary"


def amine_table(pinfo: pd.DataFrame, avail: pd.DataFrame) -> pd.DataFrame:
    """One row per amine with prices, indices, viscosity coefficient, sites and availability."""
    src = pd.read_csv(INPUTS / "amine_inputs.csv").set_index("amine")
    visc = json.loads((INPUTS / "viscosity_fit.json").read_text())
    rows = []
    core = core_amines()
    n_sites_core = {"MEA": 1, "MDEA": 1, "AMP": 1, "PZ": 2}
    vp_ref = _vapour_reference(pinfo)
    for name in CORE_NAMES:
        rows.append({"name": name, "smiles": core[name].smiles, "mw": core[name].mw,
                     "n_sites": n_sites_core[name], "cls": "core",
                     **src.loc[name].to_dict(), "visc_a": visc["a"][name],
                     "volatility": vp_ref[name], "tier": "commodity"})
    for r in pinfo.itertuples():
        cls = amine_class(r.site_classes)
        c = src.loc[f"class:{cls}"].to_dict()
        lib = src.loc["class:library"].to_dict()
        row = {"name": r.name, "smiles": r.smiles, "mw": r.mw, "n_sites": r.n_sites, "cls": cls}
        if r.name in src.index:
            row.update(src.loc[r.name].to_dict())
            row["tier"] = "commodity" if "market" in str(src.loc[r.name, "price_basis"]) else "specialty"
            row["visc_a"] = visc["a"].get(r.name, c["visc_a"])
        else:
            row.update({k: c[k] for k in c if not k.startswith("price")})
            row.update({k: lib[k] for k in lib if k.startswith("price")})
            row["tier"] = "catalogue"
        row["volatility"] = vp_ref[r.name]
        rows.append(row)
    t = pd.DataFrame(rows).set_index("name")
    t["reactive_group"] = t["smiles"].map(reactive_group)
    t["n_vendors"] = t["smiles"].map(avail["n_vendors"]) if len(avail) else np.nan
    t["chem_name"] = t["smiles"].map(avail["title"]) if len(avail) else None
    return t


def _vapour_reference(pinfo: pd.DataFrame) -> dict:
    """Volatility relative to MEA. PZ is measured: lean 5 m PZ against lean 7 m MEA at 40 C
    (Hilliard 2008). AMP and MDEA follow the loaded-solution order of Nguyen et al. (2010).
    Partners use OPERA vapour pressure where it exists, otherwise the boiling point."""
    out = {"MEA": 1.0, "MDEA": 0.05, "AMP": 2.0, "PZ": 0.45}
    log_vp_mea = np.log10(0.4)           # mmHg at 25 C, handbook value
    bp_mea = 170.0
    for r in pinfo.itertuples():
        lv = getattr(r, "logvp_pred", np.nan)
        if pd.notna(lv):
            out[r.name] = float(10.0 ** (lv - log_vp_mea))
        else:
            bp = getattr(r, "bp_lit_c", np.nan)
            out[r.name] = float(10.0 ** (-(bp - bp_mea) / 40.0)) if pd.notna(bp) else 1.0
    return out


def composition_matrix(df: pd.DataFrame, names: list) -> np.ndarray:
    """(n_mix, n_amine) wt%."""
    idx = {n: i for i, n in enumerate(names)}
    W = np.zeros((len(df), len(names)))
    for j, n in enumerate(CORE_NAMES):
        W[:, idx[n]] = df[f"wt_{n}"].to_numpy()
    for i, (ps, ws) in enumerate(zip(df["partners"], df["partner_wt"])):
        if ps:
            for p, w in zip(ps.split("|"), str(ws).split("|")):
                W[i, idx[p]] = float(w)
    return W


def compute(df: pd.DataFrame, t: pd.DataFrame, cap: dict, q: dict, mea_idx: int,
            overrides: dict | None = None, pz_heat_uplift: float = 0.0) -> pd.DataFrame:
    names = list(t.index)
    k = next(iter(cap.values())).shape[1]
    W = composition_matrix(df, names)
    frac = W / TOTAL_WT
    sc = {n: _draw(n, *v, k) for n, v in SCALARS.items()}
    for n, v in (overrides or {}).items():
        sc[n] = np.full(k, float(v))

    # amine-level draws: (n_amine, k)
    def draws(field):
        return np.vstack([_draw(f"{n}:{field}", r[f"{field}_low"], r[f"{field}_med"],
                                r[f"{field}_high"], k) for n, r in t.iterrows()])

    price = draws("price")
    oxid = draws("oxidation")
    corr = draws("corrosion")
    vol = t["volatility"].to_numpy()[:, None]

    # viscosity: nominal, from the rich end of the cement scenario
    mw = t["mw"].to_numpy()
    n_mol = W / mw                                     # mol amine per 100 g solvent
    n_N = n_mol @ t["n_sites"].to_numpy()
    alpha_rich = (df["cement_rich_loading"].to_numpy() * n_mol.sum(axis=1)) / n_N
    alpha_lean = (df["cement_lean_loading"].to_numpy() * n_mol.sum(axis=1)) / n_N
    visc = json.loads((INPUTS / "viscosity_fit.json").read_text())
    a_w = (W / 100.0) @ t["visc_a"].to_numpy()
    mu_rich = visc["mu_water_40C_mpas"] * np.exp(a_w * (1.0 + visc["b"] * alpha_rich))

    f_pz = 2.0 * n_mol[:, names.index("PZ")] / n_N       # PZ share of the basic N
    out = df[["mixture_id"]].copy()
    out["alpha_rich_per_N"] = alpha_rich
    out["alpha_lean_per_N"] = alpha_lean
    out["mu_rich_mpas"] = mu_rich
    out["corrosion_index"] = frac @ t["corrosion_med"].to_numpy()
    out["oxidation_index"] = frac @ t["oxidation_med"].to_numpy()
    out["volatility_index"] = frac @ t["volatility"].to_numpy()
    out["price_per_kg_amine"] = frac @ t["price_med"].to_numpy()
    sle = pd.read_csv(ROOT / "data" / "interim" / "hilliard2008_pz_sle.csv")
    out["pz_liquidus_C"] = np.where(df["wt_PZ"] > 0, np.interp(df["wt_PZ"] / 100.0, sle["w_PZ"], sle["liquidus_C"]), np.nan)

    total = {}
    comp = {}
    for s in SCENARIOS:
        c = cap[s]
        g = q[s] + pz_heat_uplift * KJ_PER_MOL_TO_GJ_PER_T * f_pz[:, None]
        kappa = sc["q_mea_pilot"] / g[mea_idx]               # (k,) pilot / model for MEA
        q_real = g * kappa
        heat = sc[f"heat_{s}"]
        energy = q_real * heat
        circ = c[mea_idx] / c                                # solvent circulation vs MEA
        flue = 13.0 / SCENARIOS[s]["p_feed"]                 # less gas per t CO2 at higher pCO2
        loss = (sc["makeup_floor"] + sc["makeup_ox_mea"] * (frac @ oxid)) * circ
        price_mix = frac @ price
        makeup_oxid = (sc["makeup_floor"] * price_mix + sc["makeup_ox_mea"] * (frac @ (oxid * price))) * circ
        vapour = sc["vapour_mea_coal"] * flue * (frac @ (vol * price))
        vapour_kg = sc["vapour_mea_coal"] * flue * (frac @ vol)
        makeup = makeup_oxid + vapour
        solvent_kg = TONNE_MOL / c                           # kg solvent per t CO2
        inventory = solvent_kg * (TOTAL_WT / 100.0) * price_mix * INVENTORY_HOLDUP_H \
            * CAPITAL_CHARGE / OPERATING_H
        corrosion = sc["corrosion_mea"] * (frac @ corr)
        viscosity = sc["viscosity_base"] * ((mu_rich[:, None] / mu_rich[mea_idx]) ** VISCOSITY_EXPONENT - 1.0)
        tot = energy + makeup + inventory + corrosion + viscosity
        total[s] = tot
        comp[s] = {"energy": energy, "makeup": makeup, "inventory": inventory,
                   "corrosion": corrosion, "viscosity": viscosity}
        out[f"{s}_q_pilot_scale"] = q_real[:, 0]
        out[f"{s}_makeup_kg_per_t"] = (loss + vapour_kg)[:, 0]
        for name, arr in comp[s].items():
            out[f"{s}_cost_{name}"] = arr[:, 0]
        out[f"{s}_cost_total"] = tot[:, 0]

    both = 0.5 * (total["cement"] + total["coal"])
    saving = both[mea_idx][None, :] - both                   # > 0 is cheaper than MEA
    out["cost_both"] = both[:, 0]                            # nominal: every input at its median
    out["cost_lo90"] = np.nanquantile(both, 0.05, axis=1)
    out["cost_hi90"] = np.nanquantile(both, 0.95, axis=1)
    out["saving_vs_mea"] = np.nanmedian(saving, axis=1)
    out["saving_lo90"] = np.nanquantile(saving, 0.05, axis=1)
    out["saving_hi90"] = np.nanquantile(saving, 0.95, axis=1)
    out["p_cheaper_than_mea"] = np.mean(saving > 0, axis=1)
    return out


def flags(df: pd.DataFrame, t: pd.DataFrame) -> pd.DataFrame:
    """Hard exclusions (`excluded_because`) and soft warnings (`warnings`)."""
    excl, warn = [], []
    tiers = t["tier"].to_dict()
    react = t["reactive_group"].to_dict()
    vend = t["n_vendors"].to_dict()
    for r in df.itertuples():
        e, w = [], []
        for p in (r.partners.split("|") if r.partners else []):
            if isinstance(react[p], str):
                e.append(f"{p} has a reactive group ({react[p]})")
            if tiers[p] == "catalogue" and not (pd.notna(vend[p]) and vend[p] >= MIN_VENDORS):
                e.append(f"{p} not purchasable")
        if r.mu_rich_mpas > MAX_RICH_VISCOSITY:
            e.append(f"rich viscosity {r.mu_rich_mpas:.0f} mPa s")
        if r.pz_liquidus_C >= PZ_LIQUIDUS_WARN_C:
            w.append(f"fresh solvent solidifies below about {r.pz_liquidus_C:.0f} C: prepare and store warm")
        if r.corrosion_index >= CORROSION_FLAG:
            w.append("corrosive to carbon steel: needs inhibitor or stainless")
        excl.append("; ".join(e))
        warn.append("; ".join(w))
    return pd.DataFrame({"excluded_because": excl, "warnings": warn}, index=df.index)


def rank(df: pd.DataFrame) -> pd.DataFrame:
    df["practical_ok"] = df["excluded_because"] == ""
    # rank on the saving against MEA: it is paired sample by sample, so uncertainty shared by
    # every mixture (heat price, pilot duty) cancels and only real differences remain
    ok = df["practical_ok"] & df["saving_vs_mea"].notna()
    df["rank_practical"] = pd.NA
    df.loc[ok, "rank_practical"] = df.loc[ok, "saving_vs_mea"].rank(ascending=False, method="first").astype(int)
    df["rank_practical_in_color"] = pd.NA
    for color, g in df[ok].groupby("color"):
        df.loc[g.index, "rank_practical_in_color"] = g["saving_vs_mea"].rank(ascending=False, method="first").astype(int)
    return df


# Reboiler duty of CESAR1 (AMP + PZ) against 30 wt% MEA from the same study, GJ/t.
ENERGY_BENCHMARK = {
    "Verhaeghe et al. 2025 (PCCC-8), equal stripper pressure": (3.70, 3.92),
    "Mertdag thesis, ProMax simulation": (2.80, 3.50),
    "Frontiers in Energy Research 2024, biomass CHP": (2.86, 3.61),
}


def energy_check() -> dict:
    """Does the short-cut duty reproduce the measured CESAR1 : MEA ratio?"""
    core, _ = load_core_models()

    def mix(comp):
        water = 100.0 - sum(comp.values())
        return [(core[n], w / core[n].mw * 1000.0 / water) for n, w in comp.items()]

    b = compile_batch([mix({"MEA": 30.0}), mix({"AMP": 27.0, "PZ": 13.0})])
    out = {"model": {}}
    for s, sc in SCENARIOS.items():
        r = evaluate(b, sc)
        q = r["q_reb_gj_per_t"]
        out["model"][s] = {"q_mea_gj_per_t": float(q[0]), "q_cesar1_gj_per_t": float(q[1]),
                           "ratio_cesar1_to_mea": float(q[1] / q[0])}
    out["measured_ratio"] = {k: round(c / m, 3) for k, (c, m) in ENERGY_BENCHMARK.items()}
    # Extra PZ heat the benchmarks can tolerate: CESAR1's ratio may rise to the highest reported.
    n_pz, n_amp = 13.0 / core["PZ"].mw, 27.0 / core["AMP"].mw
    f_pz = 2.0 * n_pz / (2.0 * n_pz + n_amp)
    top = max(out["measured_ratio"].values())
    out["pz_heat_uplift_allowed_by_benchmarks"] = float(min(
        (top * m["q_mea_gj_per_t"] - m["q_cesar1_gj_per_t"]) / (KJ_PER_MOL_TO_GJ_PER_T * f_pz)
        for m in out["model"].values()))
    out["cesar1_ratio_with_full_calorimetric_heat"] = None
    return out


def _top(res: pd.DataFrame, ok: np.ndarray, color: np.ndarray, which: str, n: int) -> set:
    g = res[ok & (color == which)]
    return set(g.nsmallest(n, "cost_both")["mixture_id"])


def pz_heat_stress(df, t, cap, q, mea_idx, ok, uplift: float, n: int = 20) -> dict:
    """What if Hilliard's calorimetry, not the VLE-based heat, is right at the stripper? The model's
    heat comes from VLE measured up to 120 C and the pilot CESAR1 : MEA ratio supports it, but
    calorimetry reads higher in proportion to PZ's share of the N. Not used in the ranking."""
    c1 = {s: v[:, :1] for s, v in cap.items()}
    q1 = {s: v[:, :1] for s, v in q.items()}
    color = df["color"].to_numpy()
    base = compute(df, t, c1, q1, mea_idx)
    res = compute(df, t, c1, q1, mea_idx, pz_heat_uplift=uplift)

    def best(which):
        g = res[ok & (color == which)].nlargest(1, "saving_vs_mea").iloc[0]
        return {"composition": df.set_index("mixture_id").loc[g["mixture_id"], "composition"],
                "saving": float(g["saving_vs_mea"])}

    pz = np.flatnonzero((df["composition"] == "PZ 30%").to_numpy())[0]
    return {"uplift_kj_per_mol_at_all_N_as_PZ": uplift,
            "pz_30_saving": float(res["saving_vs_mea"].iloc[pz]),
            "n_cheaper_than_mea": int((res["saving_vs_mea"][ok] > 0).sum()),
            "n_cheaper_base": int((base["saving_vs_mea"][ok] > 0).sum()),
            "best": {c: best(c) for c in ("yellow", "blue")},
            "kept_in_top_n": {c: len(_top(base, ok, color, c, n) & _top(res, ok, color, c, n))
                              for c in ("yellow", "blue")}}


def sensitivity(df, t, cap, q, mea_idx, ok, n: int = 20) -> dict:
    """Move one assumption at a time to the end of its range (nominal model) and count how
    many of the top-n in each colour stay. A mixture list that only holds at the median of an
    assumed number would not be worth taking to the lab."""
    c1 = {s: v[:, :1] for s, v in cap.items()}
    q1 = {s: v[:, :1] for s, v in q.items()}
    color = df["color"].to_numpy()
    base = compute(df, t, c1, q1, mea_idx)
    ref = {c: _top(base, ok, color, c, n) for c in ("yellow", "blue")}
    out = {}
    for name, (lo, _, hi) in SCALARS.items():
        for tag, v in (("low", lo), ("high", hi)):
            r = compute(df, t, c1, q1, mea_idx, {name: v})
            out[f"{name}={tag}"] = {c: len(ref[c] & _top(r, ok, color, c, n)) for c in ref}
    return {"top_n": n, "kept_in_top_n": out,
            "worst_case": {c: min(v[c] for v in out.values()) for c in ref}}


def main():
    df = pd.read_csv(SCREEN / "mixtures_ranked.csv", keep_default_na=False, na_values=["", "nan"])
    df["partners"] = df["partners"].fillna("").astype(str)
    df["partner_wt"] = df["partner_wt"].fillna("").astype(str)
    pinfo = pd.read_csv(SCREEN / "partners.csv")
    avail = load_availability()
    t = amine_table(pinfo, avail)

    mc = np.load(SCREEN / "mc_samples.npz")
    assert (mc["mixture_id"] == df["mixture_id"].to_numpy()).all(), "re-run the screen"
    cap = {s: mc[f"{s}_cyclic"].astype(float) for s in SCENARIOS}
    q = {s: mc[f"{s}_q_reb"].astype(float) for s in SCENARIOS}
    mea_idx = int(np.flatnonzero((df["composition"] == "MEA 30%").to_numpy())[0])

    res = compute(df, t, cap, q, mea_idx)
    full = df.merge(res, on="mixture_id")
    full = pd.concat([full, flags(full, t)], axis=1)
    full = rank(full)
    full.to_csv(SCREEN / "mixtures_practical.csv", index=False)
    ok_mask = full["practical_ok"].to_numpy()
    fit = json.loads((ROOT / "data" / "processed" / "thermo" / "calibrated_core_amines.json").read_text())
    uplift = -fit["fit_report"]["Hilliard2008_heats"]["bias_at_120C_vs_PZ_N_fraction"]["slope"]
    energy = energy_check()
    allowed = energy["pz_heat_uplift_allowed_by_benchmarks"]
    n_pz, n_amp = 13.0 / 86.14, 27.0 / 89.14
    m = energy["model"]["coal"]
    energy["cesar1_ratio_with_full_calorimetric_heat"] = float(
        (m["q_cesar1_gj_per_t"] + uplift * KJ_PER_MOL_TO_GJ_PER_T * 2 * n_pz / (2 * n_pz + n_amp)) / m["q_mea_gj_per_t"])
    checks = {"energy": energy,
              "sensitivity": sensitivity(df, t, cap, q, mea_idx, ok_mask),
              "pz_heat_stress": {"full_calorimetry": pz_heat_stress(df, t, cap, q, mea_idx, ok_mask, uplift),
                                 "benchmark_limit": pz_heat_stress(df, t, cap, q, mea_idx, ok_mask, allowed)}}
    (INPUTS / "checks.json").write_text(json.dumps(checks, indent=2))
    print(json.dumps(checks["energy"], indent=2))
    print("list stability:", checks["sensitivity"]["worst_case"], "of", checks["sensitivity"]["top_n"])
    print("PZ heat stress test:", json.dumps(checks["pz_heat_stress"], indent=2))
    t.drop(columns=["price_basis", "oxidation_basis", "corrosion_basis"]).to_csv(SCREEN / "amines_practical.csv")

    ok = full[full["practical_ok"]]
    print(f"{len(ok)} of {len(full)} mixtures pass the practical filter "
          f"({ok['color'].value_counts().to_dict()})")
    mea = full.iloc[mea_idx]
    print(f"30 wt% MEA: ${mea.cost_both:.1f}/t  (cement ${mea.cement_cost_total:.1f}, coal ${mea.coal_cost_total:.1f})")
    print(ok.nlargest(12, "saving_vs_mea")[["composition", "color", "cost_both", "saving_vs_mea",
                                            "p_cheaper_than_mea", "rank_both"]].to_string(index=False))


if __name__ == "__main__":
    main()
