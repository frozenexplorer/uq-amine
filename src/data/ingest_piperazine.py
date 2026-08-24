"""
Ingest Ermatchkov et al. (2006) Piperazine CO2 solubility data
from the NIST ThermoML JSON representation.

Source:
Ermatchkov, V.; Kamps, A. P.-S.; Speyer, D.; Maurer, G.
"Solubility of Carbon Dioxide in Aqueous Solutions of Piperazine
in the Low Gas Loading Region"
J. Chem. Eng. Data, 2006
DOI: 10.1021/je0601917

ThermoML mapping:
    Variable 1 -> Temperature [K]
    Variable 2 -> PZ molality [mol/kg water]
    Variable 3 -> CO2 partial pressure [kPa]
    Property 1 -> CO2 molality [mol/kg water]

Loading is calculated as:

    alpha = CO2 molality / PZ molality

Canonical output:
    amine
    SMILES
    T
    P_CO2
    conc
    loading_alpha
    source
    license
"""

import json
from pathlib import Path

import pandas as pd


INPUT_PATH = Path("data/raw/piperazine_ermatchkov_2006.json")
OUTPUT_PATH = Path("data/interim/piperazine_ermatchkov_2006.csv")

PZ_SMILES = "C1CNCCN1"


def ingest_piperazine(path: Path) -> pd.DataFrame:
    """Parse the ThermoML JSON and return the canonical PZ dataset."""

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    rows = []

    for block in data["PureOrMixtureData"]:
        for measurement in block["NumValues"]:
            variables = {
                item["nVarNumber"]: item["nVarValue"]
                for item in measurement["VariableValue"]
            }

            properties = {
                item["nPropNumber"]: item["nPropValue"]
                for item in measurement["PropertyValue"]
            }

            temperature = variables[1]
            pz_molality = variables[2]
            co2_pressure = variables[3]
            co2_molality = properties[1]

            if pz_molality <= 0:
                raise ValueError(
                    f"Invalid PZ molality: {pz_molality}"
                )

            loading_alpha = co2_molality / pz_molality

            rows.append(
                {
                    "amine": "PZ",
                    "SMILES": PZ_SMILES,
                    "T": temperature,
                    "P_CO2": co2_pressure,
                    "conc": pz_molality,
                    "loading_alpha": loading_alpha,
                    "source": (
                        "Ermatchkov et al. 2006; "
                        "DOI:10.1021/je0601917; "
                        "NIST ThermoML"
                    ),
                    "license": "not specified",
                }
            )

    return pd.DataFrame(rows)


def validate(df: pd.DataFrame) -> None:
    """Basic validation of the canonical dataset."""

    expected_columns = [
        "amine",
        "SMILES",
        "T",
        "P_CO2",
        "conc",
        "loading_alpha",
        "source",
        "license",
    ]

    assert list(df.columns) == expected_columns

    assert len(df) > 0
    assert df["amine"].eq("PZ").all()
    assert df["SMILES"].eq(PZ_SMILES).all()

    assert df["T"].notna().all()
    assert df["P_CO2"].notna().all()
    assert df["conc"].notna().all()
    assert df["loading_alpha"].notna().all()

    assert (df["T"] > 0).all()
    assert (df["P_CO2"] >= 0).all()
    assert (df["conc"] > 0).all()
    assert (df["loading_alpha"] >= 0).all()


def main():
    print(f"Reading: {INPUT_PATH}")

    df = ingest_piperazine(INPUT_PATH)

    validate(df)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)

    print(f"\nRows extracted: {len(df)}")
    print(f"Output: {OUTPUT_PATH}")

    print("\nRanges:")
    print(f"  T:             {df['T'].min():.2f} – {df['T'].max():.2f} K")
    print(
        f"  P_CO2:         "
        f"{df['P_CO2'].min():.4f} – {df['P_CO2'].max():.4f} kPa"
    )
    print(
        f"  PZ conc:       "
        f"{df['conc'].min():.4f} – {df['conc'].max():.4f} mol/kg"
    )
    print(
        f"  loading alpha: "
        f"{df['loading_alpha'].min():.4f} – "
        f"{df['loading_alpha'].max():.4f}"
    )

    print("\nFirst 5 rows:")
    print(df.head().to_string(index=False))


if __name__ == "__main__":
    main()