"""
Calibrate the equilibrium model against experimental VLE (pCO2 vs loading) data.

    MEA  <- Wagner et al. (2013)             (NIST ThermoML, pCO2 <= 2000 kPa, 313-393 K)
            + Aronu et al. (2011)            (15-60 mass%, 40-80 C, measured pCO2 0.0007-19 kPa)
    MEA, PZ, MEA+PZ <- Dugas (2009)          HELD OUT: wetted-wall column, MEA and PZ in the same
                                             apparatus -> like-for-like capacity benchmark
                                             (the ranking-relevant PZ : MEA ratio)
    AMP  <- Hartono et al. (2020)            (rows with a measured CO2 partial pressure)
    PZ   <- Ermatchkov et al. (2006)
    MDEA <- JOINT fit, after PZ: Leontiadis et al. (2019) + Dey et al. (2018) single-MDEA VLE
            (298-333 K), Xu (2011) MDEA+PZ blends (100-160 C) and Arcis et al. (2008)
            calorimetry; free: logK25, dH, b_conc (concentration term). Checked by
            leave-one-blend-out and by Xu (2011) Table 2-12 capacity / heat benchmarks.
    AMP+PZ blend <- Dash et al. (2011)       HELD OUT: never used for fitting; it tests
                                             whether single-amine parameters predict blends

Fitting is MAP (prior-regularised least squares): residuals on loading scaled by an
observation sigma, plus (theta - prior) / prior_sigma terms, so data-poor parameters
stay near literature values. Posterior 1-sigma (from the Jacobian, inflated by the
reduced chi-square) becomes the species sd_logK / sd_dH used for Monte Carlo UQ.

Parameter uncertainty alone under-covers the held-out blend (the single-amine model
misses AMP/PZ synergy), so a model-discrepancy margin is learned by conformalized
quantile regression (CQR, Romano et al. 2019) on the held-out blend residuals:

    score_i = max(lo_i - y_i, y_i - hi_i)     (lo/hi = MC 5/95 % loading quantiles)
    q_hat   = conformal 90 % quantile of the scores
    final interval = [lo - q_hat, hi + q_hat]

Coverage of that recipe is checked leave-one-concentration-group-out, and the final
q_hat (all groups) is stored as `loading_discrepancy_q90` for the screening stage.

Run:  python -m src.thermo.calibrate
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from rdkit.Chem import Descriptors
from scipy.optimize import least_squares

from src.screening.partners import CURATED, Partner, analyse, build_model, protonation_order

from .chemistry import (CORE_NAMES, MW_WATER, AmineModel, Species, core_amines,
                        water_vapor_pressure_kpa)
from .equilibrium import (compile_batch, heat_of_absorption, pco2_at_loading, sample_batch,
                          solve)

ROOT = Path(__file__).resolve().parents[2]
STRUCT = ROOT / "data" / "processed" / "structured"
OUT_DIR = ROOT / "data" / "processed" / "thermo"
FIG_DIR = ROOT / "reports" / "figures" / "calibration"
PARAMS_JSON = OUT_DIR / "calibrated_core_amines.json"

SIGMA_ABS = 0.02   # loading observation noise, mol CO2 / mol amine
SIGMA_REL = 0.03
MAX_PCO2 = 2000.0  # kPa, upper limit of calibration data (ideal-solution model)


def wt_to_molality(w_pct, mw, total_wt_pct):
    return (np.asarray(w_pct, float) / mw) * 1000.0 / (100.0 - np.asarray(total_wt_pct, float))


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
def load_data() -> dict:
    m = pd.read_csv(STRUCT / "modeling_dataset_with_hartono_dash.csv")

    h = m[(m["source"] == "Hartono et al. (2020)") & m["pCO2_kPa"].notna()].copy()
    amp = pd.DataFrame({
        "T": h["T_K"].astype(float),
        "p": h["pCO2_kPa"].astype(float),
        "m_AMP": wt_to_molality(h["amp_wt_pct"], 89.14, h["amp_wt_pct"]),
        "m_PZ": 0.0,
        "loading": h["loading_molCO2_per_molamine"].astype(float),
        "label": h["amp_wt_pct"].map(lambda w: f"{w:g} wt% AMP"),
    })

    e = pd.read_csv(ROOT / "data" / "interim" / "piperazine_ermatchkov_2006.csv")
    pz = pd.DataFrame({
        "T": e["T"].astype(float),
        "p": e["P_CO2"].astype(float),
        "m_AMP": 0.0,
        "m_PZ": e["conc"].astype(float),
        "loading": e["loading_alpha"].astype(float),
        "label": e["conc"].map(lambda c: f"{c:.2f} m PZ"),
    })

    d = m[m["source"] == "Dash et al. (2011)"].copy()
    tot = d["amp_wt_pct"] + d["pz_wt_pct"]
    blend = pd.DataFrame({
        "T": d["T_K"].astype(float),
        "p": d["pCO2_kPa"].astype(float),
        "m_AMP": wt_to_molality(d["amp_wt_pct"], 89.14, tot),
        "m_PZ": wt_to_molality(d["pz_wt_pct"], 86.14, tot),
        "loading": d["loading_molCO2_per_molamine"].astype(float),
        "label": [f"{a:g}/{z:g} wt% AMP/PZ" for a, z in zip(d["amp_wt_pct"], d["pz_wt_pct"])],
    })
    # MEA (Wagner 2013) and MDEA (Leontiadis 2019, Dey 2018) from NIST ThermoML,
    # see src/data/ingest_thermoml_mea_mdea.py. Capped at MAX_PCO2 like the other sets:
    # the ideal-solution model is not meant for multi-MPa CO2.
    t = pd.read_csv(ROOT / "data" / "interim" / "mea_mdea_vle_thermoml.csv")
    t = t[t["pCO2_kPa"] <= MAX_PCO2]
    single = {}
    for amine in ("MEA", "MDEA"):
        g = t[t["amine"] == amine]
        single[amine] = pd.DataFrame({
            "T": g["T"].astype(float),
            "p": g["pCO2_kPa"].astype(float),
            f"m_{amine}": g["m_amine"].astype(float),
            "loading": g["loading"].astype(float),
            "label": [f"{s.split(' et')[0]} {m:.1f} m" for s, m in zip(g["source"], g["m_amine"])],
        })

    # Aronu (2011): measured pCO2 at 40-80 C, 15-60 mass% MEA (src/data/ingest_aronu2011_mea.py).
    # Fills the lean/absorber region Wagner barely covers (Wagner starts at 1.4 kPa at 40 C).
    # Adding it with the same 4 free constants was chosen over adding a concentration term
    # (b_conc): the term fit Aronu better in-sample but failed leave-one-concentration-out at
    # 60 mass% (MAE 0.025 vs 0.017) and did not improve the held-out Dugas checks. docs/LOG.md.
    a = pd.read_csv(ROOT / "data" / "interim" / "mea_aronu2011.csv")
    aronu = pd.DataFrame({"T": a["T"].astype(float), "p": a["pCO2_kPa"].astype(float),
                          "m_MEA": a["m_amine"].astype(float), "loading": a["loading"].astype(float),
                          "label": [f"Aronu {w} wt%" for w in a["w_amine_pct"]]})
    mea = pd.concat([single["MEA"], aronu], ignore_index=True)

    out = {"MEA": mea, "MDEA": single["MDEA"], "AMP": amp, "PZ": pz, "AMP+PZ": blend}
    for df in out.values():
        for n in CORE_NAMES:
            if f"m_{n}" not in df:
                df[f"m_{n}"] = 0.0
        df.reset_index(drop=True, inplace=True)
    return out


def _mixtures(df: pd.DataFrame, models: dict):
    cols = [(n, df[f"m_{n}"].to_numpy()) for n in CORE_NAMES]
    return [[(models[n], m[i]) for n, m in cols if m[i] > 0] for i in range(len(df))]


def predict_loading(df: pd.DataFrame, models: dict) -> np.ndarray:
    b = compile_batch(_mixtures(df, models))
    return solve(b, df["T"].to_numpy(), df["p"].to_numpy())["loading"]


# ---------------------------------------------------------------------------
# Parameterisation: which species constants are free for each amine
# ---------------------------------------------------------------------------
FREE = {
    "MEA": [("MEAH+", "logK25"), ("MEAH+", "dH"), ("MEACOO-", "logK25"), ("MEACOO-", "dH")],
    # MDEA: fitted JOINTLY on single-MDEA VLE (298-333 K), Xu (2011) MDEA+PZ blends
    # (100-160 C, ~50 wt% amine) and Arcis (2008) calorimetry. A concentration term on the
    # apparent protonation constant (Kent-Eisenberg extension) reconciles all three; a
    # heat-capacity term also fits but needs an unphysical dCp (~ -0.6 kJ/mol/K, protonation
    # heat -25 -> -90 kJ/mol over 25-130 C), so it was rejected. See docs/LOG.md 2026-10-15.
    "MDEA": [("MDEAH+", "logK25"), ("MDEAH+", "dH"), ("MDEAH+", "b_conc")],
    "AMP": [("AMPH+", "logK25"), ("AMPH+", "dH"), ("AMPCOO-", "logK25"), ("AMPCOO-", "dH")],
    "PZ": [("PZH+", "logK25"), ("PZH+", "dH"), ("PZCOO-", "logK25"), ("PZCOO-", "dH"),
           ("H+PZCOO-", "logK25"), ("H+PZCOO-", "dH"), ("PZ(COO-)2", "logK25"),
           ("PZ(COO-)2", "dH")],
}
# Prior sigma used for regularisation (looser than the MC sd of the literature prior;
# apparent KE constants legitimately drift from thermodynamic values).
PRIOR_SIGMA = {"logK25": 0.6, "dH": 12.0, "dCp": 0.3, "b_conc": 0.1}
SD_FIELD = {"logK25": "sd_logK", "dH": "sd_dH", "dCp": "sd_dCp", "b_conc": "sd_b_conc"}
# Per-parameter overrides. MDEA protonation enthalpy: the MDEA VLE data only span
# 298-333 K, and with the loose 12 kJ/mol prior the fit drifted to -48.5 kJ/mol, which made
# the held-out calorimetry (Arcis 2008) WORSE (MAE 6.2 kJ/mol). A literature-grade prior
# (-34.9 +/- 3, calorimetric value) leaves the loading fit unchanged (MAE 0.029 vs 0.030)
# and brings the heat of absorption to MAE 1.4 kJ/mol -- consistent with both datasets.
PRIOR_SIGMA_OVERRIDE = {("MDEA", "MDEAH+", "dH"): 3.0}


def _get(model: AmineModel, sp_name: str, field: str) -> float:
    return getattr(next(s for s in model.species if s.name == sp_name), field)


def _set(model: AmineModel, values: dict) -> AmineModel:
    species = []
    for s in model.species:
        upd = {f: v for (n, f), v in values.items() if n == s.name}
        species.append(replace(s, **upd) if upd else s)
    return model.with_species(species)


def fit_amine(name: str, df: pd.DataFrame, models: dict, extra_resid=None) -> tuple:
    """MAP fit of FREE[name]. `extra_resid(models) -> scaled residual array` adds other
    observations (e.g. calorimetric heats) to the same objective."""
    base = models[name]
    keys = FREE[name]
    theta0 = np.array([_get(base, n, f) for n, f in keys])
    psig = np.array([PRIOR_SIGMA_OVERRIDE.get((name, n, f), PRIOR_SIGMA[f]) for n, f in keys])
    obs = df["loading"].to_numpy()
    sig = SIGMA_ABS + SIGMA_REL * obs

    def model_for(theta):
        return {**models, name: _set(base, dict(zip(keys, theta)))}

    def resid(theta):
        m = model_for(theta)
        parts = [(predict_loading(df, m) - obs) / sig]
        if extra_resid is not None:
            parts.append(extra_resid(m))
        return np.concatenate(parts + [(theta - theta0) / psig])

    res = least_squares(resid, theta0, method="trf", x_scale=psig, diff_step=1e-4)
    n_data = len(res.fun) - len(theta0)
    r_data = res.fun[:n_data]
    chi2_red = float(np.sum(r_data ** 2) / max(n_data - len(theta0), 1))
    J = res.jac
    cov = np.linalg.pinv(J.T @ J) * max(chi2_red, 1.0)
    sd = np.sqrt(np.clip(np.diag(cov), 0, None))

    fitted = _set(base, dict(zip(keys, res.x)))
    # posterior sd into the species uncertainty fields
    sd_vals = {}
    for (n, f), s in zip(keys, sd):
        sd_vals[(n, SD_FIELD[f])] = float(s)
    fitted = _set(fitted, sd_vals)
    fitted.source = "calibrated"
    fitted.note = f"MAP fit to {len(obs)} pCO2-loading points" + (
        f" + {n_data - len(obs)} other observations" if n_data > len(obs) else "")

    pred = predict_loading(df, {**models, name: fitted})
    stats = {
        "n_points": len(obs),
        "n_other_observations": n_data - len(obs),
        "chi2_reduced": chi2_red,
        "mae_loading": float(np.mean(np.abs(pred - obs))),
        "aard_pct": float(100 * np.mean(np.abs(pred - obs) / obs)),
        "params": {f"{n}.{f}": {"prior": float(t0), "fit": float(t), "sd": float(s)}
                   for (n, f), t0, t, s in zip(keys, theta0, res.x, sd)},
    }
    return fitted, stats, pred


# ---------------------------------------------------------------------------
# Held-out blend validation + coverage
# ---------------------------------------------------------------------------
def mc_interval(df: pd.DataFrame, models: dict, k: int = 200, seed: int = 0,
                inflate: float = 1.0):
    b = compile_batch(_mixtures(df, models))
    b.sd_logK = b.sd_logK * inflate
    b.sd_dH = b.sd_dH * inflate
    tb, _ = sample_batch(b, k, seed)
    T = np.repeat(df["T"].to_numpy(), k)
    p = np.repeat(df["p"].to_numpy(), k)
    L = solve(tb, T, p)["loading"].reshape(len(df), k)
    return L[:, 0], np.quantile(L, 0.05, axis=1), np.quantile(L, 0.95, axis=1)


def coverage(obs, lo, hi):
    return float(np.mean((obs >= lo) & (obs <= hi)))


def conformal_q(scores, alpha=0.10):
    n = len(scores)
    level = min(1.0, np.ceil((n + 1) * (1 - alpha)) / n)
    return float(np.quantile(scores, level, method="higher"))


def cqr(df, lo, hi, alpha=0.10):
    """Conformal margin from all points + leave-one-group-out coverage estimate."""
    obs = df["loading"].to_numpy()
    scores = np.maximum(lo - obs, obs - hi)
    groups = df["label"].to_numpy()
    per_group = {}
    for g in pd.unique(groups):
        test = groups == g
        q = conformal_q(scores[~test], alpha)
        per_group[g] = coverage(obs[test], lo[test] - q, hi[test] + q)
    return conformal_q(scores, alpha), per_group


# ---------------------------------------------------------------------------
# Second held-out blend: MDEA + PZ at stripper temperatures (Xu 2011 thesis)
# ---------------------------------------------------------------------------
def load_mdea_pz_xu() -> pd.DataFrame:
    x = pd.read_csv(ROOT / "data" / "interim" / "mdea_pz_xu2011.csv")
    x = x[x["pCO2_kPa"] <= MAX_PCO2].reset_index(drop=True)
    df = pd.DataFrame({
        "T": x["T"], "p": x["pCO2_kPa"], "m_MDEA": x["m_MDEA"], "m_PZ": x["m_PZ"],
        # model loading is per mol of amine MOLECULES; convert the thesis' per-alkalinity value
        "loading": x["n_co2"] / (x["m_MDEA"] + x["m_PZ"]),
        "label": [f"{b}, {t - 273.15:.0f} C" for b, t in zip(x["blend"], x["T"])],
        "blend": x["blend"], "alkalinity_m": x["alkalinity_m"],
        "loading_per_alkalinity": x["loading_per_alkalinity"],
    })
    for n in CORE_NAMES:
        if f"m_{n}" not in df:
            df[f"m_{n}"] = 0.0
    return df


def mdea_pz_validation(models: dict, q_hat: float) -> tuple:
    """Prediction + coverage of the AMP+PZ-derived conformal margin on a blend it never saw."""
    df = load_mdea_pz_xu()
    nominal, lo, hi = mc_interval(df, models)
    obs = df["loading"].to_numpy()
    scale = (df["m_MDEA"] + df["m_PZ"]) / df["alkalinity_m"]       # per-molecule -> per-alkalinity
    report = {
        "n_points": len(df),
        "mae_loading_per_alkalinity": float(np.mean(np.abs((nominal - obs) * scale))),
        "bias_loading_per_alkalinity": float(np.mean((nominal - obs) * scale)),
        "coverage90_param_only": coverage(obs, lo, hi),
        "coverage90_with_AMP_PZ_margin": coverage(obs, lo - q_hat, hi + q_hat),
        "by_blend": {},
    }
    for b in pd.unique(df["blend"]):
        mk = (df["blend"] == b).to_numpy()
        report["by_blend"][b] = {
            "n": int(mk.sum()),
            "mae_loading_per_alkalinity": float(np.mean(np.abs((nominal - obs)[mk] * scale[mk]))),
            "coverage90_with_margin": coverage(obs[mk], lo[mk] - q_hat, hi[mk] + q_hat),
        }
    return df, nominal, lo - q_hat, hi + q_hat, report


# ---------------------------------------------------------------------------
# Heat-of-absorption validation (MDEA, Arcis et al. 2008 flow calorimetry)
# ---------------------------------------------------------------------------
def enthalpy_validation(models: dict, n_grid: int = 12) -> pd.DataFrame:
    """
    Arcis et al. report the INTEGRAL enthalpy of solution per mol of CO2 fed at 322.5 K.
    All ThermoML points lie at or beyond saturation, where extra CO2 stays in the gas and
    adds ~no heat, so the measured value is  dh_int(a_sat) * a_sat / a_fed.  The model
    gives a_sat at pCO2 = P - x_w p_sat,H2O and dh_int by integrating its differential
    heat (Gibbs-Helmholtz) over loading 0 -> a_sat. Never used for fitting.
    """
    h = pd.read_csv(ROOT / "data" / "interim" / "mdea_enthalpy_arcis2008.csv")
    T = h["T"].to_numpy()
    m = h["m_amine"].to_numpy()
    x_w = (1000 / MW_WATER) / (1000 / MW_WATER + m)
    p_sat = h["P_kPa"].to_numpy() - x_w * water_vapor_pressure_kpa(T)
    b = compile_batch([[(models["MDEA"], mi)] for mi in m])
    n_sat = solve(b, T, p_sat)["n_co2"]
    frac = (np.arange(n_grid) + 0.5) / n_grid
    bb = b.repeat(n_grid)
    Tg = np.repeat(T, n_grid)
    n_target = (n_sat[:, None] * frac[None, :]).ravel()
    p_grid = pco2_at_loading(bb, Tg, n_target)
    dh = heat_of_absorption(bb, Tg, p_grid).reshape(len(h), n_grid)
    dh_int = dh.mean(axis=1)
    a_sat = n_sat / m
    pred = -dh_int * np.minimum(1.0, a_sat / h["loading"].to_numpy())
    return h.assign(model_dH=pred, model_loading_sat=a_sat)


HEAT_SIGMA = 2.0   # kJ/mol, calorimetric observation noise used in the joint MDEA fit
MDEA_FIT_ORDER = ("MEA", "AMP", "PZ", "MDEA")   # PZ before MDEA: the blend data need it


def heat_resid(models: dict) -> np.ndarray:
    h = enthalpy_validation(models, n_grid=8)
    return (h["model_dH"] - h["dH_solution_kj_per_mol"]).to_numpy() / HEAT_SIGMA


def mdea_fit_frame(single: pd.DataFrame, xu: pd.DataFrame) -> pd.DataFrame:
    return pd.concat([single, xu[list(single.columns)]], ignore_index=True)


def lobo_mdea(single: pd.DataFrame, xu: pd.DataFrame, models: dict) -> dict:
    """Leave-one-blend-out: refit MDEA without one Xu blend, predict that blend."""
    out = {}
    scale = ((xu["m_MDEA"] + xu["m_PZ"]) / xu["alkalinity_m"]).to_numpy()
    for hold in pd.unique(xu["blend"]):
        keep = (xu["blend"] != hold).to_numpy()
        fitted, _, _ = fit_amine("MDEA", mdea_fit_frame(single, xu[keep]), models,
                                 extra_resid=heat_resid)
        err = (predict_loading(xu, {**models, "MDEA": fitted}) - xu["loading"].to_numpy()) * scale
        out[hold] = {"n": int((~keep).sum()),
                     "mae_loading_per_alkalinity": float(np.mean(np.abs(err[~keep]))),
                     "bias_loading_per_alkalinity": float(np.mean(err[~keep]))}
    return out


# Xu (2011) Table 2-12: cyclic capacity between PCO2* = 0.5 and 5 kPa at 40 C,
# mol CO2 / kg (amine + water), from his empirical fits to measured VLE.
XU_CAPACITY = {"7 m MEA": ({"MEA": 7.0}, 0.50), "8 m PZ": ({"PZ": 8.0}, 0.85),
               "7 m MDEA / 2 m PZ": ({"MDEA": 7.0, "PZ": 2.0}, 0.84),
               "5 m MDEA / 5 m PZ": ({"MDEA": 5.0, "PZ": 5.0}, 0.98)}


XU_HEAT = {"7 m MEA": 72.0, "8 m PZ": 67.0, "7 m MDEA / 2 m PZ": 72.3, "5 m MDEA / 5 m PZ": 69.0}


def heat_benchmark(models: dict, temps_c=(40.0, 80.0, 120.0)) -> pd.DataFrame:
    """Xu (2011) Table 2-12 heat of absorption at mid loading (PCO2* = 1.5 kPa at 40 C),
    from his Gibbs-Helmholtz fit over 40-160 C, vs the model at 40 / 80 / 120 C. This is the
    check that rejected the heat-capacity variant (it over-states the stripper heat of
    MDEA blends by 15-25 kJ/mol)."""
    mixes = [[(models[n], m) for n, m in comp.items()] for comp, _ in XU_CAPACITY.values()]
    b = compile_batch(mixes)
    n_mid = solve(b, 313.15, 1.5)["n_co2"]
    df = pd.DataFrame({"solvent": list(XU_CAPACITY), "xu_2011": [XU_HEAT[k] for k in XU_CAPACITY]})
    for t in temps_c:
        p = pco2_at_loading(b, t + 273.15, n_mid)
        df[f"model_{t:.0f}C"] = heat_of_absorption(b, t + 273.15, p)
    return df


def capacity_benchmark(models: dict) -> pd.DataFrame:
    """Does the model value each solvent correctly RELATIVE TO MEA? (ranking-relevant)"""
    mixes = [[(models[n], m) for n, m in comp.items()] for comp, _ in XU_CAPACITY.values()]
    b = compile_batch(mixes)
    lean = solve(b, 313.15, 0.5)["n_co2"]
    rich = solve(b, 313.15, 5.0)["n_co2"]
    cap = (rich - lean) / b.solvent_kg_per_kg_water
    df = pd.DataFrame({"solvent": list(XU_CAPACITY), "model": cap,
                       "xu_2011": [v for _, v in XU_CAPACITY.values()]})
    df["model_vs_MEA"] = df["model"] / df["model"].iloc[0]
    df["xu_vs_MEA"] = df["xu_2011"] / df["xu_2011"].iloc[0]
    return df


# ---------------------------------------------------------------------------
# Held-out MEA / PZ / MEA+PZ (Dugas 2009 thesis, wetted-wall column)
# ---------------------------------------------------------------------------
# Xu's Table 2-12 MEA capacity (0.50) comes from his concentration-independent empirical
# fit over 2.9-24.6 m MEA and 40-150 C; at 40 C it reads 7 m MEA 0.01-0.03 mol/mol too high
# at 5 kPa. Measured 7 m MEA data give 0.30-0.33 mol/kg (Aronu 2011, Wagner 2013, Dugas 2009),
# so the like-for-like benchmark below uses Dugas' measured points, where MEA and PZ come
# from the same apparatus.
DUGAS_CAPACITY = {"7 m MEA": (7.0, 0.0), "8 m PZ": (0.0, 8.0), "7 m MEA / 2 m PZ": (7.0, 2.0),
                  "5 m PZ": (0.0, 5.0), "13 m MEA": (13.0, 0.0)}


def mea_interlab_inflation(models: dict, target: float = 0.90) -> tuple:
    """Smallest factor k on MEA's parameter sd so the parameter-only 90 % interval covers
    `target` of the independent Dugas (2009) MEA points. The pooled Wagner + Aronu fit
    (chi2_red < 1) halves the posterior sd, but that only reflects within-lab scatter: on
    another lab's data the raw intervals cover ~62 %. An under-stated MEA spread would make
    candidates look robustly better than the MEA reference (score_lo90 > 0) for the wrong
    reason. Dugas sets this width only; it never enters the point fit."""
    df = load_dugas()
    df = df[df["system"] == "MEA"].reset_index(drop=True)
    obs = df["loading"].to_numpy()
    raw = None
    for k in np.arange(1.0, 8.01, 0.25):
        _, lo, hi = mc_interval(df, models, inflate=k)
        cov = coverage(obs, lo, hi)
        raw = cov if raw is None else raw
        if cov >= target:
            return float(k), raw, cov
    return float(k), raw, cov


def load_dugas() -> pd.DataFrame:
    d = pd.read_csv(ROOT / "data" / "interim" / "dugas2009_wwc.csv")
    df = pd.DataFrame({"T": d["T"], "p": d["pCO2_kPa"], "m_MEA": d["m_MEA"], "m_PZ": d["m_PZ"],
                       "loading": d["loading"], "system": d["system"],
                       "alkalinity_m": d["alkalinity_m"],
                       "loading_per_alkalinity": d["loading_per_alkalinity"],
                       "label": [f"Dugas {s} {a:g}/{z:g} m" for s, a, z in
                                 zip(d["system"], d["m_MEA"], d["m_PZ"])]})
    for n in CORE_NAMES:
        if f"m_{n}" not in df:
            df[f"m_{n}"] = 0.0
    return df


def _data_loading_at(g: pd.DataFrame, p_kpa: float) -> float:
    """Log-linear interpolation of measured loading (per alkalinity) at pCO2 = p (linear
    extrapolation from the last two points if p is just beyond the data, e.g. 7 m MEA)."""
    g = g.sort_values("p")
    lp, a = np.log(g["p"].to_numpy()), g["loading_per_alkalinity"].to_numpy()
    x = np.log(p_kpa)
    if x <= lp[-1]:
        return float(np.interp(x, lp, a))
    return float(a[-1] + (a[-1] - a[-2]) / (lp[-1] - lp[-2]) * (x - lp[-1]))


def dugas_validation(models: dict, q_hat: float) -> tuple:
    df = load_dugas()
    nominal, lo, hi = mc_interval(df, models)
    obs = df["loading"].to_numpy()
    scale = ((df["m_MEA"] + df["m_PZ"]) / df["alkalinity_m"]).to_numpy()
    err = (nominal - obs) * scale
    report = {"n_points": len(df), "by_system": {}}
    for s in pd.unique(df["system"]):
        mk = (df["system"] == s).to_numpy()
        report["by_system"][s] = {
            "n": int(mk.sum()),
            "mae_loading_per_alkalinity": float(np.mean(np.abs(err[mk]))),
            "bias_loading_per_alkalinity": float(np.mean(err[mk])),
            "coverage90_with_AMP_PZ_margin": coverage(obs[mk], lo[mk] - q_hat, hi[mk] + q_hat),
        }
    # like-for-like capacity at 40 C, PCO2* 0.5 -> 5 kPa
    rows = []
    mixes = [[(models[n], m) for n, m in (("MEA", a), ("PZ", z)) if m > 0]
             for a, z in DUGAS_CAPACITY.values()]
    b = compile_batch(mixes)
    lean = solve(b, 313.15, 0.5)["n_co2"]
    rich = solve(b, 313.15, 5.0)["n_co2"]
    cap_model = (rich - lean) / b.solvent_kg_per_kg_water
    d40 = df[np.isclose(df["T"], 313.15)]
    for (name, (a, z)), cm in zip(DUGAS_CAPACITY.items(), cap_model):
        g = d40[np.isclose(d40["m_MEA"], a) & np.isclose(d40["m_PZ"], z)]
        alk = a + 2 * z
        cap_data = (_data_loading_at(g, 5.0) - _data_loading_at(g, 0.5)) * alk / (
            1.0 + (a * 61.08 + z * 86.14) / 1000.0)
        rows.append({"solvent": name, "model": float(cm), "dugas_2009": cap_data})
    cap = pd.DataFrame(rows)
    cap["model_vs_MEA"] = cap["model"] / cap["model"].iloc[0]
    cap["dugas_vs_MEA"] = cap["dugas_2009"] / cap["dugas_2009"].iloc[0]
    report["capacity_benchmark"] = cap.to_dict(orient="records")
    return df, nominal, lo - q_hat, hi + q_hat, report, cap


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# DETA (Chang et al. 2013): the one partner amine with direct pCO2-loading data
# ---------------------------------------------------------------------------
DETA_SMILES, DETA_MW = "NCCNCCN", 103.17
# Sites: two terminal primary N (pKa 9.84 / 9.02) and the central secondary N (pKa 4.23).
# The two primaries share their enthalpies and carbamate constants. pKa1 stays fixed.
DETA_PARAMS = ("prot_dH_primary", "prot_dH_secondary", "pKa3", "carb_logK_primary",
               "carb_dH_primary", "carb_logK_secondary", "carb_dH_secondary", "pKa2")
DETA_PRIOR = np.array([-51.0, -45.0, 4.23, 1.4, -22.0, 0.6, -18.0, 9.02])
DETA_PRIOR_SD = np.array([8.0, 8.0, 0.6, 1.0, 12.0, 1.0, 12.0, 0.3])
DETA_PKA1 = 9.84
# Wang et al. (2026): measured absorption capacity at 323 K, 13 vol% CO2, mol CO2/kg absorbent.
# TMPDA and HEPZ are uncalibrated, so this is a coarse check, never a fit.
WANG_2026 = {"3-5": ({"DETA": 20, "HEPZ": 5, "AMP": 5}, 3.358),
             "4-5": ({"DETA": 20, "TMPDA": 5, "AMP": 5}, 3.358),
             "1-1": ({"TMPDA": 10, "PZ": 10, "DETA": 10}, 2.964),
             "2-2": ({"TMPDA": 15, "AMP": 5, "DETA": 10}, 2.667)}


def deta_model(theta, sd=None) -> AmineModel:
    t = dict(zip(DETA_PARAMS, theta))
    u = dict(zip(DETA_PARAMS, sd if sd is not None else np.zeros(len(theta))))
    sites = []
    for k, (cls, pka, sd_pka) in enumerate((("primary", DETA_PKA1, 0.15),
                                            ("primary", t["pKa2"], u["pKa2"]),
                                            ("secondary", t["pKa3"], u["pKa3"]))):
        sites.append(AmineModel(f"DETA#{k}", DETA_SMILES, DETA_MW, [
            Species(f"DETA#{k}", 0, 0, 0.0, 0.0),
            Species(f"DETA#{k}H+", 1, 0, pka, t[f"prot_dH_{cls}"], sd_pka, u[f"prot_dH_{cls}"]),
            Species(f"DETA#{k}COO-", 0, 1, t[f"carb_logK_{cls}"], t[f"carb_dH_{cls}"],
                    u[f"carb_logK_{cls}"], u[f"carb_dH_{cls}"])]))
    return AmineModel("DETA", DETA_SMILES, DETA_MW, sites[0].species, sites=3, source="calibrated",
                      note="MAP fit to Chang et al. (2013), 84 pCO2-loading points", site_models=sites)


def predict_deta(df: pd.DataFrame, model: AmineModel) -> np.ndarray:
    b = compile_batch([[(model, m)] for m in df["m_amine"]])
    return solve(b, df["T"].to_numpy(), df["pCO2_kPa"].to_numpy())["loading"]


def fit_deta(df: pd.DataFrame) -> tuple:
    obs = df["loading"].to_numpy()
    sig = SIGMA_ABS + SIGMA_REL * obs

    def resid(theta):
        return np.r_[(predict_deta(df, deta_model(theta)) - obs) / sig,
                     (theta - DETA_PRIOR) / DETA_PRIOR_SD]

    res = least_squares(resid, DETA_PRIOR, method="trf", x_scale=DETA_PRIOR_SD, diff_step=1e-4)
    n = len(obs)
    chi2_red = float(np.sum(res.fun[:n] ** 2) / max(n - len(res.x), 1))
    cov = np.linalg.pinv(res.jac.T @ res.jac) * max(chi2_red, 1.0)
    sd = np.sqrt(np.clip(np.diag(cov), 0, None))
    return res.x, sd, chi2_red


def deta_report(df: pd.DataFrame, theta, sd, chi2_red, models: dict) -> dict:
    fitted = deta_model(theta, sd)
    pred = predict_deta(df, fitted)
    obs = df["loading"].to_numpy()
    logo = {}
    for w, g in df.groupby(df["w_amine"].round(2)):
        th, _, _ = fit_deta(df[df["w_amine"].round(2) != w])
        p = predict_deta(g, deta_model(th))
        logo[f"{w:.0%}"] = {"mae": float(np.mean(np.abs(p - g["loading"]))),
                            "bias": float(np.mean(p - g["loading"]))}
    # the same laboratory's MEA points against the MEA model fitted on other laboratories
    m = pd.read_csv(ROOT / "data" / "interim" / "deta_chang2013.csv").query("amine == 'MEA'")
    m = m[m["pCO2_kPa"] <= MAX_PCO2]
    b = compile_batch([[(models["MEA"], x)] for x in m["m_amine"]])
    mea = solve(b, m["T"].to_numpy(), m["pCO2_kPa"].to_numpy())["loading"]
    return {"n_points": len(df), "chi2_reduced": chi2_red,
            "mae_loading": float(np.mean(np.abs(pred - obs))),
            "bias_loading": float(np.mean(pred - obs)),
            "params": {k: {"prior": float(p), "fit": float(t), "sd": float(s)}
                       for k, p, t, s in zip(DETA_PARAMS, DETA_PRIOR, theta, sd)},
            "leave_one_concentration_out": logo,
            "same_lab_mea_check": {"n": len(m), "mae": float(np.mean(np.abs(mea - m["loading"]))),
                                   "bias": float(np.mean(mea - m["loading"]))}}


def wang_check(models: dict) -> list:
    """Absorption capacity of DETA ternary blends (Wang 2026) vs the model at 323 K, 13 kPa."""
    pool = {n: (s, p) for n, s, p, _ in CURATED}
    extra = {}
    for n in ("TMPDA", "HEPZ"):
        smi, pka = pool[n]
        mol, idx, classes, dm = analyse(smi)
        idx, classes, pkas = protonation_order(idx, classes, pka, dm)
        extra[n] = build_model(Partner(n, smi, Descriptors.MolWt(mol), pka, 0.3, "curated",
                                       classes, pkas, {}))
    allm = {**models, **extra}
    out = []
    for name, (comp, measured) in WANG_2026.items():
        water = 100.0 - sum(comp.values())
        mix = [(allm[a], w / allm[a].mw * 1000.0 / water) for a, w in comp.items()]
        b = compile_batch([mix])
        n_co2 = solve(b, np.array([323.15]), np.array([13.0]))["n_co2"][0]
        out.append({"blend": name, "composition": comp, "measured_mol_per_kg": measured,
                    "model_mol_per_kg": float(n_co2 / b.solvent_kg_per_kg_water[0])})
    return out


# ---------------------------------------------------------------------------
# DEA and MPA: single-site partners with direct data. Apparent pKa, protonation heat and
# carbamate constants are all free, as for the core amines, starting from the class priors.
# ---------------------------------------------------------------------------
SINGLE_SITE = {"DEA": ("OCCNCCO", 105.14, 8.88, -45.0, 0.6, -18.0),
               "MPA": ("NCCCO", 75.11, 9.96, -51.0, 1.4, -22.0)}
SINGLE_PRIOR_SD = np.array([0.5, 8.0, 1.0, 12.0])
DEA_HEAT_POINTS = ((322.5, 5.0), (372.9, 20.0))   # low-loading plateau of Arcis (2012)
HEAT_SIGMA = 3.0                                  # kJ/mol


def single_site_model(name, theta, sd=None) -> AmineModel:
    smiles, mw = SINGLE_SITE[name][:2]
    pka, dh, lk, cdh = theta
    u = sd if sd is not None else np.zeros(4)
    site = AmineModel(f"{name}#0", smiles, mw, [
        Species(f"{name}#0", 0, 0, 0.0, 0.0),
        Species(f"{name}#0H+", 1, 0, pka, dh, u[0], u[1]),
        Species(f"{name}#0COO-", 0, 1, lk, cdh, u[2], u[3])])
    return AmineModel(name, smiles, mw, site.species, sites=1, source="calibrated", site_models=[site])


def fit_single_site(name: str, df: pd.DataFrame, heat: float | None = None) -> tuple:
    obs = df["loading"].to_numpy()
    sig = SIGMA_ABS + SIGMA_REL * obs
    prior = np.array(SINGLE_SITE[name][2:])
    m30 = 0.30 / SINGLE_SITE[name][1] * 1000.0 / 0.70

    def resid(theta):
        model = single_site_model(name, theta)
        parts = [(predict_deta(df, model) - obs) / sig]
        if heat is not None:
            b = compile_batch([[(model, m30)]])
            parts.append(np.array([(float(heat_of_absorption(b, np.array([T]), np.array([p]))[0]) - heat)
                                   / HEAT_SIGMA for T, p in DEA_HEAT_POINTS]))
        return np.concatenate(parts + [(theta - prior) / SINGLE_PRIOR_SD])

    res = least_squares(resid, prior, method="trf", x_scale=SINGLE_PRIOR_SD, diff_step=1e-4)
    n = len(obs)
    chi2_red = float(np.sum(res.fun[:n] ** 2) / max(n - len(prior), 1))
    cov = np.linalg.pinv(res.jac.T @ res.jac) * max(chi2_red, 1.0)
    sd = np.sqrt(np.clip(np.diag(cov), 0, None))
    model = single_site_model(name, res.x, sd)
    pred = predict_deta(df, model)
    prior_pred = predict_deta(df, single_site_model(name, prior))
    model.note = f"MAP fit to {n} pCO2-loading points"
    return model, {"n_points": n, "chi2_reduced": chi2_red,
                   "mae_prior": float(np.mean(np.abs(prior_pred - obs))),
                   "mae_loading": float(np.mean(np.abs(pred - obs))),
                   "bias_loading": float(np.mean(pred - obs)),
                   "params": dict(zip(("pKa", "prot_dH", "carb_logK", "carb_dH"), res.x.tolist())),
                   "sd": sd.tolist()}


# ---------------------------------------------------------------------------
# Hilliard (2008): held-out loading check, and calorimetry against the model's VLE-based heats
# ---------------------------------------------------------------------------
def _mea_pz_mix(models, m_mea, m_pz):
    return [(models[n], m) for n, m in (("MEA", m_mea), ("PZ", m_pz)) if m > 0]


def hilliard_validation(models: dict) -> dict:
    h = pd.read_csv(ROOT / "data" / "interim" / "hilliard2008_vle.csv")
    b = compile_batch([_mea_pz_mix(models, r.m_MEA, r.m_PZ) for r in h.itertuples()])
    n_co2 = solve(b, h["T"].to_numpy(), h["pCO2_kPa"].to_numpy())["n_co2"]
    h["err"] = n_co2 / (h["m_MEA"] + 2.0 * h["m_PZ"]) - h["loading_per_N"]
    return {s: {"n": len(g), "mae_per_N": float(g["err"].abs().mean()), "bias_per_N": float(g["err"].mean())}
            for s, g in h.groupby("system")}


def hilliard_heat_check(models: dict) -> dict:
    """Calorimetric differential heats against the Gibbs-Helmholtz heats of the VLE-fitted model.
    The two can disagree: the model's heat comes from measured VLE, not from calorimetry."""
    d = pd.read_csv(ROOT / "data" / "interim" / "hilliard2008_heats.csv")
    d = d[d["loading_per_N"].between(0.05, 0.45)].copy()
    model = []
    for r in d.itertuples():
        b = compile_batch([_mea_pz_mix(models, r.m_MEA, r.m_PZ)])
        T = np.array([r.T])
        p = pco2_at_loading(b, T, np.array([r.loading_per_N * (r.m_MEA + 2.0 * r.m_PZ)]))
        model.append(float(heat_of_absorption(b, T, np.asarray(p).ravel()[:1])[0]))
    d["bias"] = np.array(model) - d["dH_kj_per_mol"]
    d["f_pz"] = 2.0 * d["m_PZ"] / (d["m_MEA"] + 2.0 * d["m_PZ"])
    table = [{"T_C": round(T - 273.15), "f_pz_N": round(f, 2), "n": len(g),
              "measured": float(g["dH_kj_per_mol"].mean()), "bias": float(g["bias"].mean())}
             for (T, f), g in d.groupby(["T", "f_pz"])]
    hot = pd.DataFrame([r for r in table if r["T_C"] == 120])
    slope, intercept = np.polyfit(hot["f_pz_N"], hot["bias"], 1)
    return {"by_group": table, "bias_at_120C_vs_PZ_N_fraction": {"slope": float(slope), "intercept": float(intercept)}}


def parity_plot(ax, df, pred, title, lo=None, hi=None):
    obs = df["loading"].to_numpy()
    labels = df["label"].to_numpy()
    for lab in pd.unique(labels):
        mk = labels == lab
        if lo is not None:
            ax.errorbar(obs[mk], pred[mk], yerr=[pred[mk] - lo[mk], hi[mk] - pred[mk]],
                        fmt="o", ms=4, alpha=0.75, elinewidth=0.6, capsize=0, label=lab)
        else:
            ax.plot(obs[mk], pred[mk], "o", ms=4, alpha=0.75, label=lab)
    lim = [0, max(obs.max(), np.nanmax(pred)) * 1.05]
    ax.plot(lim, lim, "k-", lw=0.8)
    ax.fill_between(lim, [l - 0.05 for l in lim], [l + 0.05 for l in lim], color="0.85", zorder=0)
    ax.set_xlim(lim); ax.set_ylim(lim)
    ax.set_xlabel("measured loading (mol CO$_2$/mol amine)")
    ax.set_ylabel("model loading")
    ax.set_title(title, fontsize=10)
    ax.legend(fontsize=6, frameon=False, ncol=2)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    data = load_data()
    prior = core_amines()

    prior_pred = {k: predict_loading(df, prior) for k, df in data.items()}
    prior_data = dict(data)   # data["MDEA"] is extended with the Xu blends during fitting

    models = dict(prior)
    report = {}
    fitted_pred = {}
    xu = load_mdea_pz_xu()
    n_single_mdea = len(data["MDEA"])
    cap_prior = capacity_benchmark(prior)
    for name in MDEA_FIT_ORDER:
        if name == "MDEA":
            cap_before = capacity_benchmark({**models, "MDEA": prior["MDEA"]})
            df_fit = mdea_fit_frame(data["MDEA"], xu)
            fitted, stats, pred = fit_amine(name, df_fit, models, extra_resid=heat_resid)
            data["MDEA"] = df_fit
            # Model-form uncertainty. b_conc is pinned only by ~50 wt% blends at 100-160 C,
            # and the two defensible models bracket MDEA's value vs MEA (Xu Table 2-12:
            # without the term MDEA-rich blends are +12 % too high at the absorber, with it
            # -16 % too low). Widen sd so the no-correction model (b = 0) sits at 2 sigma
            # and the Monte Carlo spans both.
            b_fit = _get(fitted, "MDEAH+", "b_conc")
            sd_fit = _get(fitted, "MDEAH+", "sd_b_conc")
            fitted = _set(fitted, {("MDEAH+", "sd_b_conc"): max(sd_fit, abs(b_fit) / 2.0)})
            stats["model_form_sd_b_conc"] = max(sd_fit, abs(b_fit) / 2.0)
        else:
            fitted, stats, pred = fit_amine(name, data[name], models)
        models[name] = fitted
        report[name] = stats
        fitted_pred[name] = pred
        print(f"{name}: n={stats['n_points']}  MAE={stats['mae_loading']:.3f}  "
              f"AARD={stats['aard_pct']:.1f}%  chi2_red={stats['chi2_reduced']:.2f}")
        for k, v in stats["params"].items():
            print(f"    {k:22s} prior {v['prior']:8.2f} -> fit {v['fit']:8.3f} +/- {v['sd']:.3f}")

    # MEA parameter sd: widen to inter-laboratory scale (see mea_interlab_inflation)
    k_mea, cov_raw, cov_k = mea_interlab_inflation(models)
    mea = models["MEA"]
    models["MEA"] = _set(mea, {(s.name, f): getattr(s, f) * k_mea for s in mea.species
                               for f in ("sd_logK", "sd_dH")})
    report["MEA"]["interlab_sd_inflation"] = {"factor": k_mea, "dugas_coverage90_raw": cov_raw,
                                              "dugas_coverage90_inflated": cov_k}
    print(f"MEA sd inflated x{k_mea:.2f} to inter-lab scale: parameter-only 90% coverage on "
          f"Dugas 2009 MEA {cov_raw:.2f} -> {cov_k:.2f}")

    # held-out blend
    blend = data["AMP+PZ"]
    obs = blend["loading"].to_numpy()
    nominal, lo, hi = mc_interval(blend, models)
    cov1 = coverage(obs, lo, hi)
    q_hat, logo = cqr(blend, lo, hi)
    lo_i, hi_i = lo - q_hat, hi + q_hat
    report["AMP+PZ_heldout"] = {
        "n_points": len(blend),
        "mae_loading_prior": float(np.mean(np.abs(prior_pred["AMP+PZ"] - obs))),
        "mae_loading_calibrated": float(np.mean(np.abs(nominal - obs))),
        "aard_pct_calibrated": float(100 * np.mean(np.abs(nominal - obs) / obs)),
        "bias_loading_calibrated": float(np.mean(nominal - obs)),
        "coverage90_param_only": cov1,
        "loading_discrepancy_q90": q_hat,
        "coverage90_cqr_leave_group_out": logo,
        "coverage90_cqr_leave_group_out_mean": float(np.mean(list(logo.values()))),
    }
    hb = report["AMP+PZ_heldout"]
    print(f"AMP+PZ held-out: MAE prior {hb['mae_loading_prior']:.3f} -> calibrated "
          f"{hb['mae_loading_calibrated']:.3f} (bias {hb['bias_loading_calibrated']:+.3f}); "
          f"90% coverage param-only {cov1:.2f}; CQR margin {q_hat:.3f} -> "
          f"leave-group-out coverage {hb['coverage90_cqr_leave_group_out_mean']:.2f} {logo}")

    # MDEA + PZ (Xu 2011): now part of the MDEA fit -> in-sample numbers + leave-one-blend-out
    xdf, x_nom, x_lo, x_hi, xrep = mdea_pz_validation(models, q_hat)
    xrep["leave_one_blend_out"] = lobo_mdea(data["MDEA"].iloc[:n_single_mdea], xu, models)
    report["MDEA+PZ_Xu2011"] = xrep
    print(f"MDEA+PZ (Xu 2011, n={xrep['n_points']}, 100-160 C, in fit): MAE "
          f"{xrep['mae_loading_per_alkalinity']:.3f} mol/mol alkalinity "
          f"(bias {xrep['bias_loading_per_alkalinity']:+.3f}); 90% coverage with margin "
          f"{xrep['coverage90_with_AMP_PZ_margin']:.2f}")
    for b_, v in xrep["leave_one_blend_out"].items():
        print(f"    leave-one-blend-out, {b_}: MAE {v['mae_loading_per_alkalinity']:.3f} "
              f"(bias {v['bias_loading_per_alkalinity']:+.3f})")

    # heat of absorption (MDEA): part of the joint MDEA fit
    h_prior = enthalpy_validation(prior)
    h_fit = enthalpy_validation(models)
    obs_h = h_fit["dH_solution_kj_per_mol"].to_numpy()
    report["MDEA_enthalpy_Arcis2008"] = {
        "n_points": len(h_fit), "used_in_fit": True,
        "mae_kj_per_mol_prior": float(np.mean(np.abs(h_prior["model_dH"] - obs_h))),
        "mae_kj_per_mol_calibrated": float(np.mean(np.abs(h_fit["model_dH"] - obs_h))),
        "bias_kj_per_mol_calibrated": float(np.mean(h_fit["model_dH"] - obs_h)),
    }
    he = report["MDEA_enthalpy_Arcis2008"]
    print(f"MDEA heat of absorption (Arcis 2008, n={he['n_points']}, in fit): MAE prior "
          f"{he['mae_kj_per_mol_prior']:.1f} -> calibrated {he['mae_kj_per_mol_calibrated']:.1f} kJ/mol "
          f"(bias {he['bias_kj_per_mol_calibrated']:+.1f})")

    # capacity benchmark vs Xu (2011) Table 2-12: is MDEA valued correctly relative to MEA?
    cap_after = capacity_benchmark(models)
    report["capacity_benchmark_Xu2011"] = {
        "definition": "40 C, PCO2* 0.5 -> 5 kPa, mol CO2/kg(amine+water)",
        "literature_priors": cap_prior.to_dict(orient="records"),
        "before_mdea_blend_fit": cap_before.to_dict(orient="records"),
        "calibrated": cap_after.to_dict(orient="records"),
    }
    print("Capacity benchmark (Xu 2011 Table 2-12; ratio to 7 m MEA):")
    for r0, r1, r2 in zip(cap_prior.itertuples(), cap_before.itertuples(), cap_after.itertuples()):
        print(f"    {r2.solvent:18s} Xu {r2.xu_vs_MEA:.2f} | priors {r0.model_vs_MEA:.2f} | "
              f"MDEA literature prior {r1.model_vs_MEA:.2f} | calibrated {r2.model_vs_MEA:.2f} "
              f"(abs {r2.model:.2f} vs {r2.xu_2011:.2f})")
    print("    (Xu's MEA value is from a concentration-independent empirical fit; the measured "
          "like-for-like benchmark is Dugas 2009 below)")

    # held-out MEA / PZ / MEA+PZ (Dugas 2009) + like-for-like capacity benchmark
    ddf, d_nom, d_lo, d_hi, drep, dcap = dugas_validation(models, q_hat)
    report["Dugas2009_heldout"] = drep
    print(f"Dugas 2009 HELD OUT (wetted-wall column, n={drep['n_points']}):")
    for s, v in drep["by_system"].items():
        print(f"    {s:6s} n={v['n']:2d}  MAE {v['mae_loading_per_alkalinity']:.3f} mol/mol alkalinity "
              f"(bias {v['bias_loading_per_alkalinity']:+.3f}); 90% coverage with margin "
              f"{v['coverage90_with_AMP_PZ_margin']:.2f}")
    print("Capacity benchmark, MEASURED (Dugas 2009, 40 C, 0.5 -> 5 kPa; ratio to 7 m MEA):")
    for r in dcap.itertuples():
        print(f"    {r.solvent:18s} data {r.dugas_vs_MEA:.2f} | model {r.model_vs_MEA:.2f} "
              f"(abs {r.model:.3f} vs {r.dugas_2009:.3f} mol/kg)")
    hb_x = heat_benchmark(models)
    report["heat_benchmark_Xu2011"] = hb_x.to_dict(orient="records")
    print("Heat-of-absorption benchmark (Xu 2011 Table 2-12, kJ/mol; model at 40/80/120 C):")
    for r in hb_x.itertuples():
        print(f"    {r.solvent:18s} Xu {r.xu_2011:5.1f} | model {r.model_40C:5.1f} / "
              f"{r.model_80C:5.1f} / {r.model_120C:5.1f}")

    report["Hilliard2008_heldout"] = hilliard_validation(models)
    print(f"Hilliard 2008 HELD OUT (per mol N): {report['Hilliard2008_heldout']}")
    report["Hilliard2008_heats"] = hilliard_heat_check(models)
    print("Hilliard 2008 calorimetry vs model heats:")
    for r in report["Hilliard2008_heats"]["by_group"]:
        print(f"    {r['T_C']:3d} C  PZ share of N {r['f_pz_N']:.2f}  n={r['n']:2d}  measured "
              f"{r['measured']:5.1f}  model bias {r['bias']:+.1f} kJ/mol")

    # DETA: the only partner amine with direct CO2 data
    deta_df = pd.read_csv(ROOT / "data" / "interim" / "deta_chang2013.csv").query("amine == 'DETA'")
    deta_theta, deta_sd, deta_chi2 = fit_deta(deta_df)
    report["DETA"] = deta_report(deta_df, deta_theta, deta_sd, deta_chi2, models)
    deta = deta_model(deta_theta, deta_sd)
    rd = report["DETA"]
    print(f"DETA (Chang 2013): n={rd['n_points']}  MAE={rd['mae_loading']:.3f}  "
          f"chi2_red={rd['chi2_reduced']:.2f}")
    for k, v in rd["params"].items():
        print(f"    {k:22s} prior {v['prior']:8.2f} -> fit {v['fit']:8.3f} +/- {v['sd']:.3f}")
    print(f"    leave-one-concentration-out: {rd['leave_one_concentration_out']}")
    print(f"    same-lab MEA check: {rd['same_lab_mea_check']}")
    report["DETA_blends_Wang2026"] = wang_check({**models, "DETA": deta})
    print("DETA ternary blends (Wang 2026, 323 K, 13 kPa, absorption capacity mol/kg):")
    for r in report["DETA_blends_Wang2026"]:
        print(f"    {r['blend']}  measured {r['measured_mol_per_kg']:.2f} | "
              f"model {r['model_mol_per_kg']:.2f}")

    # DEA and MPA: the partners that lead the practical list, checked against direct data
    pv = pd.read_csv(ROOT / "data" / "interim" / "dea_mpa_vle_thermoml.csv")
    arcis = pd.read_csv(ROOT / "data" / "interim" / "dea_enthalpy_arcis2012.csv")
    dea_heat = float(arcis.groupby("T")["dH_solution_kj_per_mol"].apply(lambda s: s.head(5).mean()).mean())
    calibrated_partners = {"DETA": deta}
    for name, heat in (("DEA", dea_heat), ("MPA", None)):
        fitted, st = fit_single_site(name, pv[pv["amine"] == name], heat)
        calibrated_partners[name] = fitted
        report[name] = st
        print(f"{name}: n={st['n_points']}  MAE prior {st['mae_prior']:.3f} -> fit {st['mae_loading']:.3f}  "
              f"chi2_red={st['chi2_reduced']:.2f}  {st['params']}")
    g = pv[pv["amine"] == "PZ"]
    b_pz = compile_batch([[(models["PZ"], m)] for m in g["m_amine"]])
    # Ghalib reports PZ loading per mol alkalinity: the model per mol PZ runs a steady 1.8x above it
    pz_pred = solve(b_pz, g["T"].to_numpy(), g["pCO2_kPa"].to_numpy())["loading"] / 2.0
    report["Ghalib2016_same_lab_PZ_check"] = {"n": len(g), "mae": float(np.mean(np.abs(pz_pred - g["loading"]))),
                                              "bias": float(np.mean(pz_pred - g["loading"]))}
    print(f"same-lab PZ check (Ghalib 2016): {report['Ghalib2016_same_lab_PZ_check']}")

    # save parameters
    payload = {"loading_discrepancy_q90": q_hat, "fit_report": report, "amines": {}, "partners": {
        n: {"smiles": m.smiles, "mw": m.mw, "source": m.source, "note": m.note,
            "sites": [[vars(s) for s in site.species] for site in m.site_models]}
        for n, m in calibrated_partners.items()}}
    for name, mdl in models.items():
        payload["amines"][name] = {
            "smiles": mdl.smiles, "mw": mdl.mw, "source": mdl.source, "note": mdl.note,
            "species": [vars(s) for s in mdl.species],
        }
    PARAMS_JSON.write_text(json.dumps(payload, indent=2))
    print("saved", PARAMS_JSON.relative_to(ROOT))

    # figures
    titles = {"MEA": "MEA (Wagner 2013 + Aronu 2011) - fitted", "MDEA": "MDEA (Leontiadis 2019, Dey 2018, + Xu 2011 MDEA+PZ) - fitted",
              "AMP": "AMP (Hartono 2020) - fitted", "PZ": "PZ (Ermatchkov 2006) - fitted"}
    fig, axes = plt.subplots(3, 3, figsize=(16, 14.4))
    for ax, name in zip(axes.flat, CORE_NAMES):
        parity_plot(ax, data[name], fitted_pred[name], titles[name])
    parity_plot(axes.flat[4], blend, nominal,
                f"AMP+PZ (Dash 2011) - HELD OUT, 90% CQR bands (+/-{q_hat:.3f})", lo_i, hi_i)
    parity_plot(axes.flat[5], xdf, x_nom,
                f"MDEA+PZ (Xu 2011, 100-160 C) - in MDEA fit\nleave-one-blend-out MAE "
                f"{max(v['mae_loading_per_alkalinity'] for v in xrep['leave_one_blend_out'].values()):.3f}; 90% "
                f"coverage {xrep['coverage90_with_AMP_PZ_margin']:.2f}", x_lo, x_hi)
    parity_plot(axes.flat[8], ddf, d_nom, "MEA, PZ, MEA+PZ (Dugas 2009) - HELD OUT\n"
                "loading per mol amine; 90% CQR bands", d_lo, d_hi)
    ax = axes.flat[7]
    # rows: Dugas solvents (measured, like-for-like), then Xu's MDEA/PZ blends (vs Xu's 7 m MEA)
    xu_rows = cap_after[cap_after["solvent"].str.contains("MDEA")]
    labels = [f"{s} (Dugas)" for s in dcap["solvent"]] + [f"{s} (Xu)" for s in xu_rows["solvent"]]
    yd = np.arange(len(dcap))
    yx = len(dcap) + np.arange(len(xu_rows))
    ax.plot(dcap["dugas_vs_MEA"], yd, "o", ms=9, color="#0b0b0b", label="measured (Dugas 2009)")
    ax.plot(xu_rows["xu_vs_MEA"], yx, "o", ms=9, mfc="none", color="#0b0b0b",
            label="Xu (2011) Table 2-12 (empirical fits)")
    ax.plot(cap_before.loc[xu_rows.index, "model_vs_MEA"], yx, "s", ms=7, mfc="none",
            color="#8c8b86", label="model, MDEA literature prior")
    ax.plot(np.r_[dcap["model_vs_MEA"], xu_rows["model_vs_MEA"]], np.r_[yd, yx], "D", ms=7,
            color="#2a78d6", label="model, calibrated")
    ax.set_yticks(np.r_[yd, yx])
    ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()
    ax.axvline(1.0, color="0.6", lw=0.8)
    ax.set_xlabel("cyclic capacity relative to 7 m MEA\n(40 C, PCO2* 0.5 -> 5 kPa)")
    ax.set_title("Is each solvent valued correctly vs MEA?", fontsize=10)
    ax.legend(fontsize=7, frameon=False, loc="upper right")
    ax = axes.flat[6]
    for (w, color) in zip(sorted(h_fit["w_amine"].unique()), ("#2a78d6", "#eb6834")):
        g = h_fit[h_fit["w_amine"] == w]
        ax.plot(g["loading"], -g["dH_solution_kj_per_mol"], "o", ms=5, color=color,
                label=f"measured, {w:.0%} MDEA")
        for i, (P, gp) in enumerate(g.groupby("P_kPa")):
            gp = gp.sort_values("loading")
            ax.plot(gp["loading"], -gp["model_dH"], "-", lw=1.2, color=color, alpha=0.8,
                    label=f"model, {w:.0%} MDEA (one line per pressure)" if i == 0 else None)
    ax.set_xlabel("CO$_2$ fed (mol / mol MDEA)")
    ax.set_ylabel("-$\\Delta H_{solution}$ (kJ / mol CO$_2$ fed)")
    ax.set_title(f"MDEA heat of absorption (Arcis 2008, 322.5 K) - in joint MDEA fit\n"
                 f"MAE {he['mae_kj_per_mol_calibrated']:.1f} kJ/mol", fontsize=10)
    ax.legend(fontsize=7, frameon=False)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "parity_calibration.png", dpi=160)

    fig, axes = plt.subplots(1, 5, figsize=(24, 4.8))
    for ax, name in zip(axes, list(CORE_NAMES) + ["AMP+PZ"]):
        parity_plot(ax, prior_data[name], prior_pred[name], f"{name} - literature priors only")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "parity_priors_only.png", dpi=160)
    print("figures ->", FIG_DIR.relative_to(ROOT))


if __name__ == "__main__":
    main()
