"""
DEA and MPA pCO2-loading data and DEA heats of solution from NIST ThermoML.

    DEA  Ghalib, L.; Ali, B. S.; Ashri, W. M.; Mazari, S. Fluid Phase Equilib. 2016, 414, 1-13.
         DOI 10.1016/j.fluid.2015.12.056. 15 points, 2 M DEA, 313-353 K. The same record has
         12 points for 1 M PZ, used only to check the laboratory against the PZ model. Its
         DEA + PZ blends are not in the record.
    MPA  Leontiadis et al. 2019, DOI 10.1016/j.fluid.2019.112254 (3-amino-1-propanol block).
         60 points, 10 and 15 wt%, 298-333 K.
    Heat Arcis, H.; Ballerat-Busserolles, K.; Rodier, L.; Coxam, J.-Y. J. Chem. Eng. Data 2012,
         57, 840-855. DOI 10.1021/je201012e. 30 wt% DEA, 322.5 and 372.9 K.

ThermoML labels the Ghalib and Leontiadis loadings "mole fraction"; the values are loadings,
as with the MDEA blocks in ingest_thermoml_mea_mdea.py. Ghalib's PZ loadings are per mol of
alkalinity (DEA has one N, so the DEA points are unaffected).

Outputs: data/interim/dea_mpa_vle_thermoml.csv, data/interim/dea_enthalpy_arcis2012.csv
Run:     python -m src.data.ingest_dea_mpa_thermoml
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.data.ingest_thermoml_mea_mdea import _block, _rows

ROOT = Path(__file__).resolve().parents[2]
OUT_VLE = ROOT / "data" / "interim" / "dea_mpa_vle_thermoml.csv"
OUT_H = ROOT / "data" / "interim" / "dea_enthalpy_arcis2012.csv"

GHALIB = "10.1016/j.fluid.2015.12.056"
LEONTIADIS = "10.1016/j.fluid.2019.112254"
ARCIS = "10.1021/je201012e"
MW = {"DEA": 105.14, "PZ": 86.14, "MPA": 75.11}
# Molarity to molality with an approximate solution density (kg/L).
DENSITY = {"DEA": 1.02, "PZ": 1.00}


def _molality_from_molarity(c: float, name: str) -> float:
    w = c * MW[name] / 1000.0 / DENSITY[name]
    return w / MW[name] * 1000.0 / (1.0 - w)


def main():
    rows = []
    for block, name, c in ((1, "DEA", 2.0), (0, "PZ", 1.0)):
        for v, p in _rows(_block(GHALIB, block)):
            rows.append(dict(amine=name, T=v[1], pCO2_kPa=v[2], m_amine=_molality_from_molarity(c, name),
                             loading=p[1], source="Ghalib et al. (2016)", doi=GHALIB))
    for v, p in _rows(_block(LEONTIADIS, 1)):
        T, w, pco2 = v[1], v[2], v[3]
        rows.append(dict(amine="MPA", T=T, pCO2_kPa=pco2, m_amine=w / MW["MPA"] * 1000.0 / (1.0 - w),
                         loading=p[1], source="Leontiadis et al. (2019)", doi=LEONTIADIS))
    vle = pd.DataFrame(rows)
    h = pd.DataFrame([dict(T=v[1], P_kPa=v[2], x_co2=v[3], dH_solution_kj_per_mol=p[1])
                      for v, p in _rows(_block(ARCIS, 2))])
    OUT_VLE.parent.mkdir(parents=True, exist_ok=True)
    vle.to_csv(OUT_VLE, index=False)
    h.to_csv(OUT_H, index=False)
    for a, g in vle.groupby("amine"):
        print(f"{a:4s} n={len(g):3d}  T {g['T'].min():.0f}-{g['T'].max():.0f} K  "
              f"pCO2 {g.pCO2_kPa.min():.3g}-{g.pCO2_kPa.max():.4g} kPa  "
              f"loading {g.loading.min():.2f}-{g.loading.max():.2f}")
    print(f"DEA heats (Arcis 2012): n={len(h)}, first points {h['dH_solution_kj_per_mol'].head(3).tolist()}")
    print("->", OUT_VLE.relative_to(ROOT), "|", OUT_H.relative_to(ROOT))


if __name__ == "__main__":
    main()
