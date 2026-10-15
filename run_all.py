"""
Fresh clone -> key figures.

    smoke test -> calibrate equilibrium model on VLE data (AMP, PZ; AMP+PZ held out)
    -> screen ~23k yellow/blue mixtures with Monte Carlo UQ -> figures + shortlist

Neo4j is optional and needs a running server + .env, so it is not chained here:
    python -m src.data.load_neo4j_graph       # VLE / candidate graph
    python -m src.data.load_neo4j_mixtures    # screened mixtures (yellow / blue)
"""

import os
import subprocess
import sys

# MKL's default OpenMP threading layer is missing from the conda env on Windows and
# crashes LAPACK calls; TBB works (also set in environment.yml `variables:`).
os.environ.setdefault("MKL_THREADING_LAYER", "TBB")

STEPS = [
    ("RDKit smoke test", [sys.executable, "src/data/smoke_test.py"]),
    ("Calibrate equilibrium model", [sys.executable, "-m", "src.thermo.calibrate"]),
    ("Screen mixtures", [sys.executable, "-m", "src.screening.run_screen"]),
    ("Figures + shortlist", [sys.executable, "-m", "src.viz.screening_plots"]),
]


def main():
    for name, cmd in STEPS:
        print(f"\n=== {name} ===")
        result = subprocess.run(cmd)
        if result.returncode != 0:
            print(f"FAILED: {name}")
            sys.exit(1)
    print("\nAll steps completed.")


if __name__ == "__main__":
    main()
