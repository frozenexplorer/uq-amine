"""
Sanity checks for the practical stage. No test runner needed:

    python -m tests.test_practical

(also collected by pytest if it is installed). The first group needs no generated data; the
second is skipped until the pipeline has written data/processed/screening/mixtures_practical.csv.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.screening.practical import SCALARS, SCREEN, _draw, purchasable, reactive_group


def test_draws_keep_median_and_range():
    d = _draw("test", 2.0, 6.0, 10.0, 481)
    assert d[0] == 6.0, "sample 0 must be the nominal value"
    assert abs(np.median(d) - 6.0) < 0.1
    assert abs(np.quantile(d, 0.05) - 2.0) < 0.2
    assert abs(np.quantile(d, 0.95) - 10.0) < 0.5


def test_single_sample_is_nominal():
    assert _draw("test", 2.0, 6.0, 10.0, 1)[0] == 6.0


def test_makeup_anchors():
    """Floor + oxidation term must give MEA 1.5 kg/t and CESAR1 near the measured 0.45 kg/t."""
    floor, ox = SCALARS["makeup_floor"][1], SCALARS["makeup_ox_mea"][1]
    assert abs(floor + ox - 1.5) < 1e-9
    assert abs(floor + ox * 0.11 - 0.45) < 0.03


def test_reactive_groups_are_rejected():
    assert reactive_group("C1COC2(CCN(CC3CO3)CC2)O1") == "epoxide"
    assert reactive_group("NCCO") is None
    assert not purchasable("C1CN2CC1C1(CO1)C2", pd.DataFrame())


def _results():
    path = SCREEN / "mixtures_practical.csv"
    return pd.read_csv(path, keep_default_na=False, na_values=["", "nan"], low_memory=False) if path.exists() else None


def test_mea_is_the_zero_point():
    df = _results()
    if df is None:
        return
    mea = df[df["composition"] == "MEA 30%"].iloc[0]
    assert abs(mea["saving_vs_mea"]) < 1e-9
    assert abs(mea["coal_makeup_kg_per_t"] - 1.55) < 0.05


def test_listed_mixtures_pass_the_filter():
    df = _results()
    if df is None:
        return
    ranked = df[pd.to_numeric(df["rank_practical"], errors="coerce").notna()]
    assert (ranked["excluded_because"].fillna("") == "").all()
    assert ranked["rank_practical"].astype(float).is_unique


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
