"""
Ingest the "CO2_chemical_solvents" Zenodo dataset (Zenodo badge 430190456;
local copy under `our data/Amine_Earlier work/CO2_chemical_solvents-main/`).

That repo studies CO2 reaction rate (kinetics, out of this project's scope
per docs/BACKLOG.md) and CO2 binding free energy dG_MD (relevant to regeneration
energy) for amines, via MD simulation + ML (OPERA descriptors + RF/XGB
ensembles trained on many ISIDA fragment-descriptor variants).

Its `data/` and `screening/` folders hold 193 near-duplicate files: same
124 learning-set compounds / 945 screening compounds each time, differing
only in which ISIDA fragment-descriptor columns are appended. We only need
one instance of the shared identity/target/OPERA columns, so this script:

  1. Takes the column INTERSECTION across all 193 learning-set files
     (robust to which exact fragment columns are appended per file) to
     recover the common {cid, std_smiles, CompRate_ylog, dG_MD_ylog} +
     OPERA descriptor columns, from one representative file.
  2. Does the same for the 945-compound screening library (descriptors
     only, no labels).
  3. Joins the screening library against the repo's own ensemble
     predictions (results/screening/Comprate_pred.csv, dG_pred.csv) to
     pull in the real ground truth for the 124 compounds tested there
     (source in {"100MDamines","Chowdhury"}) and the RF-ensemble mean/std
     for the rest -- the ensemble spread is a ready-made epistemic
     uncertainty signal per candidate.

Outputs:
    data/processed/structured/candidate_amines_learning_set.csv   (124 rows)
    data/processed/structured/candidate_amines_screening_library.csv (945 rows)

Raw files are NOT copied into data/raw/ -- the source repo is ~500MB with
193x duplicated descriptor files, so this script reads directly from the
personal `our data/` dump (gitignored, left in place) to avoid bloating
the repo.
"""

import glob
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

SOLVENTS_REPO = (
    ROOT
    / "our data"
    / "Amine_Earlier work"
    / "CO2_chemical_solvents-main"
    / "CO2_chemical_solvents-main"
)

OUT_DIR = ROOT / "data/processed/structured"

LEARNING_OUT = OUT_DIR / "candidate_amines_learning_set.csv"
SCREENING_OUT = OUT_DIR / "candidate_amines_screening_library.csv"


def common_columns(file_glob: str) -> list:
    files = sorted(glob.glob(file_glob))
    if not files:
        raise FileNotFoundError(f"No files matched: {file_glob}")

    common = None
    for f in files:
        cols = set(pd.read_csv(f, nrows=0).columns)
        common = cols if common is None else (common & cols)

    return files, [c for c in pd.read_csv(files[0], nrows=0).columns if c in common]


def build_learning_set() -> pd.DataFrame:
    files, cols = common_columns(str(SOLVENTS_REPO / "data" / "*.csv"))

    df = pd.read_csv(files[0], usecols=cols)[cols]

    if len(df) != 124:
        raise ValueError(f"Expected 124 learning-set compounds, got {len(df)}")

    if df["std_smiles"].duplicated().any():
        raise ValueError("Duplicate SMILES in learning set")

    return df


def build_screening_library() -> pd.DataFrame:
    files, cols = common_columns(str(SOLVENTS_REPO / "screening" / "*.csv"))

    descriptors = pd.read_csv(files[0], usecols=cols)[cols]
    descriptors = descriptors.drop(columns=["source"])

    if len(descriptors) != 945:
        raise ValueError(f"Expected 945 screening compounds, got {len(descriptors)}")

    comprate = pd.read_csv(SOLVENTS_REPO / "results/screening/Comprate_pred.csv")
    dg = pd.read_csv(SOLVENTS_REPO / "results/screening/dG_pred.csv")

    comprate_rf_cols = [c for c in comprate.columns if c.endswith("_RF")]
    dg_rf_cols = [c for c in dg.columns if c.endswith("_RF")]

    comprate_slim = comprate[
        ["std_smiles", "source", "cas", "RMD", "comprate_avg_pred", "comprate_avg_pred_AD"]
    ].copy()
    comprate_slim["comprate_rf_ensemble_std"] = comprate[comprate_rf_cols].std(axis=1)

    dg_slim = dg[
        ["std_smiles", "ΔGMD", "dg_avg_pred", "dg_avg_pred_AD"]
    ].rename(columns={"ΔGMD": "dGMD"})
    dg_slim["dg_rf_ensemble_std"] = dg[dg_rf_cols].std(axis=1)

    merged = descriptors.merge(comprate_slim, on="std_smiles", how="left").merge(
        dg_slim, on="std_smiles", how="left"
    )

    if len(merged) != 945:
        raise ValueError(f"Row count changed after merge: {len(merged)}")

    return merged


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    learning = build_learning_set()
    learning.to_csv(LEARNING_OUT, index=False)
    print(f"Learning set:   {learning.shape} -> {LEARNING_OUT}")

    screening = build_screening_library()
    screening.to_csv(SCREENING_OUT, index=False)
    print(f"Screening set:  {screening.shape} -> {SCREENING_OUT}")

    print("\nScreening source breakdown:")
    print(screening["source"].value_counts().to_string())

    print(f"\nScreening rows with real ground-truth RMD: {screening['RMD'].notna().sum()}")
    print(f"Screening rows with real ground-truth dGMD: {screening['dGMD'].notna().sum()}")


if __name__ == "__main__":
    main()
