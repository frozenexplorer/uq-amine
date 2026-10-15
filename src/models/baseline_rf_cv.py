from pathlib import Path
import json
import joblib
import numpy as np
import pandas as pd

from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import KFold, cross_validate


DATA_PATH = Path("data/processed/structured/modeling_dataset.csv")
MODEL_DIR = Path("models")

FEATURES = [
    "T_C",
    "P_kPa",
    "wt_percent",
    "molarity",
    "x1",
]

TARGET = "x2"


df = pd.read_csv(DATA_PATH)

X = df[FEATURES]
y = df[TARGET]


model = RandomForestRegressor(
    n_estimators=300,
    min_samples_leaf=2,
    random_state=42,
    n_jobs=-1,
)


cv = KFold(
    n_splits=5,
    shuffle=True,
    random_state=42,
)


scores = cross_validate(
    model,
    X,
    y,
    cv=cv,
    scoring={
        "mae": "neg_mean_absolute_error",
        "rmse": "neg_root_mean_squared_error",
        "r2": "r2",
    },
    n_jobs=-1,
)


mae = -scores["test_mae"]
rmse = -scores["test_rmse"]
r2 = scores["test_r2"]


metrics = {
    "model": "RandomForestRegressor",
    "target": TARGET,
    "features": FEATURES,
    "folds": 5,
    "mae_mean": float(mae.mean()),
    "mae_std": float(mae.std()),
    "rmse_mean": float(rmse.mean()),
    "rmse_std": float(rmse.std()),
    "r2_mean": float(r2.mean()),
    "r2_std": float(r2.std()),
    "fold_mae": mae.tolist(),
    "fold_rmse": rmse.tolist(),
    "fold_r2": r2.tolist(),
}


with open(
    MODEL_DIR / "baseline_random_forest_cv_metrics.json",
    "w",
) as f:
    json.dump(metrics, f, indent=2)


print("=" * 70)
print("5-FOLD CROSS-VALIDATION — RANDOM FOREST")
print("=" * 70)

print("\nFeatures:")
print(FEATURES)

print("\nFold results:")

for i in range(5):
    print(
        f"Fold {i + 1}: "
        f"MAE={mae[i]:.8f}, "
        f"RMSE={rmse[i]:.8f}, "
        f"R²={r2[i]:.6f}"
    )

print("\nMean ± Std:")

print(f"MAE  : {mae.mean():.8f} ± {mae.std():.8f}")
print(f"RMSE : {rmse.mean():.8f} ± {rmse.std():.8f}")
print(f"R²   : {r2.mean():.6f} ± {r2.std():.6f}")

print("\nSaved:")
print(" - models/baseline_random_forest_cv_metrics.json")
