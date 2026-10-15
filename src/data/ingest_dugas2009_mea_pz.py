"""
MEA, PZ and MEA/PZ equilibrium CO2 partial pressure at 40-100 C, transcribed from

    Dugas, R. E. "Carbon Dioxide Absorption, Desorption, and Diffusion in Aqueous Piperazine
    and Monoethanolamine." PhD Dissertation, The University of Texas at Austin, 2009
    (supervisor G. T. Rochelle). Open copy hosted by the Rochelle group:
    https://sites.utexas.edu/rochelle/wp-content/uploads/sites/3310/2015/02/
        Dugas-2009-Carbon-Dioxide-Absorption-Desorption-and-Diffusion-in-Aqueous-Piperazine-and-Monoethanolamine.pdf
    Local copy: data/raw/dugas_2009_thesis/ (gitignored)

    Table 4.4: 7, 9, 11, 13 m MEA        (50 points)
    Table 4.5: 2, 5, 8, 12 m PZ          (43 points)
    Table 4.6: 7 m MEA / 2 m PZ          (12 points)

P*CO2 comes from a wetted-wall column: each row brackets equilibrium with six inlet CO2
pressures (absorption and desorption) and interpolates to zero flux -- a different method
from the equilibrium cells of Wagner (2013) and Aronu (2011), which makes it a useful
independent check. Loading is mol CO2 / mol ALKALINITY (MEA: 1 N, PZ: 2 N), converted here to
mol CO2 per mol amine molecules for the model. "m" = mol / kg water.

Why it matters: MEA and PZ were measured in the SAME apparatus, so their capacity ratio at
the absorber (40 C, P*CO2 0.5 -> 5 kPa) is a like-for-like benchmark of how the model values
PZ relative to MEA -- the ranking-relevant question. Table 4.6 is a held-out MEA+PZ blend
(the chemistry of the best yellow mixtures).

Every value is checked against the PDF text (`verify()`, needs pdftotext): MEA and MEA/PZ
columns must occur as contiguous runs of numbers in the pdftotext output; PZ rows (the table
is printed row-wise) must have loading and P* on the same line of `pdftotext -layout`.

Output: data/interim/dugas2009_wwc.csv
Run:    python -m src.data.ingest_dugas2009_mea_pz
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pandas as pd

from src.data.ingest_aronu2011_mea import _pdftotext

ROOT = Path(__file__).resolve().parents[2]
PDF = (ROOT / "data" / "raw" / "dugas_2009_thesis" /
       "dugas_2009_co2_absorption_desorption_diffusion_pz_mea.pdf")
OUT = ROOT / "data" / "interim" / "dugas2009_wwc.csv"

# Table 4.4 / 4.6: (m_MEA, m_PZ) -> (temperatures per point, loading column, P* column [Pa]),
# columns verbatim in table order. Temperature runs: 40 C x4, 60 C x4, 80 C x2, 100 C x2
# (9 and 13 m: x5 / x4 at 40 and 60 C), read from the table's row labels.
T_4422 = [40] * 4 + [60] * 4 + [80] * 2 + [100] * 2
T_5522 = [40] * 5 + [60] * 5 + [80] * 2 + [100] * 2
COLUMNS = {
    (7, 0): (T_4422, "0.252 0.351 0.432 0.496 0.252 0.351 0.432 0.496 0.271 0.366 0.271 0.366",
             "15.7 77 465 4216 109 660 3434 16157 1053 4443 5297 19008"),
    (9, 0): (T_5522, "0.231 0.324 0.382 0.441 0.496 0.231 0.324 0.382 0.441 0.496 0.265 0.356 "
                     "0.265 0.356",
             "10.4 34 107 417 5354 61 263 892 2862 21249 979 4797 4940 21534"),
    (11, 0): (T_4422, "0.261 0.353 0.428 0.461 0.261 0.353 0.428 0.461 0.256 0.359 0.256 0.359",
              "14.0 67 434 1509 96 634 3463 8171 860 3923 4274 18657"),
    (13, 0): (T_4422, "0.252 0.372 0.435 0.502 0.252 0.372 0.435 0.502 0.254 0.355 0.254 0.355",
              "12.3 84 491 8792 100 694 3859 29427 873 3964 3876 18406"),
    (7, 2): (T_4422, "0.242 0.333 0.416 0.477 0.242 0.333 0.416 0.477 0.242 0.333 0.242 0.333",
             "27 166 1425 7418 178 1256 7122 33704 1138 6174 4340 26571"),
}
# Table 4.5 (printed row-wise): m_PZ -> rows "T loading P*[Pa]"
PZ_ROWS = {
    2: """40 0.240 96; 40 0.316 499; 40 0.352 1305; 40 0.411 7127;
          60 0.240 559; 60 0.316 2541; 60 0.352 5593; 60 0.411 25378;
          80 0.239 2492; 80 0.324 12260; 100 0.239 9569; 100 0.324 39286""",
    5: """40 0.226 65; 40 0.299 346; 40 0.354 1120; 40 0.402 4563;
          60 0.226 385; 60 0.299 1814; 60 0.354 5021; 60 0.402 17233;
          80 0.238 2192; 80 0.321 9699; 100 0.238 8888; 100 0.321 36960""",
    8: """40 0.231 68; 40 0.305 530; 40 0.360 1409; 40 0.404 8153;
          60 0.231 430; 60 0.305 2407; 60 0.360 7454; 60 0.404 30783;
          80 0.253 3255; 80 0.289 9406; 100 0.253 13605; 100 0.289 32033""",
    12: """60 0.231 331; 60 0.289 1865; 60 0.354 6791;
           80 0.222 2115; 80 0.290 9141; 100 0.222 7871; 100 0.290 33652""",
}
TABLE = {(7, 2): "Table 4.6"}


def _pz_rows():
    for m_pz, txt in PZ_ROWS.items():
        for row in txt.replace("\n", " ").split(";"):
            t_c, ldg, p = row.split()
            yield m_pz, int(t_c), ldg, p


def build() -> pd.DataFrame:
    rows = []

    def add(m_mea, m_pz, t_c, ldg, p_pa, table):
        alk = m_mea + 2 * m_pz
        n_co2 = float(ldg) * alk
        rows.append(dict(system="MEA/PZ" if m_mea and m_pz else ("MEA" if m_mea else "PZ"),
                         T=t_c + 273.15, pCO2_kPa=float(p_pa) / 1000.0, m_MEA=float(m_mea),
                         m_PZ=float(m_pz), alkalinity_m=float(alk),
                         loading_per_alkalinity=float(ldg), n_co2=n_co2,
                         loading=n_co2 / (m_mea + m_pz), table=table,
                         method="wetted-wall column, P* bracketed by absorption/desorption",
                         source="Dugas (2009) PhD thesis, UT Austin"))

    for (m_mea, m_pz), (temps, ldg, p) in COLUMNS.items():
        ldg, p = ldg.split(), p.split()
        assert len(temps) == len(ldg) == len(p), (m_mea, m_pz)
        for t_c, a, pi in zip(temps, ldg, p):
            add(m_mea, m_pz, t_c, a, pi, TABLE.get((m_mea, m_pz), "Table 4.4"))
    for m_pz, t_c, a, pi in _pz_rows():
        add(0, m_pz, t_c, a, pi, "Table 4.5")
    return pd.DataFrame(rows)


def verify() -> bool:
    exe = _pdftotext()
    if exe is None or not PDF.exists():
        print("verify: skipped (needs the Dugas 2009 PDF and pdftotext)")
        return False
    raw = subprocess.run([exe, str(PDF), "-"], capture_output=True, check=True).stdout
    raw = " " + " ".join(raw.decode("utf-8", "replace").split()) + " "
    lay = subprocess.run([exe, "-layout", str(PDF), "-"], capture_output=True, check=True).stdout
    lay = [" " + " ".join(l.split()) + " " for l in lay.decode("utf-8", "replace").splitlines()]
    assert "Dugas" in raw[:3000] and "Rochelle" in raw[:5000], "PDF is not the Dugas (2009) thesis"
    n = 0
    for key, (_, ldg, p) in COLUMNS.items():
        for col in (ldg, p):
            run = " " + " ".join(col.split()) + " "
            assert run in raw, f"{key}: column not found verbatim in the PDF text: {col[:40]}..."
            n += len(col.split())
    for m_pz, t_c, a, p in _pz_rows():
        assert any(f" {a} {p} " in l for l in lay), f"{m_pz} m PZ, {t_c} C: '{a} {p}' not on one line"
        n += 2
    print(f"verify: {n} numbers (MEA + MEA/PZ columns, PZ rows) found verbatim in the PDF text")
    return True


def main():
    verify()
    df = build()
    assert len(df) == 50 + 43 + 12, len(df)
    # P* rises with T at fixed loading, and with loading at fixed T (within each solvent)
    for (_, _, t), g in df.groupby(["m_MEA", "m_PZ", "T"]):
        g = g.sort_values("loading_per_alkalinity")
        assert g.pCO2_kPa.is_monotonic_increasing, (g.iloc[0].to_dict(), t)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    for (s, a, z), g in df.groupby(["system", "m_MEA", "m_PZ"]):
        print(f"{s:6s} {a:4.0f} m MEA {z:4.0f} m PZ: n={len(g):2d}  T {g['T'].min() - 273.15:.0f}-"
              f"{g['T'].max() - 273.15:.0f} C  P* {g.pCO2_kPa.min():.4f}-{g.pCO2_kPa.max():.1f} kPa")
    print("->", OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
