"""
Ingest hand-curated literature performance tables for amine blends from
`our data/Amine_Earlier work/Amine Blends_Computations_NotebookLM/`.

These tables were extracted from source PDFs with NotebookLM (an AI
summarization tool) rather than transcribed directly from the papers by a
human. TREAT AS UNVERIFIED until spot-checked against the underlying PDFs
(2026_Wang, 2025_Gupta, 2025_Liang, the AEP/DMEA paper, and the untitled
"Source_1" behind the MEA/MDEA/AMP/PZ table -- all in
`References_Amine/` next to this script's inputs).

Reported units are heterogeneous across sources (mol/mol, mol/kg, mol/L,
GJ/t CO2, kJ/mol CO2 all appear for related-but-different quantities) and
this script does NOT attempt to force them into one unit -- that would
require density/molar-mass assumptions not given in the sources. Instead
it produces a tidy long-format table: one row per (blend, metric), with
an explicit `unit` column and the original cell text preserved in
`raw_text` for auditing.

Two outputs, kept separate because kinetics is out of this project's
scope per docs/BACKLOG.md:
    data/processed/structured/literature_blend_performance.csv
        (thermodynamic/stability metrics: loading, cyclic capacity, heat
        of absorption, regeneration efficiency/duty, corrosion, stability)
    data/processed/structured/literature_blend_kinetics.csv
        (absorption rate -- kinetics; not currently a modeling target)
"""

import re
from pathlib import Path

import docx
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

NOTEBOOKLM_DIR = ROOT / "our data" / "Amine_Earlier work" / "Amine Blends_Computations_NotebookLM"

XLSX_A = NOTEBOOKLM_DIR / "Comparison of Amine Blends for Carbon Dioxide Capture Performance.xlsx"
XLSX_B = NOTEBOOKLM_DIR / "Performance Metrics of Amine Blends for CO2 Capture.xlsx"
XLSX_C = NOTEBOOKLM_DIR / "Performance of MEA_MDEA Blends with AMP and Piperazine.xlsx"
DOCX_A = NOTEBOOKLM_DIR / "Amine blends data.docx"

OUT_DIR = ROOT / "data/processed/structured"
PERFORMANCE_OUT = OUT_DIR / "literature_blend_performance.csv"
KINETICS_OUT = OUT_DIR / "literature_blend_kinetics.csv"


def clean_text(x) -> str:
    if pd.isna(x):
        return ""
    s = str(x)
    s = re.sub(r"\$([^$]*)\$", lambda m: m.group(1), s)  # strip $...$ math
    s = s.replace("_{2}", "2").replace("_2", "2")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def parse_numeric(raw: str):
    """Best-effort number extraction; returns (value, value_min, value_max) or (None, None, None).

    A range is recognized either as "NUM - NUM" / "NUM – NUM" (hyphen or
    en/em-dash between two numbers, not a leading minus sign) or "NUM to NUM".
    """
    if not raw or raw.lower().startswith("not in source"):
        return None, None, None

    range_match = re.search(
        r"(-?\d+\.?\d*)\s*[-–—]\s*(\d+\.?\d*)", raw.replace(",", "")
    )
    if range_match:
        a, b = float(range_match.group(1)), float(range_match.group(2))
        return None, min(a, b), max(a, b)

    nums = re.findall(r"-?\d+\.?\d*", raw.replace(",", ""))
    if not nums:
        return None, None, None
    nums = [float(n) for n in nums]

    if "to" in raw.lower() and len(nums) >= 2:
        return None, min(nums[:2]), max(nums[:2])

    return nums[0], None, None


def melt_table(df: pd.DataFrame, id_col: str, metric_cols: list, source_document: str, source_map: dict = None):
    rows = []

    for _, r in df.iterrows():
        blend_label = clean_text(r[id_col])
        source_idx = clean_text(r.get("Source", ""))
        source_reference = source_map.get(source_idx, source_idx) if source_map else source_idx

        for col in metric_cols:
            if col not in df.columns:
                continue
            raw = clean_text(r[col])
            if not raw:
                continue

            value, vmin, vmax = parse_numeric(raw)

            rows.append(
                {
                    "source_document": source_document,
                    "blend_label": blend_label,
                    "metric": col,
                    "value": value,
                    "value_min": vmin,
                    "value_max": vmax,
                    "raw_text": raw,
                    "source_reference": source_reference,
                }
            )

    return rows


def load_source_map(xlsx_path: Path) -> dict:
    refs = pd.read_excel(xlsx_path, sheet_name="Source References")
    return {str(int(i)): clean_text(ref) for i, ref in zip(refs["Index"], refs["Reference"])}


def build_performance_rows():
    rows = []

    df_a = pd.read_excel(XLSX_A, sheet_name="Table 1")
    map_a = load_source_map(XLSX_A)
    metric_cols_a = [
        "Max Equilibrium CO2 Loading (mol/mol)",
        "Cyclic Capacity (mol/L or mol/kg)",
        "Heat of Absorption (kJ/mol)",
        "Regeneration Efficiency (%)",
    ]
    rows += melt_table(df_a, "Amine Blend Components", metric_cols_a, XLSX_A.name, map_a)

    df_b = pd.read_excel(XLSX_B, sheet_name="Table 1")
    map_b = load_source_map(XLSX_B)
    metric_cols_b = [
        "Absorption Capacity (mol CO2/L or mol/kg)",
        "Cyclic Capacity (mol CO2/L or mol/kg)",
        "Heat of Absorption (kJ/mol)",
        "Regeneration Efficiency (%)",
        "Regeneration Heat Duty (GJ/t CO2 or kJ/mol)",
        "Corrosion Rate (mmpy)",
        "Oxidative Stability (%)",
    ]
    rows += melt_table(df_b, "Amine Blend Formulation", metric_cols_b, XLSX_B.name, map_b)

    d = docx.Document(DOCX_A)
    table2 = d.tables[2]
    header = [c.text.strip() for c in table2.rows[0].cells]
    data = [[c.text.strip() for c in row.cells] for row in table2.rows[1:]]
    df_c = pd.DataFrame(data, columns=header)
    metric_cols_c = [
        "Abs. Capacity (mol/mol)",
        "Cyclic Capacity",
        "Regen. Energy (GJ/t CO$_2$)",
        "Stability / Retention",
    ]
    rows += melt_table(df_c, "Combination", metric_cols_c, DOCX_A.name)

    return rows


def build_kinetics_rows():
    df = pd.read_excel(XLSX_C, sheet_name="Table 1")

    rows = []
    for _, r in df.iterrows():
        blend_label = clean_text(r["Amine Blend"])
        concentration = clean_text(r["Concentration (wt%)"])
        temperature = clean_text(r["Temperature (K)"])
        pco2 = clean_text(r["CO $_2$  Partial Pressure (kPa)"])
        abs_capacity_raw = clean_text(r["Absorption Capacity (molCO $_2$ /molamine)"])
        rate_raw = clean_text(r["Absorption Rate (mmol/mol·s)"])
        cyclic_raw = clean_text(r["Cyclic Loading (molCO $_2$ /molamine)"])
        notes = clean_text(r["Degradation/Stability Observations"])
        source = clean_text(r["Source"])

        abs_value, _, _ = parse_numeric(abs_capacity_raw)
        rate_value, _, _ = parse_numeric(rate_raw)
        cyclic_value, _, _ = parse_numeric(cyclic_raw)

        rows.append(
            {
                "source_document": XLSX_C.name,
                "blend_label": blend_label,
                "concentration_wt_pct_raw": concentration,
                "temperature_K": float(temperature) if temperature else None,
                "co2_partial_pressure_kPa": float(pco2) if pco2 else None,
                "absorption_capacity_mol_co2_per_mol_amine": abs_value,
                "absorption_rate_mmol_per_mol_s": rate_value,
                "cyclic_loading_mol_co2_per_mol_amine": cyclic_value,
                "notes": notes,
                "source_reference": source,
            }
        )

    return pd.DataFrame(rows)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    perf_rows = build_performance_rows()
    perf_df = pd.DataFrame(perf_rows)
    perf_df.to_csv(PERFORMANCE_OUT, index=False)
    print(f"Performance (long format): {perf_df.shape} -> {PERFORMANCE_OUT}")
    print("\nMetrics present:")
    print(perf_df["metric"].value_counts().to_string())

    kin_df = build_kinetics_rows()
    kin_df.to_csv(KINETICS_OUT, index=False)
    print(f"\nKinetics: {kin_df.shape} -> {KINETICS_OUT}")


if __name__ == "__main__":
    main()
