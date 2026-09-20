"""
Ingest the in-house "BlendCO2" equilibrium-solver scan results
(`our data/Amine_Earlier work/BlendCO2 3/BlendCO2/all_blends_ranked.csv`).

IMPORTANT -- this is SIMULATED data, not experimental data. It comes from
an in-house equilibrium solver (single.py / binary.py / pz.py / ternary.py)
that ranks MEA/MDEA/AMP/PZ blend compositions by cyclic_capacity and cost.
The solver's core physics module (`equilibrium_solver.py`) is missing from
both local copies of the project -- only its compiled `.pyc` remains -- so
its assumptions cannot currently be audited. Do not mix this data into the
same UQ-calibration pool as real experimental measurements
(data/processed/structured/unified_vle_dataset_with_hartono_dash.csv,
piperazine_ermatchkov_2006.csv) without keeping the `data_type` column
intact to separate them.

Output:
    data/processed/structured/blendco2_simulated_blends.csv  (177 rows)
"""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

SOURCE_CSV = (
    ROOT
    / "our data"
    / "Amine_Earlier work"
    / "BlendCO2 3"
    / "BlendCO2"
    / "all_blends_ranked.csv"
)

OUTPUT = ROOT / "data/processed/structured/blendco2_simulated_blends.csv"


def main():
    df = pd.read_csv(SOURCE_CSV)

    df = df.rename(columns={"source": "generator_script"})
    df.insert(0, "data_type", "simulated")
    df.insert(
        1,
        "provenance",
        "in-house equilibrium solver (BlendCO2); solver source (equilibrium_solver.py) "
        "unavailable, only compiled .pyc found -- physics unverified",
    )

    expected_amines = {"comp_MEA", "comp_MDEA", "comp_AMP", "comp_PZ"}
    if not expected_amines.issubset(df.columns):
        raise ValueError(f"Missing expected composition columns: {expected_amines - set(df.columns)}")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT, index=False)

    print(f"Rows: {len(df)} -> {OUTPUT}")
    print("\nBlend type counts:")
    print(df["blend_type"].value_counts().to_string())
    print("\ncyclic_capacity range:", df["cyclic_capacity"].min(), "-", df["cyclic_capacity"].max())


if __name__ == "__main__":
    main()
