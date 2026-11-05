"""
DETA pCO2-loading data from NIST ThermoML.

    Chang, Y.-C.; Leron, R. B.; Li, M.-H. "Equilibrium solubility of carbon dioxide in
    aqueous solutions of (diethylenetriamine + piperazine)." J. Chem. Thermodyn. 2013, 64,
    106-113. DOI 10.1016/j.jct.2013.05.005

Block 1: 84 points, 20 / 30 / 40 wt% DETA, 313.2 and 353.2 K, pCO2 0.8-937 kPa, loading in
mol CO2 / mol DETA. The record stores composition as the water : DETA mass ratio
(4 / 2.333 / 1.5). Block 0: 12 MEA points from the same apparatus, used only to check that
this laboratory agrees with the MEA data the model is fitted on.

The paper's 333.2 K points and its DETA + PZ blends are NOT in the ThermoML record.

Output: data/interim/deta_chang2013.csv
Run:    python -m src.data.ingest_chang2013_deta
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.data.ingest_thermoml_mea_mdea import _block, _rows

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "interim" / "deta_chang2013.csv"

DOI = "10.1016/j.jct.2013.05.005"
SOURCE = "Chang et al. (2013)"
MW_DETA = 103.17
MW_MEA = 61.08
MEA_T_K = 313.2
MEA_WATER_RATIO = 5.536  # block 0 constraint: mass ratio water : MEA (about 15 wt% MEA)


def main():
    out = []
    for v, p in _rows(_block(DOI, 1)):
        w = 1.0 / (1.0 + v[2])
        out.append(dict(amine="DETA", T=v[1], pCO2_kPa=v[3], w_amine=w,
                        m_amine=w / MW_DETA * 1000.0 / (1.0 - w), loading=p[1],
                        source=SOURCE, doi=DOI))
    for v, p in _rows(_block(DOI, 0)):
        out.append(dict(amine="MEA", T=MEA_T_K, pCO2_kPa=v[1],
                        w_amine=1.0 / (1.0 + MEA_WATER_RATIO),
                        m_amine=1000.0 / (MEA_WATER_RATIO * MW_MEA), loading=p[1],
                        source=SOURCE, doi=DOI))
    df = pd.DataFrame(out)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    for a, g in df.groupby("amine"):
        print(f"{a:5s} n={len(g):3d}  T {g['T'].min():.0f}-{g['T'].max():.0f} K  "
              f"pCO2 {g.pCO2_kPa.min():.3g}-{g.pCO2_kPa.max():.4g} kPa  "
              f"loading {g.loading.min():.3f}-{g.loading.max():.3f}")
    print("->", OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
