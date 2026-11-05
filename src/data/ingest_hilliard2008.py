"""
MEA, PZ and MEA+PZ data from Hilliard (2008), UT Austin PhD thesis (Appendices D and I).

    D.4  H2O-MEA-CO2       3.5 / 7 / 11 m MEA, 40 and 60 C
    D.5  H2O-PZ-CO2        0.9-5 m PZ, 40 and 60 C
    D.7  H2O-MEA-PZ-CO2    7/2, 3.5/2, 7/3.6, 3.5/3.6 m MEA/PZ, 40 and 60 C
    H.1, H.4, H.5          differential heat of absorption (NTNU calorimeter), 2.4 m PZ and
                           7 m MEA + 2 / 3.5 m PZ, 40 / 80 / 120 C
    I.1  H2O-PZ            dissolution (liquidus) temperature against PZ mass fraction

Each VLE row has pCO2, the measured amine partial pressures and the loading, stored per mol of
basic N (D.4 per mol MEA, D.5 and D.7 per mol MEA + 2 mol PZ, as printed).

Two PDF-text problems are handled explicitly:
  * The 7 m MEA / 2 m PZ, 40 C block of D.7 extracts with its pressure columns one row low, so
    it is transcribed by hand in MEA_PZ_7_2_40C (the other three blends confirm the alignment).
  * The 3.5 m MEA / 3.6 m PZ pCO2 column is printed to one decimal in the extracted text; points
    below 0.5 kPa carry almost no information and are dropped.

The PDF is gitignored and the outputs are tracked, so this step quietly keeps the stored tables
when the PDF is missing.

Outputs: data/interim/hilliard2008_vle.csv, data/interim/hilliard2008_pz_sle.csv,
         data/interim/hilliard2008_heats.csv
Run:     python -m src.data.ingest_hilliard2008
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pandas as pd

from src.data.ingest_aronu2011_mea import _pdftotext

ROOT = Path(__file__).resolve().parents[2]
PDF = ROOT / "data" / "raw" / "hilliard_2008_thesis" / "hilliard_2008_predictive_thermo_model_k2co3_pz_mea.pdf"
OUT_VLE = ROOT / "data" / "interim" / "hilliard2008_vle.csv"
OUT_SLE = ROOT / "data" / "interim" / "hilliard2008_pz_sle.csv"
OUT_HEAT = ROOT / "data" / "interim" / "hilliard2008_heats.csv"

NUM = r"(\d+\.?\d*)"
DATE = r"\d{2}/\d{2}/\d{2}"
SOLN = r"\S+"
ROW_MEA = re.compile(rf"^\s*{NUM}\s+{DATE}\s+{NUM}\s+{SOLN}\s+{NUM}\s+{NUM}\s+{NUM}\s+{NUM}\s*$")
ROW_BLEND = re.compile(rf"^\s*{NUM}\s+{NUM}\s+{DATE}\s+{NUM}\s+{SOLN}\s+{NUM}\s+{NUM}\s+{NUM}\s+{NUM}\s+{NUM}\s*$")
ROW_HEAT = re.compile(r"^\s*(\d+)\s+(0\.\d+)\s+(\d+\.\d+)\s*$")
HEAT_SECTIONS = (("H.1 Tabulated 2.4 m PZ Data", "H.2 Tabulated", 0.0, 2.4),
                 ("H.4 Tabulated 7 m MEA + 2 m PZ Data", "H.5 Tabulate", 7.0, 2.0),
                 ("H.5 Tabulate 7 m MEA + 3.5 m PZ Data", "APPENDIX I", 7.0, 3.5))
ROW_SLE = re.compile(r"^\s*\d+\.?\d*[AB]\s+(0\.\d+)\s+\d+/\d+/\d+\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s*$")

# m MEA, m PZ, T / C, loading per N, pCO2, pMEA, pPZ (kPa). Rows 2-1 to 2-6 of Table D.7.
MEA_PZ_7_2_40C = [
    (6.90, 1.97, 40.023, 0.113, 0.00635, 0.00659, 0.00191),
    (6.86, 1.96, 39.997, 0.183, 0.0139, 0.00542, 0.00172),
    (6.99, 2.00, 39.981, 0.235, 0.0281, 0.00414, 0.00157),
    (7.20, 2.06, 40.010, 0.306, 0.0962, 0.00346, 0.00137),
    (7.23, 2.07, 40.007, 0.366, 0.313, 0.00248, 0.00110),
    (6.95, 1.99, 39.968, 0.450, 2.67, 0.00134, 0.000592),
]
MIN_PCO2_LOW_PRECISION = 0.5


def _section(text: str, start: str, end: str) -> list:
    a = text.index(start, text.index("APPENDIX D Tabulated VLE Data"))
    return text[a:text.index(end, a)].splitlines()


def _row(system, m_mea, m_pz, t_c, alpha, pco2, p_mea, p_pz):
    return dict(system=system, m_MEA=m_mea, m_PZ=m_pz, T=t_c + 273.15, loading_per_N=alpha,
                pCO2_kPa=pco2, p_MEA_kPa=p_mea, p_PZ_kPa=p_pz)


def parse_vle(text: str) -> pd.DataFrame:
    rows = []
    for line in _section(text, "D.4 Tabulated H2O-MEA-CO2 Data", "D.5 Tabulated H2O-PZ-CO2 Data"):
        m = ROW_MEA.match(line)
        if m:
            c, t, a, p, pm, _ = map(float, m.groups())
            rows.append(_row("MEA", c, 0.0, t, a, p, pm, None))
    for line in _section(text, "D.5 Tabulated H2O-PZ-CO2 Data", "D.6 Tabulated H2O-K2CO3-PZ-CO2 Data"):
        m = ROW_MEA.match(line)
        if m:
            c, t, a, p, pp, _ = map(float, m.groups())
            rows.append(_row("PZ", 0.0, c, t, a, p, None, pp))
    for line in _section(text, "D.7 Tabulated H2O-MEA-PZ-CO2 Data", "D.8 Tabulated H2O-K2CO3-MEA-CO2 Data"):
        m = ROW_BLEND.match(line)
        if not m:
            continue
        mea, pz, t, a, p, pm, pp, _ = map(float, m.groups())
        if a == 0.0 or (abs(mea - 7.0) < 0.3 and abs(pz - 2.0) < 0.15 and t < 50.0):
            continue                      # unloaded, or the shifted block handled below
        if abs(mea - 3.5) < 0.2 and abs(pz - 3.6) < 0.2 and p < MIN_PCO2_LOW_PRECISION:
            continue
        rows.append(_row("MEA+PZ", mea, pz, t, a, p, pm, pp))
    rows += [_row("MEA+PZ", *r) for r in MEA_PZ_7_2_40C]
    return pd.DataFrame(rows)


def parse_sle(text: str) -> pd.DataFrame:
    a = text.index("I.1 Tabulated H2O-PZ Dissolution Data", text.index("APPENDIX I Tabulated SLE Data"))
    rows = []
    for line in text[a:text.index("I.2 Tabulated", a)].splitlines():
        m = ROW_SLE.match(line)
        if m:
            rows.append(dict(w_PZ=float(m.group(1)), liquidus_C=float(m.group(3))))
    return pd.DataFrame(rows).groupby("w_PZ", as_index=False)["liquidus_C"].mean()


def parse_heats(text: str) -> pd.DataFrame:
    start = text.index("APPENDIX H Tabulated Differential Habs Data", text.index("APPENDIX D Tabulated VLE Data"))
    rows = []
    for head, end, m_mea, m_pz in HEAT_SECTIONS:
        a = text.index(head, start)
        for line in text[a:text.index(end, a + 5)].splitlines():
            m = ROW_HEAT.match(line)
            if m:
                rows.append(dict(m_MEA=m_mea, m_PZ=m_pz, T=float(m.group(1)) + 273.15,
                                 loading_per_N=float(m.group(2)), dH_kj_per_mol=float(m.group(3))))
    return pd.DataFrame(rows)


def main():
    exe = _pdftotext()
    if exe is None or not PDF.exists():
        print("skipped: needs the Hilliard PDF and pdftotext; keeping the stored tables")
        return
    text = subprocess.run([exe, "-layout", str(PDF), "-"], capture_output=True).stdout.decode("utf-8", "ignore")
    vle, sle, heats = parse_vle(text), parse_sle(text), parse_heats(text)
    OUT_VLE.parent.mkdir(parents=True, exist_ok=True)
    vle.to_csv(OUT_VLE, index=False)
    sle.to_csv(OUT_SLE, index=False)
    heats.to_csv(OUT_HEAT, index=False)
    for s, g in vle.groupby("system"):
        print(f"{s:7s} n={len(g):3d}  T {g['T'].min() - 273.15:.0f}-{g['T'].max() - 273.15:.0f} C  "
              f"pCO2 {g.pCO2_kPa.min():.3g}-{g.pCO2_kPa.max():.3g} kPa  "
              f"loading/N {g.loading_per_N.min():.2f}-{g.loading_per_N.max():.2f}")
    print(f"PZ liquidus: n={len(sle)}, 30 wt% = {sle.iloc[(sle.w_PZ - 0.30).abs().argmin()].liquidus_C:.1f} C")
    print(f"heats: n={len(heats)}")
    print("->", OUT_VLE.relative_to(ROOT), "|", OUT_SLE.relative_to(ROOT), "|", OUT_HEAT.relative_to(ROOT))


if __name__ == "__main__":
    main()
