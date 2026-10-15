"""
Chemistry definitions for the amine-CO2-H2O equilibrium model.

Kent-Eisenberg-style ideal speciation model on a molality basis (mol / kg water).
Every amine is described by a list of *species* relative to its free (neutral) form:

    [S] = K_S(T) * [Am] * [H+]^h * [HCO3-]^c          charge(S) = h - c

    h = protons added, c = carbamate groups added (Am + HCO3- <-> AmCOO- + H2O)
    K_S(T) = 10^logK25 * exp(-dH/R * (1/T - 1/298.15))       (van 't Hoff)

so protonation (h=1, c=0), carbamate (h=0, c=1), protonated carbamate (h=1, c=1),
dicarbamate (h=0, c=2) etc. all share one representation. "Apparent" constants are
calibrated against VLE data (src/thermo/calibrate.py), which absorbs non-ideality.

Water / CO2 constants: Edwards et al. (1978), molality basis -- same expressions as the
legacy BlendCO2 single.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import List, Optional

import numpy as np

R_KJ = 8.314462618e-3  # kJ / (mol K)
T_REF = 298.15
LN10 = np.log(10.0)
MW_WATER = 18.015
MW_CO2 = 44.01


# ---------------------------------------------------------------------------
# Water / CO2 system:  ln K = a/T + b ln T + c T + d
# ---------------------------------------------------------------------------
_EDWARDS = {
    "K1": (-12092.1, -36.7816, 0.0, 235.482),        # CO2 + H2O <-> HCO3- + H+
    "K2": (-12431.7, -35.4819, 0.0, 220.067),        # HCO3- <-> CO3-- + H+
    "Kw": (-13445.9, -22.4773, 0.0, 140.932),        # H2O <-> H+ + OH-
    "HCO2": (-6789.04, -11.4519, -0.010454, 94.4914),  # Henry, atm kg / mol
}


def _ln_edwards(name: str, T):
    a, b, c, d = _EDWARDS[name]
    T = np.asarray(T, dtype=float)
    return a / T + b * np.log(T) + c * T + d


def ln_water_constants(T):
    """Return ln K1, ln K2, ln Kw, ln H_CO2 (H in kPa kg / mol)."""
    return (
        _ln_edwards("K1", T),
        _ln_edwards("K2", T),
        _ln_edwards("Kw", T),
        _ln_edwards("HCO2", T) + np.log(101.325),
    )


def water_vapor_pressure_kpa(T):
    """Antoine equation for pure water (kPa); two ranges, good to ~1 % over 1-200 C."""
    tc = np.asarray(T, dtype=float) - 273.15
    lo = 8.07131 - 1730.63 / (233.426 + tc)
    hi = 8.14019 - 1810.94 / (244.485 + tc)
    log10_mmhg = np.where(tc <= 100.0, lo, hi)
    return 10.0 ** log10_mmhg * 0.133322


# ---------------------------------------------------------------------------
# Amine description
# ---------------------------------------------------------------------------
@dataclass
class Species:
    name: str
    h: int
    c: int
    logK25: float
    dH: float                 # kJ/mol for forming this species from free amine
    sd_logK: float = 0.0      # 1-sigma uncertainty used for Monte Carlo propagation
    sd_dH: float = 0.0

    @property
    def charge(self) -> int:
        return self.h - self.c


@dataclass
class AmineModel:
    """One amine (or one independent basic site of a polyamine, see `sites`)."""
    name: str
    smiles: str
    mw: float
    species: List[Species]
    sites: int = 1                      # number of independent pseudo-sites (polyamines)
    source: str = "literature"          # literature | calibrated | predicted
    note: str = ""
    site_models: Optional[List["AmineModel"]] = field(default=None, repr=False)

    def with_species(self, species: List[Species], **kw) -> "AmineModel":
        return replace(self, species=species, **kw)


def _sp(name, h, c, logK25, dH, sd_logK=0.0, sd_dH=0.0):
    return Species(name, h, c, logK25, dH, sd_logK, sd_dH)


# ---------------------------------------------------------------------------
# Literature priors for the four core amines (25 C, infinite-dilution-ish values).
# These are STARTING points; AMP and PZ are recalibrated in calibrate.py.
# MEA and MDEA currently have no pCO2-loading data in the repo -> literature only,
# carried with wider uncertainty until data arrives.
#
#   MEA  pKa 9.50, dH_prot -50.5      (Kim et al. 1987; Bates & Pinching)
#        carbamate log K ~1.5, dH ~-23 (Austgen 1989 / Aroua 1999 order of magnitude;
#        dH chosen so overall dH_abs ~ -85 kJ/mol at low loading)
#   MDEA pKa 8.56, dH_prot -34.9      (Kamps & Maurer 1996; Oscarson 1989)
#   AMP  pKa 9.68, dH_prot -54.0      (Hamborg & Versteeg 2009); unstable carbamate
#   PZ   pKa1 9.73 (-42.9), pKa2 5.35 (-31.1) (Hetzer 1967); carbamate / protonated
#        carbamate / dicarbamate after Ermatchkov et al. (2003) order of magnitude
# ---------------------------------------------------------------------------
def core_amines() -> dict:
    return {
        "MEA": AmineModel(
            "MEA", "NCCO", 61.08,
            [
                _sp("MEA", 0, 0, 0.0, 0.0),
                _sp("MEAH+", 1, 0, 9.50, -50.5, 0.15, 3.0),
                _sp("MEACOO-", 0, 1, 1.50, -23.0, 0.35, 8.0),
            ],
            note="literature priors; no pCO2-loading data in repo yet",
        ),
        "MDEA": AmineModel(
            "MDEA", "CN(CCO)CCO", 119.16,
            [
                _sp("MDEA", 0, 0, 0.0, 0.0),
                _sp("MDEAH+", 1, 0, 8.56, -34.9, 0.15, 3.0),
            ],
            note="literature priors; no pCO2-loading data in repo yet",
        ),
        "AMP": AmineModel(
            "AMP", "CC(C)(N)CO", 89.14,
            [
                _sp("AMP", 0, 0, 0.0, 0.0),
                _sp("AMPH+", 1, 0, 9.68, -54.0, 0.15, 3.0),
                _sp("AMPCOO-", 0, 1, -1.00, -15.0, 0.50, 8.0),
            ],
        ),
        "PZ": AmineModel(
            "PZ", "C1CNCCN1", 86.14,
            [
                _sp("PZ", 0, 0, 0.0, 0.0),
                _sp("PZH+", 1, 0, 9.73, -42.9, 0.15, 3.0),
                _sp("PZH2++", 2, 0, 15.08, -74.0, 0.25, 5.0),
                _sp("PZCOO-", 0, 1, 1.40, -20.0, 0.35, 8.0),
                _sp("H+PZCOO-", 1, 1, 10.84, -50.0, 0.40, 8.0),
                _sp("PZ(COO-)2", 0, 2, 1.90, -40.0, 0.50, 10.0),
            ],
        ),
    }


CORE_NAMES = ("MEA", "MDEA", "AMP", "PZ")
