"""
Process-level performance of a solvent from the equilibrium model.

Absorber / stripper screening model (both scenarios share the stripper):

    rich  = equilibrium CO2 at absorber bottom   (T_abs, p_feed)
    lean  = equilibrium CO2 at stripper bottom   (T_strip, p_lean)
    cyclic capacity  = (rich - lean) per kg of unloaded solvent          [mol / kg]

Reboiler duty, short-cut after Oexmann & Kather (2010):

    Q_reb = Q_des + Q_sens + Q_strip                                    [kJ / mol CO2]
    Q_des   = heat of desorption, mean of the rich-end (T_top) and lean-end (T_strip)
    Q_sens  = cp * dT_hx / cyclic capacity     (heating the solvent across the HX approach)
    Q_strip = dHvap_water * p_H2O(T_top) / p*CO2(rich, T_top)   (stripping steam at the top)

with T_top = T_strip - dT_hx (rich solvent enters the stripper after the cross HX).
All values are equilibrium estimates for RANKING solvents, not plant design numbers.
"""

from __future__ import annotations

import numpy as np

from src.thermo.chemistry import MW_CO2, R_KJ, water_vapor_pressure_kpa
from src.thermo.equilibrium import Batch, heat_of_absorption, pco2_at_loading_newton, solve

SCENARIOS = {
    "cement": dict(label="Cement flue gas", T_abs=313.15, p_feed=20.0, T_strip=393.15, p_lean=5.0),
    "coal": dict(label="Coal flue gas", T_abs=313.15, p_feed=13.0, T_strip=393.15, p_lean=5.0),
}
PROCESS = dict(cp_kj_per_kg_k=3.8, dT_hx=10.0, dHvap_kj_per_mol=40.0)
KJ_PER_MOL_TO_GJ_PER_T = 1000.0 / MW_CO2 / 1000.0


def evaluate(b: Batch, sc: dict, proc: dict = PROCESS) -> dict:
    T_abs, T_strip = sc["T_abs"], sc["T_strip"]
    T_top = T_strip - proc["dT_hx"]

    rich = solve(b, T_abs, sc["p_feed"])
    lean = solve(b, T_strip, sc["p_lean"], lnH0=rich["lnH"])
    n_rich, n_lean = rich["n_co2"], lean["n_co2"]
    cyclic = (n_rich - n_lean) / b.solvent_kg_per_kg_water

    dH_rich_abs = heat_of_absorption(b, T_abs, sc["p_feed"], lnH0=rich["lnH"])
    # Clausius-Clapeyron start for p*(rich, T_top), then Newton
    lnp0 = np.log(sc["p_feed"]) + dH_rich_abs / R_KJ * (1.0 / T_abs - 1.0 / T_top)
    p_top, lnH_top = pco2_at_loading_newton(b, T_top, n_rich, lnp0)
    dH_top = heat_of_absorption(b, T_top, p_top, lnH0=lnH_top)
    dH_lean = heat_of_absorption(b, T_strip, sc["p_lean"], lnH0=lean["lnH"])
    q_des = 0.5 * (dH_top + dH_lean)

    with np.errstate(divide="ignore", invalid="ignore"):
        q_sens = proc["cp_kj_per_kg_k"] * proc["dT_hx"] / cyclic
        q_strip = proc["dHvap_kj_per_mol"] * water_vapor_pressure_kpa(T_top) / p_top
    q_reb = q_des + q_sens + q_strip
    infeasible = ~(cyclic > 1e-3) | ~np.isfinite(q_reb)
    q_reb = np.where(infeasible, np.nan, q_reb)

    return {
        "rich_loading": rich["loading"],
        "lean_loading": lean["loading"],
        "rich_mol_per_kg": n_rich / b.solvent_kg_per_kg_water,
        "lean_mol_per_kg": n_lean / b.solvent_kg_per_kg_water,
        "cyclic_mol_per_kg": cyclic,
        "dH_abs_40C": dH_rich_abs,
        "q_des": q_des,
        "q_sens": q_sens,
        "q_strip": q_strip,
        "q_reb_kj_per_mol": q_reb,
        "q_reb_gj_per_t": q_reb * KJ_PER_MOL_TO_GJ_PER_T,
        "p_top_kpa": p_top,
        "pH_rich": rich["pH"],
        "infeasible": infeasible,
    }
