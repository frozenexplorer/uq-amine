"""Load the calibrated core-amine models written by src/thermo/calibrate.py."""

from __future__ import annotations

import json
from pathlib import Path

from .chemistry import AmineModel, Species, core_amines

ROOT = Path(__file__).resolve().parents[2]
PARAMS_JSON = ROOT / "data" / "processed" / "thermo" / "calibrated_core_amines.json"


def load_core_models() -> tuple:
    """Returns ({name: AmineModel}, loading_discrepancy_q90). Falls back to priors."""
    if not PARAMS_JSON.exists():
        return core_amines(), 0.10
    payload = json.loads(PARAMS_JSON.read_text())
    models = {}
    for name, d in payload["amines"].items():
        models[name] = AmineModel(name, d["smiles"], d["mw"],
                                  [Species(**s) for s in d["species"]],
                                  source=d["source"], note=d["note"])
    return models, float(payload["loading_discrepancy_q90"])


def load_partner_models() -> dict:
    """Partner amines calibrated on CO2 data (polyamines keep one model per basic site)."""
    if not PARAMS_JSON.exists():
        return {}
    out = {}
    for name, d in json.loads(PARAMS_JSON.read_text()).get("partners", {}).items():
        sites = [AmineModel(f"{name}#{k}", d["smiles"], d["mw"], [Species(**s) for s in sp])
                 for k, sp in enumerate(d["sites"])]
        out[name] = AmineModel(name, d["smiles"], d["mw"], sites[0].species, sites=len(sites),
                               source=d["source"], note=d["note"], site_models=sites)
    return out
