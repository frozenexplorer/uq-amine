"""
40 C viscosity of aqueous amines from NIST ThermoML, and the mixture rule used by the
practical stage (src/screening/practical.py):

    ln(mu / mu_water) = (sum_i a_i w_i) * (1 + b * loading_per_alkalinity)

w_i = amine mass fraction, loading in mol CO2 / mol basic N. a_i is fitted per amine and b is
shared. Only points with total amine <= 40 wt% are used, the range the screen works in.

    MEA   Amundsen et al. 2009, loaded and unloaded        10.1021/je900188m
    PZ    Freeman & Rochelle 2011, loaded and unloaded     10.1021/je1012263
    MDEA  Bernal-Garcia et al. 2004; Paul & Mandal 2006    10.1021/je0302250, 10.1021/je060195b
    AMP   Paul & Mandal 2006, AMP + PZ blends              10.1021/je060195b
    DETA  Hartono & Svendsen 2009                          10.1016/j.jct.2008.11.012

Outputs: data/interim/viscosity_thermoml.csv, data/processed/practical/viscosity_fit.json
Run:     python -m src.data.ingest_viscosity_thermoml
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import least_squares

from src.data.ingest_thermoml_mea_mdea import _block, _rows
from src.thermo.chemistry import MW_CO2, MW_WATER

ROOT = Path(__file__).resolve().parents[2]
OUT_CSV = ROOT / "data" / "interim" / "viscosity_thermoml.csv"
OUT_FIT = ROOT / "data" / "processed" / "practical" / "viscosity_fit.json"

AMINES = ("MEA", "MDEA", "AMP", "PZ", "DETA")
MW = {"MEA": 61.08, "MDEA": 119.16, "AMP": 89.14, "PZ": 86.14, "DETA": 103.17}
N_SITES = {"MEA": 1, "MDEA": 1, "AMP": 1, "PZ": 2, "DETA": 3}
T_K, T_TOL = 313.15, 0.6
MAX_W = 0.40
MU_WATER_40C = 0.655    # mPa s, Hartono & Svendsen (2009) at 313.15 K


def _at_40c(doi: str, block: int):
    for v, p in _rows(_block(doi, block)):
        if abs(v[1] - T_K) < T_TOL:
            yield v, p[1] * 1000.0


def _row(source, mu, alpha=0.0, **w):
    return {"source": source, "mu_mpas": mu, "alpha": alpha,
            **{f"w_{a}": w.get(a, 0.0) for a in AMINES}}


def _w_from_x(x: float, mw: float) -> float:
    return x * mw / (x * mw + (1.0 - x) * MW_WATER)


def load() -> pd.DataFrame:
    rows = []
    doi = "10.1021/je900188m"
    for v, mu in _at_40c(doi, 4):                     # x_CO2, x_MEA
        x_c, x_a = v[2], v[3]
        x_w = 1.0 - x_c - x_a
        if x_a <= 0 or x_w <= 0:
            continue
        w = x_a * MW["MEA"] / (x_a * MW["MEA"] + x_w * MW_WATER)
        rows.append(_row("Amundsen 2009", mu, x_c / x_a, MEA=w))
    doi = "10.1021/je1012263"
    for v, mu in _at_40c(doi, 2):
        # ThermoML labels these "Molality" but they are mol per kg of SOLUTION: the paper's
        # abstract gives (1.5 to 7.0) mol/kg as (2 to 20) molal PZ.
        n_p, n_c = v[2], v[3]
        w = n_p * MW["PZ"] / (1000.0 - n_c * MW_CO2)      # CO2-free mass fraction
        rows.append(_row("Freeman 2011", mu, n_c / (2.0 * n_p), PZ=w))
    for v, mu in _at_40c("10.1021/je0302250", 1):     # x_MDEA
        if v[2] > 0:
            rows.append(_row("Bernal-Garcia 2004", mu, MDEA=_w_from_x(v[2], MW["MDEA"])))
    doi = "10.1021/je060195b"
    for v, mu in _at_40c(doi, 2):
        rows.append(_row("Paul 2006", mu, MDEA=v[2]))
    for v, mu in _at_40c(doi, 4):
        rows.append(_row("Paul 2006", mu, PZ=v[2], MDEA=v[3]))
    for v, mu in _at_40c(doi, 6):
        rows.append(_row("Paul 2006", mu, PZ=v[2], AMP=v[3]))
    for v, mu in _at_40c("10.1016/j.jct.2008.11.012", 5):
        if v[2] > 0:
            rows.append(_row("Hartono 2009", mu, DETA=_w_from_x(v[2], MW["DETA"])))
    df = pd.DataFrame(rows)
    return df[df[[f"w_{a}" for a in AMINES]].sum(axis=1) <= MAX_W].reset_index(drop=True)


def fit(df: pd.DataFrame) -> dict:
    W = df[[f"w_{a}" for a in AMINES]].to_numpy()
    y = np.log(df["mu_mpas"] / MU_WATER_40C).to_numpy()
    alpha = df["alpha"].to_numpy()

    def resid(th):
        return (W @ th[:-1]) * (1.0 + th[-1] * alpha) - y

    r = least_squares(resid, np.r_[np.full(len(AMINES), 4.0), 1.0])
    return {"a": dict(zip(AMINES, r.x[:-1].round(3).tolist())), "b": round(float(r.x[-1]), 3),
            "mu_water_40C_mpas": MU_WATER_40C, "n_points": len(df),
            "rms_ln_mu": float(np.sqrt(np.mean(r.fun ** 2))),
            "points_by_source": df["source"].value_counts().to_dict()}


def main():
    df = load()
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    OUT_FIT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_CSV, index=False)
    res = fit(df)
    OUT_FIT.write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))
    for a, w in (("MEA", 0.3), ("MDEA", 0.3), ("AMP", 0.3), ("PZ", 0.3), ("DETA", 0.3)):
        print(f"30 wt% {a:5s}: {MU_WATER_40C * np.exp(res['a'][a] * w):.2f} mPa s unloaded, "
              f"{MU_WATER_40C * np.exp(res['a'][a] * w * (1 + res['b'] * 0.5)):.2f} at 0.5 mol/mol N")


if __name__ == "__main__":
    main()
