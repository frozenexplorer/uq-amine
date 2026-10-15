"""
Calibrate the equilibrium model against experimental VLE (pCO2 vs loading) data.

    AMP  <- Hartono et al. (2020)            (rows with a measured CO2 partial pressure)
    PZ   <- Ermatchkov et al. (2006)
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

from .chemistry import AmineModel, core_amines
from .equilibrium import compile_batch, sample_batch, solve

ROOT = Path(__file__).resolve().parents[2]
STRUCT = ROOT / "data" / "processed" / "structured"
OUT_DIR = ROOT / "data" / "processed" / "thermo"
FIG_DIR = ROOT / "reports" / "figures" / "calibration"
PARAMS_JSON = OUT_DIR / "calibrated_core_amines.json"

SIGMA_ABS = 0.02   # loading observation noise, mol CO2 / mol amine
SIGMA_REL = 0.03


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
    for df in (amp, pz, blend):
        df.reset_index(drop=True, inplace=True)
    return {"AMP": amp, "PZ": pz, "AMP+PZ": blend}


def _mixtures(df: pd.DataFrame, models: dict):
    out = []
    for a, z in zip(df["m_AMP"], df["m_PZ"]):
        mix = []
        if a > 0:
            mix.append((models["AMP"], a))
        if z > 0:
            mix.append((models["PZ"], z))
        out.append(mix)
    return out


def predict_loading(df: pd.DataFrame, models: dict) -> np.ndarray:
    b = compile_batch(_mixtures(df, models))
    return solve(b, df["T"].to_numpy(), df["p"].to_numpy())["loading"]


# ---------------------------------------------------------------------------
# Parameterisation: which species constants are free for each amine
# ---------------------------------------------------------------------------
FREE = {
    "AMP": [("AMPH+", "logK25"), ("AMPH+", "dH"), ("AMPCOO-", "logK25"), ("AMPCOO-", "dH")],
    "PZ": [("PZH+", "logK25"), ("PZH+", "dH"), ("PZCOO-", "logK25"), ("PZCOO-", "dH"),
           ("H+PZCOO-", "logK25"), ("H+PZCOO-", "dH"), ("PZ(COO-)2", "logK25"),
           ("PZ(COO-)2", "dH")],
}
# Prior sigma used for regularisation (looser than the MC sd of the literature prior;
# apparent KE constants legitimately drift from thermodynamic values).
PRIOR_SIGMA = {"logK25": 0.6, "dH": 12.0}


def _get(model: AmineModel, sp_name: str, field: str) -> float:
    return getattr(next(s for s in model.species if s.name == sp_name), field)


def _set(model: AmineModel, values: dict) -> AmineModel:
    species = []
    for s in model.species:
        upd = {f: v for (n, f), v in values.items() if n == s.name}
        species.append(replace(s, **upd) if upd else s)
    return model.with_species(species)


def fit_amine(name: str, df: pd.DataFrame, models: dict) -> tuple:
    base = models[name]
    keys = FREE[name]
    theta0 = np.array([_get(base, n, f) for n, f in keys])
    psig = np.array([PRIOR_SIGMA[f] for _, f in keys])
    obs = df["loading"].to_numpy()
    sig = SIGMA_ABS + SIGMA_REL * obs

    def model_for(theta):
        return {**models, name: _set(base, dict(zip(keys, theta)))}

    def resid(theta):
        pred = predict_loading(df, model_for(theta))
        return np.concatenate([(pred - obs) / sig, (theta - theta0) / psig])

    res = least_squares(resid, theta0, method="trf", x_scale=psig, diff_step=1e-4)
    n_data = len(obs)
    r_data = res.fun[:n_data]
    chi2_red = float(np.sum(r_data ** 2) / max(n_data - len(theta0), 1))
    J = res.jac
    cov = np.linalg.pinv(J.T @ J) * max(chi2_red, 1.0)
    sd = np.sqrt(np.clip(np.diag(cov), 0, None))

    fitted = _set(base, dict(zip(keys, res.x)))
    # posterior sd into the species uncertainty fields
    sd_vals = {}
    for (n, f), s in zip(keys, sd):
        sd_vals[(n, "sd_logK" if f == "logK25" else "sd_dH")] = float(s)
    fitted = _set(fitted, sd_vals)
    fitted.source = "calibrated"
    fitted.note = f"MAP fit to {n_data} pCO2-loading points"

    pred = predict_loading(df, {**models, name: fitted})
    stats = {
        "n_points": n_data,
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

    models = dict(prior)
    report = {}
    fitted_pred = {}
    for name in ("AMP", "PZ"):
        fitted, stats, pred = fit_amine(name, data[name], models)
        models[name] = fitted
        report[name] = stats
        fitted_pred[name] = pred
        print(f"{name}: n={stats['n_points']}  MAE={stats['mae_loading']:.3f}  "
              f"AARD={stats['aard_pct']:.1f}%  chi2_red={stats['chi2_reduced']:.2f}")
        for k, v in stats["params"].items():
            print(f"    {k:22s} prior {v['prior']:8.2f} -> fit {v['fit']:8.2f} +/- {v['sd']:.2f}")

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
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8))
    parity_plot(axes[0], data["AMP"], fitted_pred["AMP"], "AMP (Hartono 2020) - fitted")
    parity_plot(axes[1], data["PZ"], fitted_pred["PZ"], "PZ (Ermatchkov 2006) - fitted")
    parity_plot(axes[2], blend, nominal,
                f"AMP+PZ (Dash 2011) - HELD OUT, 90% CQR bands (+/-{q_hat:.3f})", lo_i, hi_i)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "parity_calibration.png", dpi=160)

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8))
    parity_plot(axes[0], data["AMP"], prior_pred["AMP"], "AMP - literature priors only")
    parity_plot(axes[1], data["PZ"], prior_pred["PZ"], "PZ - literature priors only")
    parity_plot(axes[2], blend, prior_pred["AMP+PZ"], "AMP+PZ - literature priors only")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "parity_priors_only.png", dpi=160)
    print("figures ->", FIG_DIR.relative_to(ROOT))


if __name__ == "__main__":
    main()
