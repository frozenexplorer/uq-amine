"""
Ingest MEA and MDEA CO2-solubility (and MDEA heat-of-absorption) data from NIST ThermoML.

Raw files: data/raw/thermoml/<doi>.json, fetched automatically from
https://trc.nist.gov/ThermoML/<doi>.json when missing (data/raw/ is gitignored).
Every source is listed with its full citation in docs/data_sources.md.

    MEA   Wagner et al. 2013, J. Chem. Eng. Data 58, 883-895        DOI 10.1021/je301030z
            block 1: T, m_MEA, pCO2 -> m_CO2           (low loading, headspace GC)
            block 0: T, m_MEA, m_CO2 -> total pressure (high loading, synthetic method);
                     pCO2 = P - x_w * p_sat,H2O(T), kept only for pCO2 <= 2000 kPa
    MDEA  Leontiadis et al. 2019, Fluid Phase Equilib. 500, 112254  DOI 10.1016/j.fluid.2019.112254
            block 0: T, solvent mass fraction MDEA, pCO2 -> value labelled "mole fraction" in
                     ThermoML but numerically the LOADING (0.26-1.12 mol CO2/mol MDEA; a CO2
                     mole fraction of the liquid cannot exceed ~0.03 here)
          Dey et al. 2018, Fluid Phase Equilib. 463, 91-105        DOI 10.1016/j.fluid.2018.01.030
            block 7: 313.2 K, 30 mass% MDEA, pCO2 -> loading (same labelling as above)
    MDEA heat  Arcis et al. 2008, J. Chem. Thermodyn. 40, 1022-1029  DOI 10.1016/j.jct.2008.01.028
            block 3: 322.5 K, P, solvent mass fraction MDEA, x_CO2 -> molar enthalpy of
                     solution (kJ / mol CO2), integral heat; used for VALIDATION only

Not used (documented in docs/data_sources.md): Cheng et al. 2010 MDEA block (MDEA concentration
not recorded in the ThermoML file), Boettger 2009 / Speyer 2010 MDEA+PZ (ThermoML holds
only densities for these papers).

Outputs:
    data/interim/mea_mdea_vle_thermoml.csv      pCO2-loading points (MEA, MDEA)
    data/interim/mdea_enthalpy_arcis2008.csv    heat of absorption points (MDEA)

Run:  python -m src.data.ingest_thermoml_mea_mdea
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

from src.thermo.chemistry import MW_WATER, water_vapor_pressure_kpa

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "thermoml"
OUT_VLE = ROOT / "data" / "interim" / "mea_mdea_vle_thermoml.csv"
OUT_H = ROOT / "data" / "interim" / "mdea_enthalpy_arcis2008.csv"

MW = {"MEA": 61.08, "MDEA": 119.16}
MAX_PCO2_FROM_TOTAL = 2000.0


THERMOML_URL = "https://trc.nist.gov/ThermoML/{doi}.json"
FETCH_RETRIES = 4


def _raw_path(doi: str) -> Path:
    return RAW / (doi.replace("/", "_").replace("(", "_").replace(")", "_") + ".json")


def fetch(doi: str) -> Path:
    """data/raw/ is gitignored, so download the ThermoML file from NIST if it is missing."""
    path = _raw_path(doi)
    if not path.exists():
        RAW.mkdir(parents=True, exist_ok=True)
        # NIST rejects urllib's default User-Agent (HTTP 403)
        req = urllib.request.Request(THERMOML_URL.format(doi=doi),
                                     headers={"User-Agent": "amine-co2-uq/0.1 (research data ingestion)"})
        for attempt in range(FETCH_RETRIES):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    payload = r.read()
                break
            except (urllib.error.URLError, TimeoutError):   # NIST often answers 504
                if attempt == FETCH_RETRIES - 1:
                    raise
                time.sleep(5.0 * (attempt + 1))
        json.loads(payload)  # fail loudly on an HTML error page
        path.write_bytes(payload)
        print("downloaded", doi)
    return path


def _block(doi: str, b: int) -> dict:
    return json.loads(fetch(doi).read_text(encoding="utf-8"))["PureOrMixtureData"][b]


def _rows(pm: dict):
    for nv in pm["NumValues"]:
        v = {x["nVarNumber"]: x["nVarValue"] for x in nv["VariableValue"]}
        p = {x["nPropNumber"]: x["nPropValue"] for x in nv["PropertyValue"]}
        yield v, p


def _constraint(pm: dict, kind: str) -> float:
    for c in pm.get("Constraint", []):
        if kind in json.dumps(c["ConstraintID"]["ConstraintType"]):
            return float(c["nConstraintValue"])
    raise KeyError(kind)


def molality_from_solvent_wfrac(w: float, mw: float) -> float:
    return w / mw * 1000.0 / (1.0 - w)


def wagner_mea() -> pd.DataFrame:
    doi = "10.1021/je301030z"
    src = "Wagner et al. (2013)"
    out = []
    for v, p in _rows(_block(doi, 1)):
        T, m_a, pco2, m_c = v[1], v[2], v[3], p[1]
        out.append(dict(amine="MEA", T=T, pCO2_kPa=pco2, m_amine=m_a, loading=m_c / m_a,
                        method="headspace GC, measured pCO2", source=src, doi=doi))
    for v, p in _rows(_block(doi, 0)):
        T, m_a, m_c, P = v[1], v[2], v[3], p[1]
        x_w = (1000.0 / MW_WATER) / (1000.0 / MW_WATER + m_a + m_c)
        pco2 = P - x_w * float(water_vapor_pressure_kpa(T))
        if 0 < pco2 <= MAX_PCO2_FROM_TOTAL:
            out.append(dict(amine="MEA", T=T, pCO2_kPa=pco2, m_amine=m_a, loading=m_c / m_a,
                            method="synthetic, pCO2 = P - x_w p_sat", source=src, doi=doi))
    return pd.DataFrame(out)


def leontiadis_mdea() -> pd.DataFrame:
    doi = "10.1016/j.fluid.2019.112254"
    out = []
    for v, p in _rows(_block(doi, 0)):
        T, w, pco2, alpha = v[1], v[2], v[3], p[1]
        out.append(dict(amine="MDEA", T=T, pCO2_kPa=pco2,
                        m_amine=molality_from_solvent_wfrac(w, MW["MDEA"]), loading=alpha,
                        method="pressure decay", source="Leontiadis et al. (2019)", doi=doi))
    return pd.DataFrame(out)


def dey_mdea() -> pd.DataFrame:
    doi = "10.1016/j.fluid.2018.01.030"
    pm = _block(doi, 7)
    T = _constraint(pm, "Temperature")
    w = _constraint(pm, "Solvent: Mass fraction")
    out = []
    for v, p in _rows(pm):
        out.append(dict(amine="MDEA", T=T, pCO2_kPa=v[1],
                        m_amine=molality_from_solvent_wfrac(w, MW["MDEA"]), loading=p[1],
                        method="phase equilibration", source="Dey et al. (2018)", doi=doi))
    return pd.DataFrame(out)


def arcis_mdea_enthalpy() -> pd.DataFrame:
    doi = "10.1016/j.jct.2008.01.028"
    pm = _block(doi, 3)
    T = _constraint(pm, "Temperature")
    out = []
    for v, p in _rows(pm):
        P, w, x = v[1], v[2], v[3]
        n_a = w / MW["MDEA"] * 1000.0               # per kg of CO2-free solvent
        n_w = (1.0 - w) / MW_WATER * 1000.0
        n_c = x * (n_a + n_w) / (1.0 - x)
        out.append(dict(amine="MDEA", T=T, P_kPa=P, w_amine=w,
                        m_amine=molality_from_solvent_wfrac(w, MW["MDEA"]),
                        loading=n_c / n_a, dH_solution_kj_per_mol=p[1],
                        source="Arcis et al. (2008)", doi=doi))
    return pd.DataFrame(out)


def main():
    vle = pd.concat([wagner_mea(), leontiadis_mdea(), dey_mdea()], ignore_index=True)
    assert vle[["T", "pCO2_kPa", "m_amine", "loading"]].notna().all().all()
    assert (vle.loading > 0).all() and (vle.pCO2_kPa > 0).all()
    h = arcis_mdea_enthalpy()
    OUT_VLE.parent.mkdir(parents=True, exist_ok=True)
    vle.to_csv(OUT_VLE, index=False)
    h.to_csv(OUT_H, index=False)
    for (a, s), g in vle.groupby(["amine", "source"]):
        print(f"{a:5s} {s:26s} n={len(g):3d}  T {g['T'].min():.0f}-{g['T'].max():.0f} K  "
              f"m {g.m_amine.min():.2f}-{g.m_amine.max():.2f} mol/kg  "
              f"pCO2 {g.pCO2_kPa.min():.3g}-{g.pCO2_kPa.max():.4g} kPa  "
              f"loading {g.loading.min():.3f}-{g.loading.max():.3f}")
    print(f"MDEA enthalpy (Arcis 2008): n={len(h)}, loading {h.loading.min():.2f}-{h.loading.max():.2f}, "
          f"dH {h.dH_solution_kj_per_mol.min():.1f} to {h.dH_solution_kj_per_mol.max():.1f} kJ/mol")
    print("->", OUT_VLE.relative_to(ROOT), "|", OUT_H.relative_to(ROOT))


if __name__ == "__main__":
    main()
