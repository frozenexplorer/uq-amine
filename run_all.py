"""
Fresh clone -> ranked lists and figures.

    smoke test -> ingest data -> calibrate the equilibrium model (MEA, MDEA, AMP, PZ, DETA, DEA, MPA) ->
    screen ~23k yellow / blue mixtures with Monte Carlo UQ -> practical stage (cost + physical
    factors) -> figures, shortlist and the three lab lists

ThermoML steps need NIST. data/interim/ is tracked, so when NIST is down those steps warn and
the pipeline carries on with the stored tables.

Not chained here:
    python -m src.data.ingest_pubchem_partners   # refreshes the vendor cache (slow, needs network)
    python -m src.data.load_neo4j_graph          # VLE / candidate graph (needs a Neo4j server + .env)
    python -m src.data.load_neo4j_mixtures       # screened mixtures (yellow / blue)
"""

import os
import subprocess
import sys
from pathlib import Path

# MKL's default OpenMP threading layer is missing from the conda env on Windows and
# crashes LAPACK calls; TBB works (also set in environment.yml `variables:`).
os.environ.setdefault("MKL_THREADING_LAYER", "TBB")

ROOT = Path(__file__).resolve().parent
INTERIM = ROOT / "data" / "interim"

# (name, module or script, tracked outputs that let the pipeline survive a failed download)
STEPS = [
    ("RDKit smoke test", "src/data/smoke_test.py", ()),
    ("Ingest MEA/MDEA data (NIST ThermoML)", "src.data.ingest_thermoml_mea_mdea",
     ("mea_mdea_vle_thermoml.csv", "mdea_enthalpy_arcis2008.csv")),
    ("Ingest DETA data (Chang 2013, NIST ThermoML)", "src.data.ingest_chang2013_deta",
     ("deta_chang2013.csv",)),
    ("Ingest DEA / MPA data (NIST ThermoML)", "src.data.ingest_dea_mpa_thermoml",
     ("dea_mpa_vle_thermoml.csv", "dea_enthalpy_arcis2012.csv")),
    ("Ingest viscosity data (NIST ThermoML)", "src.data.ingest_viscosity_thermoml",
     ("viscosity_thermoml.csv",)),
    ("Ingest MDEA+PZ blend data (Xu 2011)", "src.data.ingest_xu2011_mdea_pz", ()),
    ("Ingest MEA data (Aronu 2011)", "src.data.ingest_aronu2011_mea", ()),
    ("Ingest MEA / PZ / MEA+PZ data (Dugas 2009)", "src.data.ingest_dugas2009_mea_pz", ()),
    ("Calibrate equilibrium model", "src.thermo.calibrate", ()),
    ("Screen mixtures", "src.screening.run_screen", ()),
    ("Practical stage: cost + physical factors", "src.screening.practical", ()),
    ("Screening figures + shortlist", "src.viz.screening_plots", ()),
    ("Practical figures + lab lists", "src.viz.practical_lists", ()),
]


def main():
    for name, target, fallback in STEPS:
        print(f"\n=== {name} ===")
        cmd = [sys.executable, target] if target.endswith(".py") else [sys.executable, "-m", target]
        if subprocess.run(cmd).returncode == 0:
            continue
        if fallback and all((INTERIM / f).exists() for f in fallback):
            print(f"WARNING: {name} failed; using the stored data/interim tables")
            continue
        print(f"FAILED: {name}")
        sys.exit(1)
    print("\nAll steps completed.")


if __name__ == "__main__":
    main()
