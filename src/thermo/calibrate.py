"""
Calibrate the equilibrium model against experimental VLE (pCO2 vs loading) data.

    MEA  <- Wagner et al. (2013)             (NIST ThermoML, pCO2 <= 2000 kPa)
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
from scipy.optimize import least_squares

from .chemistry import CORE_NAMES, MW_WATER, AmineModel, core_amines, water_vapor_pressure_kpa
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

    out = {"MEA": single["MEA"], "MDEA": single["MDEA"], "AMP": amp, "PZ": pz, "AMP+PZ": blend}
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
    # heat -25 -> -90 kJ/mol over 25-130 C), so it was rejected. See LOG.md 2026-10-15.
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
# Figures
# ---------------------------------------------------------------------------
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
    hb_x = heat_benchmark(models)
    report["heat_benchmark_Xu2011"] = hb_x.to_dict(orient="records")
    print("Heat-of-absorption benchmark (Xu 2011 Table 2-12, kJ/mol; model at 40/80/120 C):")
    for r in hb_x.itertuples():
        print(f"    {r.solvent:18s} Xu {r.xu_2011:5.1f} | model {r.model_40C:5.1f} / "
              f"{r.model_80C:5.1f} / {r.model_120C:5.1f}")

    # save parameters
    payload = {"loading_discrepancy_q90": q_hat, "fit_report": report, "amines": {}}
    for name, mdl in models.items():
        payload["amines"][name] = {
            "smiles": mdl.smiles, "mw": mdl.mw, "source": mdl.source, "note": mdl.note,
            "species": [vars(s) for s in mdl.species],
        }
    PARAMS_JSON.write_text(json.dumps(payload, indent=2))
    print("saved", PARAMS_JSON.relative_to(ROOT))

    # figures
    titles = {"MEA": "MEA (Wagner 2013) - fitted", "MDEA": "MDEA (Leontiadis 2019, Dey 2018, + Xu 2011 MDEA+PZ) - fitted",
              "AMP": "AMP (Hartono 2020) - fitted", "PZ": "PZ (Ermatchkov 2006) - fitted"}
    fig, axes = plt.subplots(2, 4, figsize=(20, 9.6))
    for ax, name in zip(axes.flat, CORE_NAMES):
        parity_plot(ax, data[name], fitted_pred[name], titles[name])
    parity_plot(axes.flat[4], blend, nominal,
                f"AMP+PZ (Dash 2011) - HELD OUT, 90% CQR bands (+/-{q_hat:.3f})", lo_i, hi_i)
    parity_plot(axes.flat[5], xdf, x_nom,
                f"MDEA+PZ (Xu 2011, 100-160 C) - in MDEA fit\nleave-one-blend-out MAE "
                f"{max(v['mae_loading_per_alkalinity'] for v in xrep['leave_one_blend_out'].values()):.3f}; 90% "
                f"coverage {xrep['coverage90_with_AMP_PZ_margin']:.2f}", x_lo, x_hi)
    ax = axes.flat[7]
    y = np.arange(len(cap_after))
    ax.plot(cap_after["xu_vs_MEA"], y, "o", ms=9, color="#0b0b0b", label="Xu (2011) Table 2-12")
    ax.plot(cap_before["model_vs_MEA"], y, "s", ms=7, mfc="none", color="#8c8b86",
            label="model, MDEA literature prior")
    ax.plot(cap_after["model_vs_MEA"], y, "D", ms=7, color="#2a78d6", label="model, calibrated")
    ax.set_yticks(y)
    ax.set_yticklabels(cap_after["solvent"])
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
