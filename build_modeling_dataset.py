import pandas as pd
from pathlib import Path

ROOT = Path("data")

PROCESSED = ROOT / "processed"
STRUCTURED = PROCESSED / "structured"

OUTPUT = STRUCTURED / "modeling_dataset_with_hartono_dash.csv"

print("=" * 80)
print("BUILDING MODELING DATASET")
print("=" * 80)

# ---------------------------------------------------------------------------
# 1. Load existing structured datasets
# ---------------------------------------------------------------------------

structured_files = [
    STRUCTURED / "table_6_MEA_CO2_H2O.csv",
    STRUCTURED / "table_7_AMP_PZ_CO2_H2O.csv",
    STRUCTURED / "table_8_PZ_CO2_H2O.csv",
    STRUCTURED / "table_9_AMP_CO2_H2O.csv",
]

frames = []

print("\nLoading existing structured datasets:")

for path in structured_files:
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")

    df = pd.read_csv(path)

    print(f"  {path.name}: {df.shape}")

    frames.append(df)


# ---------------------------------------------------------------------------
# 2. Load Dash normalized dataset
# ---------------------------------------------------------------------------

dash_path = PROCESSED / "dash_2011_amp_pz_co2_h2o_table7_normalized.csv"

if not dash_path.exists():
    raise FileNotFoundError(f"Missing Dash file: {dash_path}")

dash = pd.read_csv(dash_path)

print(f"\nDash dataset: {dash.shape}")


# ---------------------------------------------------------------------------
# 3. Load Hartono normalized dataset
# ---------------------------------------------------------------------------

hartono_path = PROCESSED / "hartono_2020_amp_co2_h2o_normalized.csv"

if not hartono_path.exists():
    raise FileNotFoundError(f"Missing Hartono file: {hartono_path}")

hartono = pd.read_csv(hartono_path)

print(f"Hartono dataset: {hartono.shape}")


# ---------------------------------------------------------------------------
# 4. Ensure pressure metadata exists
#
# Hartono:
#   Tables 4-6 -> pCO2
#   Tables 7-9 -> P_total
#
# Dash:
#   pCO2
# ---------------------------------------------------------------------------

def add_pressure_metadata(df):
    df = df.copy()

    # If pressure metadata already exists, preserve it.
    if "pressure_type" not in df.columns:
        df["pressure_type"] = pd.NA

    if "pressure_source" not in df.columns:
        df["pressure_source"] = pd.NA

    # Fill pressure metadata from source table when possible.
    for idx in df.index:

        source = str(df.at[idx, "source_table"]) if "source_table" in df.columns else ""

        if source.startswith("Hartono_2020_Table4") or \
           source.startswith("Hartono_2020_Table5") or \
           source.startswith("Hartono_2020_Table6"):

            df.at[idx, "pressure_type"] = "pCO2"
            df.at[idx, "pressure_source"] = "pCO2_kPa"

        elif source.startswith("Hartono_2020_Table7") or \
             source.startswith("Hartono_2020_Table8") or \
             source.startswith("Hartono_2020_Table9"):

            df.at[idx, "pressure_type"] = "P_total"
            df.at[idx, "pressure_source"] = "p_total_kPa"

        elif source.startswith("Dash_2011"):

            df.at[idx, "pressure_type"] = "pCO2"
            df.at[idx, "pressure_source"] = "pCO2_kPa"

    return df


dash = add_pressure_metadata(dash)
hartono = add_pressure_metadata(hartono)


# ---------------------------------------------------------------------------
# 5. Validate Hartono pressure values
# ---------------------------------------------------------------------------

print("\nValidating Hartono pressure metadata...")

expected_pco2_tables = {
    "Hartono_2020_Table4",
    "Hartono_2020_Table5",
    "Hartono_2020_Table6",
}

expected_ptotal_tables = {
    "Hartono_2020_Table7",
    "Hartono_2020_Table8",
    "Hartono_2020_Table9",
}

for table in expected_pco2_tables:
    subset = hartono[hartono["source_table"] == table]

    if len(subset) == 0:
        raise ValueError(f"No rows found for {table}")

    if not (subset["pressure_type"] == "pCO2").all():
        raise ValueError(f"{table} has incorrect pressure_type")

    if not (subset["pressure_source"] == "pCO2_kPa").all():
        raise ValueError(f"{table} has incorrect pressure_source")


for table in expected_ptotal_tables:
    subset = hartono[hartono["source_table"] == table]

    if len(subset) == 0:
        raise ValueError(f"No rows found for {table}")

    if not (subset["pressure_type"] == "P_total").all():
        raise ValueError(f"{table} has incorrect pressure_type")

    if not (subset["pressure_source"] == "p_total_kPa").all():
        raise ValueError(f"{table} has incorrect pressure_source")


# ---------------------------------------------------------------------------
# 6. Validate pressure conversion
# ---------------------------------------------------------------------------

for name, df in [
    ("Dash", dash),
    ("Hartono", hartono),
]:

    if "P_kPa" not in df.columns:
        raise ValueError(f"{name} dataset has no P_kPa column")

    if "P_MPa" not in df.columns:
        df["P_MPa"] = df["P_kPa"] / 1000.0

    else:
        expected = df["P_kPa"] / 1000.0

        mismatch = (
            (df["P_MPa"] - expected).abs() > 1e-9
        ).sum()

        if mismatch > 0:
            print(
                f"WARNING: {name} has {mismatch} P_MPa values "
                "that do not match P_kPa / 1000. Recalculating."
            )

            df["P_MPa"] = expected


# ---------------------------------------------------------------------------
# 7. Combine datasets
# ---------------------------------------------------------------------------

print("\nCombining datasets...")

all_frames = frames + [dash, hartono]

combined = pd.concat(
    all_frames,
    ignore_index=True,
    sort=False
)


# ---------------------------------------------------------------------------
# 8. Ensure derived pressure columns exist
# ---------------------------------------------------------------------------

if "P_kPa" not in combined.columns:
    raise ValueError("Final dataset is missing P_kPa")

combined["P_MPa"] = combined["P_kPa"] / 1000.0


# ---------------------------------------------------------------------------
# 9. Ensure Hartono/Dash metadata is preserved
# ---------------------------------------------------------------------------

combined = add_pressure_metadata(combined)


# ---------------------------------------------------------------------------
# 10. Remove exact duplicate rows
#
# Do NOT perform aggressive deduplication based only on pressure/loading.
# Different experimental sources can legitimately have similar values.
# ---------------------------------------------------------------------------

before = len(combined)

combined = combined.drop_duplicates().reset_index(drop=True)

after = len(combined)

print(f"\nExact duplicate rows removed: {before - after}")


# ---------------------------------------------------------------------------
# 11. Save
# ---------------------------------------------------------------------------

STRUCTURED.mkdir(parents=True, exist_ok=True)

combined.to_csv(
    OUTPUT,
    index=False
)

print("\n" + "=" * 80)
print("BUILD COMPLETE")
print("=" * 80)

print(f"\nOutput:")
print(f"  {OUTPUT}")

print(f"\nShape:")
print(f"  {combined.shape}")

print("\nRows by source:")
print(
    combined.groupby("source_table")
    .size()
    .to_string()
)

print("\nPressure metadata:")
print(
    combined.groupby(
        ["source_table", "pressure_type", "pressure_source"]
    )["P_kPa"]
    .agg(["count", "min", "max"])
    .to_string()
)


# ---------------------------------------------------------------------------
# 12. Final Hartono sanity checks
# ---------------------------------------------------------------------------

hartono_final = combined[
    combined["source_table"].astype(str).str.startswith("Hartono_2020")
]

print("\nHartono validation:")
print(
    hartono_final[
        [
            "source_table",
            "pressure_type",
            "pressure_source",
            "P_kPa",
            "P_MPa",
            "co2_to_amine_ratio",
        ]
    ].head(10).to_string(index=False)
)

missing_metadata = hartono_final[
    ["pressure_type", "pressure_source"]
].isna().sum()

missing_pressure = hartono_final["P_kPa"].isna().sum()

print("\nMissing Hartono pressure metadata:")
print(missing_metadata.to_string())

print(f"\nMissing Hartono P_kPa: {missing_pressure}")

if missing_pressure != 0:
    raise ValueError("Hartono contains missing P_kPa values")

if missing_metadata.sum() != 0:
    raise ValueError("Hartono contains missing pressure metadata")

print("\nSUCCESS: dataset passed validation.")
