"""
MDEA + PZ blend CO2 solubility at stripper temperatures (100-160 C), transcribed from

    Xu, Q. "Thermodynamics of CO2 Loaded Aqueous Amines." PhD Dissertation,
    The University of Texas at Austin, 2011 (supervisor G. T. Rochelle).
    Open copy: https://sites.utexas.edu/rochelle/wp-content/uploads/sites/3310/2015/02/
               Xu-2011-Thermodynamics-of-CO2-Loaded-Aqueous-Amines.pdf
    Table 2-8: 7 m MDEA / 2 m PZ (20 points)     Table 2-9: 5 m MDEA / 5 m PZ (13 points)

In the thesis, "Amine m" is the TOTAL ALKALINITY (mol N / kg water; MDEA has 1 basic N,
PZ has 2) and loading is mol CO2 / mol alkalinity. pCO2 was obtained from the measured
total pressure minus water (and amine) partial pressures. Point count (33) matches the
Barbieri & Moioli (2025) review, Table 3.

Used in the JOINT MDEA calibration (src/thermo/calibrate.py): it is the only MDEA data at
stripper temperatures (single-MDEA data stop at 333 K). As a held-out test (before it was
fitted) it exposed a +0.073 mol/mol-alkalinity bias -- the model kept too much CO2 in MDEA at
100-160 C -- and showed that the AMP+PZ conformal margin transfers (100 % coverage).
Generalisation is now checked leave-one-blend-out.

Output: data/interim/mdea_pz_xu2011.csv
Run:    python -m src.data.ingest_xu2011_mdea_pz
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "interim" / "mdea_pz_xu2011.csv"

# Transcribed verbatim from the thesis tables (columns: alkalinity m, T C, loading
# mol CO2/mol alkalinity, pCO2 kPa, total pressure kPa). The thesis prints two
# side-by-side column groups per table; they are listed here row-group by row-group.
TABLE_2_8 = """
10.51 110 0.133 78 202
10.51 120 0.132 136 307
10.51 130 0.129 226 460
10.51 140 0.125 355 668
10.51 150 0.119 553 964
10.51 160 0.113 787 1321
10.49 100 0.236 253 341
10.49 110 0.232 411 535
10.49 120 0.225 634 806
10.49 130 0.216 962 1196
10.49 140 0.205 1376 1688
10.49 150 0.193 1866 2278
10.49 160 0.177 2477 3011
10.71 100 0.234 189 276
10.71 110 0.229 346 470
10.71 120 0.223 527 698
10.71 130 0.214 827 1060
10.71 140 0.203 1181 1492
10.71 150 0.191 1609 2019
10.71 160 0.178 2054 2587
"""

TABLE_2_9 = """
14.43 110 0.221 98 220
14.43 120 0.219 173 342
14.43 130 0.216 298 528
14.43 140 0.212 489 796
14.43 150 0.206 760 1165
14.43 160 0.197 1144 1670
14.61 100 0.277 111 197
14.61 110 0.275 204 326
14.61 120 0.271 350 519
14.61 130 0.266 567 797
14.61 140 0.259 901 1208
14.61 150 0.250 1289 1693
14.61 160 0.240 1776 2301
"""

# mol ratio MDEA : PZ, so alkalinity A = r_MDEA*k + 2*r_PZ*k
BLENDS = {"7 m MDEA / 2 m PZ": (TABLE_2_8, 7.0, 2.0, "Table 2-8"),
          "5 m MDEA / 5 m PZ": (TABLE_2_9, 5.0, 5.0, "Table 2-9")}


def build() -> pd.DataFrame:
    rows = []
    for label, (txt, r_mdea, r_pz, table) in BLENDS.items():
        for line in txt.strip().splitlines():
            alk, t_c, ldg, pco2, pt = map(float, line.split())
            k = alk / (r_mdea + 2.0 * r_pz)
            rows.append(dict(blend=label, table=table, T=t_c + 273.15, pCO2_kPa=pco2,
                             P_total_kPa=pt, alkalinity_m=alk, m_MDEA=r_mdea * k, m_PZ=r_pz * k,
                             loading_per_alkalinity=ldg, n_co2=ldg * alk,
                             source="Xu (2011) PhD thesis, UT Austin"))
    return pd.DataFrame(rows)


def main():
    df = build()
    assert len(df) == 33, len(df)
    assert (df.pCO2_kPa < df.P_total_kPa).all()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    for b, g in df.groupby("blend"):
        print(f"{b}: n={len(g)}  T {g['T'].min() - 273.15:.0f}-{g['T'].max() - 273.15:.0f} C  "
              f"pCO2 {g.pCO2_kPa.min():.0f}-{g.pCO2_kPa.max():.0f} kPa  "
              f"m_MDEA {g.m_MDEA.mean():.2f}  m_PZ {g.m_PZ.mean():.2f}")
    print("->", OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
