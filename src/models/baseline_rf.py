from pathlib import Path
import json
import joblib
import numpy as np
import pandas as pd

from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


# --------------------------------------------------
# Paths
# --------------------------------------------------

DATA_PATH = Path("data/processed/structured/modeling_dataset.csv")
MODEL_DIR = Path("models")

MODEL_DIR.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------
# Features / target
# --------------------------------------------------

FEATURES = [
    "T_C",
    "P_kPa",
    "wt_percent",
    "molarity",
    "x1",
]

TARGET = "x2"


# --------------------------------------------------
# Load data
# --------------------------------------------------

df = pd.read_csv(DATA_PATH)

X = df[FEATURES]
y = df[TARGET]


# --------------------------------------------------
# Train / test split
# --------------------------------------------------

X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.20,
    random_state=42,
)


# --------------------------------------------------
# Model
# --------------------------------------------------

model = RandomForestRegressor(
    n_estimators=300,
    min_samples_leaf=2,
    random_state=42,
    n_jobs=-1,
)

model.fit(X_train, y_train)


# --------------------------------------------------
# Evaluation
# --------------------------------------------------

pred = model.predict(X_test)

mae = mean_absolute_error(y_test, pred)
rmse = np.sqrt(mean_squared_error(y_test, pred))
r2 = r2_score(y_test, pred)


# --------------------------------------------------
# Save model
# --------------------------------------------------

joblib.dump(
    model,
    MODEL_DIR / "baseline_random_forest.joblib",
)


# --------------------------------------------------
# Save metrics
# --------------------------------------------------

metrics = {
    "model": "RandomForestRegressor",
    "target": TARGET,
    "features": FEATURES,
    "train_rows": len(X_train),
    "test_rows": len(X_test),
    "mae": float(mae),
    "rmse": float(rmse),
    "r2": float(r2),
}

with open(MODEL_DIR / "baseline_random_forest_metrics.json", "w") as f:
    json.dump(metrics, f, indent=2)


# --------------------------------------------------
# Output
# --------------------------------------------------

print("=" * 70)
print("BASELINE RANDOM FOREST")
print("=" * 70)

print("\nFeatures:")
print(FEATURES)

print("\nTrain rows:", len(X_train))
print("Test rows:", len(X_test))

print("\nPerformance:")
print(f"MAE  : {mae:.8f}")
print(f"RMSE : {rmse:.8f}")
print(f"R²   : {r2:.6f}")

print("\nFeature importance:")
importance = pd.Series(
    model.feature_importances_,
    index=FEATURES,
).sort_values(ascending=False)

print(importance.to_string())

print("\nSaved:")
print(" - models/baseline_random_forest.joblib")
print(" - models/baseline_random_forest_metrics.json")
