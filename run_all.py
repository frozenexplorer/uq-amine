"""
Fresh clone -> key figures.

Currently just the Week-0 smoke test. As phases land, this will chain:
  data ingestion -> featurization -> baseline models -> UQ -> GNN -> loop target -> AL -> figures
"""

import subprocess
import sys

STEPS = [
    ("RDKit smoke test", [sys.executable, "src/data/smoke_test.py"]),
    # ("Build solubility_v1.csv", ["python3", "src/data/build_solubility_dataset.py"]),
    # ("Tabular baseline",        ["python3", "src/models/train_baseline.py"]),
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
