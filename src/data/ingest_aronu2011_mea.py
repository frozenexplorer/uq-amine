"""
MEA CO2 solubility at absorber temperatures (40-80 C, 15-60 mass%), transcribed from

    Aronu, U. E.; Gondal, S.; Hessen, E. T.; Haug-Warberg, T.; Hartono, A.; Hoff, K. A.;
    Svendsen, H. F. "Solubility of CO2 in 15, 30, 45 and 60 mass% MEA from 40 to 120 C and
    model representation using the extended UNIQUAC framework."
    Chem. Eng. Sci. 66 (2011) 6393-6406. DOI 10.1016/j.ces.2011.08.042
    Local copy: data/raw/aronu2011.pdf (gitignored)

Tables 3-6 (15 / 30 / 45 / 60 mass% MEA) each hold two kinds of data:
  * 40, 60, 80 C -- low-temperature apparatus: MEASURED CO2 partial pressure (IR analyser)
    vs loading. These are transcribed here (138 points, pCO2 0.0007-16 kPa).
  * 60-120 C -- high-temperature apparatus: measured TOTAL pressure; the printed pCO2 is
    the authors' e-UNIQUAC "pCO2 model" value. NOT used: fitting to another model's pCO2
    would be circular, and Ptot -> pCO2 at 45-60 mass% MEA needs water/MEA activities.
    (Wagner 2013 already covers MEA at 313-393 K for the stripper side.)

In Tables 3 and 5 (15 and 45 mass%) the 60 / 80 C loading column lists the low-T points
first, then the high-T points, so the measured loadings are the first n values of that
printed column. Loadings are mol CO2 / mol MEA; "mass% MEA" is of the unloaded solvent.
A few printed loadings are non-monotonic in pCO2 (e.g. 15 % / 60 C 0.0078 kPa -> 0.069;
45 % / 80 C 0.0060 kPa -> 0.025); they are kept verbatim.

Every column is checked against the PDF text (`verify()`, needs pdftotext; runs whenever
the PDF and pdftotext are available): each transcribed pCO2 column and loading column
must appear as one contiguous run of numbers in the pdftotext output.

Output: data/interim/mea_aronu2011.csv
Run:    python -m src.data.ingest_aronu2011_mea
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PDF = ROOT / "data" / "raw" / "aronu2011.pdf"
OUT = ROOT / "data" / "interim" / "mea_aronu2011.csv"
MW_MEA = 61.08

# (mass% MEA, T C): (pCO2 kPa column, loading column), transcribed verbatim, in table order.
TABLES = {
    # Table 3, 15 mass% MEA
    (15, 40): ("0.0017 0.0035 0.0068 0.0170 0.0215 0.0427 0.0450 0.0845 0.2220 0.6634 0.7013 "
               "4.8405 7.8861 16.0024",
               "0.111 0.148 0.186 0.220 0.236 0.295 0.298 0.342 0.398 0.442 0.450 0.516 0.529 "
               "0.565"),
    (15, 60): ("0.0042 0.0056 0.0068 0.0078 0.0094 0.0151 0.0234 0.0417 0.0965 0.1462 1.7998 "
               "5.4090 8.2297",
               "0.048 0.060 0.075 0.069 0.098 0.135 0.144 0.175 0.230 0.253 0.415 0.480 0.492"),
    (15, 80): ("0.0603 0.1315 0.3544 0.5250 3.6374 6.3092",
               "0.103 0.147 0.211 0.242 0.373 0.409"),
    # Table 4, 30 mass% MEA
    (30, 40): ("0.0016 0.0123 0.0246 0.0603 0.0851 0.1835 0.2928 0.3188 0.3809 0.5702 1.0662 "
               "1.8326 1.8278 2.3193 2.8577 8.5583 11.812",
               "0.102 0.206 0.250 0.337 0.353 0.401 0.417 0.421 0.433 0.447 0.464 0.476 0.477 "
               "0.485 0.489 0.516 0.524"),
    (30, 60): ("0.0045 0.0154 0.0427 0.1348 0.3015 0.6436 1.0970 2.5014 13.558",
               "0.053 0.105 0.162 0.244 0.303 0.360 0.393 0.428 0.491"),
    (30, 80): ("0.0056 0.0219 0.0557 0.1406 0.2485 0.6137 1.2538 3.7522 7.9387 8.3031",
               "0.017 0.040 0.075 0.122 0.155 0.216 0.271 0.347 0.400 0.398"),
    # Table 5, 45 mass% MEA
    (45, 40): ("0.0035 0.0035 0.0077 0.0099 0.0123 0.0164 0.0178 0.0364 0.0598 0.1087 0.1781 "
               "0.2787 0.9173 2.1609 5.4871",
               "0.141 0.148 0.195 0.217 0.234 0.276 0.271 0.300 0.354 0.390 0.404 0.428 0.464 "
               "0.475 0.497"),
    (45, 60): ("0.0019 0.0059 0.0099 0.0205 0.0787 0.1284 0.4279 1.4259 4.6349 6.2928 8.2900",
               "0.045 0.087 0.120 0.169 0.232 0.269 0.352 0.392 0.454 0.460 0.471"),
    (45, 80): ("0.0008 0.0023 0.0056 0.0060 0.0099 0.0288 0.0529 0.1236 0.3981 4.5002 11.249",
               "0.017 0.027 0.038 0.025 0.061 0.086 0.109 0.135 0.236 0.389 0.435"),
    # Table 6, 60 mass% MEA
    (60, 40): ("0.0060 0.0127 0.0281 0.0526 0.1508 0.3824 0.9062 1.5153 3.7472 12.472",
               "0.173 0.242 0.306 0.344 0.394 0.427 0.449 0.468 0.481 0.500"),
    (60, 60): ("0.0007 0.0110 0.0341 0.1097 0.2933 0.8475 3.0267 8.2258 18.967",
               "0.046 0.126 0.172 0.248 0.316 0.382 0.424 0.457 0.480"),
    (60, 80): ("0.0020 0.0170 0.0325 0.0777 0.1610 0.2513 0.5431 0.8699 1.6522 3.4300 6.0947 "
               "9.0463 11.271",
               "0.018 0.056 0.073 0.124 0.162 0.191 0.238 0.264 0.308 0.352 0.387 0.404 0.416"),
}
TABLE_NO = {15: "Table 3", 30: "Table 4", 45: "Table 5", 60: "Table 6"}


def build() -> pd.DataFrame:
    rows = []
    for (w, t_c), (p_txt, a_txt) in TABLES.items():
        p, a = p_txt.split(), a_txt.split()
        assert len(p) == len(a), (w, t_c, len(p), len(a))
        for pi, ai in zip(p, a):
            rows.append(dict(amine="MEA", T=t_c + 273.15, pCO2_kPa=float(pi),
                             m_amine=w / MW_MEA * 1000.0 / (100.0 - w), w_amine_pct=w,
                             loading=float(ai), method="low-T apparatus, measured pCO2 (IR)",
                             table=TABLE_NO[w], source="Aronu et al. (2011)",
                             doi="10.1016/j.ces.2011.08.042"))
    return pd.DataFrame(rows)


def _pdftotext() -> str | None:
    exe = shutil.which("pdftotext")
    for cand in (r"C:\Program Files\Git\mingw64\bin\pdftotext.exe",):
        if exe is None and Path(cand).exists():
            exe = cand
    return exe


def verify() -> bool:
    """Every transcribed column must occur as a contiguous run of numbers in the PDF text."""
    exe = _pdftotext()
    if exe is None or not PDF.exists():
        print("verify: skipped (needs data/raw/aronu2011.pdf and pdftotext)")
        return False
    txt = subprocess.run([exe, str(PDF), "-"], capture_output=True, check=True).stdout
    txt = " " + " ".join(txt.decode("utf-8", "replace").split()) + " "
    assert "10.1016/j.ces.2011.08.042" in txt, "PDF is not Aronu et al. (2011)"
    n = 0
    for key, cols in TABLES.items():
        for col in cols:
            run = " " + " ".join(col.split()) + " "
            assert run in txt, f"column {key} not found verbatim in the PDF text: {col[:40]}..."
            n += len(col.split())
    # the 30 and 60 mass% tables are clean column blocks: pCO2 column directly followed by
    # its loading column (tables 3/5 interleave other columns, so only checked per column)
    for key in [(w, t) for w in (30, 60) for t in (40, 60)]:
        p, a = (" ".join(c.split()) for c in TABLES[key])
        assert re.search(re.escape(p) + r" (?:aCO2 \(mol/mol\) )?" + re.escape(a), txt), key
    print(f"verify: all {len(TABLES)} x 2 columns ({n} numbers) found verbatim in the PDF text")
    return True


def main():
    verify()
    df = build()
    assert len(df) == 138, len(df)
    assert df.pCO2_kPa.between(0.0005, 20).all() and df.loading.between(0, 0.6).all()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    for (w, t), g in df.groupby(["w_amine_pct", "T"]):
        print(f"{w:2d} mass% MEA ({g.m_amine.iloc[0]:.2f} m), {t - 273.15:.0f} C: n={len(g):2d}  "
              f"pCO2 {g.pCO2_kPa.min():.4f}-{g.pCO2_kPa.max():.2f} kPa  "
              f"loading {g.loading.min():.3f}-{g.loading.max():.3f}")
    print("->", OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
