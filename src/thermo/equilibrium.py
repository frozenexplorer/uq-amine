"""
Vectorised equilibrium solver.

Given temperature T and CO2 partial pressure for N independent systems, solve the
charge balance for ln[H+]. Every other species is explicit in [H+] and [HCO3-]
(see chemistry.py), and the charge balance is strictly increasing in ln[H+]:

    d(charge)/d ln[H+] = [H+] + sum_j m_j Var_j(z) + [HCO3-] + 4[CO3--] + [OH-]  > 0

so a safeguarded Newton / bisection hybrid always converges. Everything is numpy over
an (N, J, S) grid: N systems x J amine sites x S species, padded with `valid=False`.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass
from typing import List, Sequence, Tuple

import numpy as np

from .chemistry import LN10, R_KJ, T_REF, AmineModel, ln_water_constants

LNH_LO, LNH_HI = -40.0, -2.0


@dataclass
class Batch:
    """N mixtures compiled to padded arrays."""
    m: np.ndarray          # (N, J) molality of each site, mol / kg water
    logK25: np.ndarray     # (N, J, S)
    dH: np.ndarray         # (N, J, S)
    sd_logK: np.ndarray    # (N, J, S)
    sd_dH: np.ndarray      # (N, J, S)
    h: np.ndarray          # (N, J, S)
    c: np.ndarray          # (N, J, S)
    valid: np.ndarray      # (N, J, S) bool
    amine_id: np.ndarray   # (N, J) int index into `amine_names` (-1 = padding)
    site_idx: np.ndarray   # (N, J) int index of the site within its amine
    amine_names: List[str]
    m_amine_total: np.ndarray  # (N,) total moles of amine molecules per kg water
    solvent_kg_per_kg_water: np.ndarray  # (N,) mass of unloaded solvent per kg water
    dCp: np.ndarray = None     # (N, J, S) optional heat-capacity term, kJ/(mol K)
    b_conc: np.ndarray = None  # (N, J, S) optional concentration term, log10 K per mol/kg
    sd_dCp: np.ndarray = None
    sd_b_conc: np.ndarray = None

    @property
    def m_sites(self) -> np.ndarray:
        """(N,) total molality of basic sites (alkalinity proxy) for the b_conc term."""
        return self.m.sum(axis=1)

    @property
    def n(self) -> int:
        return self.m.shape[0]

    def take(self, idx) -> "Batch":
        return Batch(
            self.m[idx], self.logK25[idx], self.dH[idx], self.sd_logK[idx], self.sd_dH[idx],
            self.h[idx], self.c[idx], self.valid[idx], self.amine_id[idx], self.site_idx[idx],
            self.amine_names,
            self.m_amine_total[idx], self.solvent_kg_per_kg_water[idx],
            self.dCp[idx], self.b_conc[idx], self.sd_dCp[idx], self.sd_b_conc[idx],
        )

    def repeat(self, k: int) -> "Batch":
        """Tile each system k times (system-major) for Monte Carlo."""
        r = lambda a: np.repeat(a, k, axis=0)
        return Batch(
            r(self.m), r(self.logK25), r(self.dH), r(self.sd_logK), r(self.sd_dH),
            r(self.h), r(self.c), r(self.valid), r(self.amine_id), r(self.site_idx),
            self.amine_names,
            r(self.m_amine_total), r(self.solvent_kg_per_kg_water),
            r(self.dCp), r(self.b_conc), r(self.sd_dCp), r(self.sd_b_conc),
        )


def _sites(model: AmineModel) -> List[AmineModel]:
    return model.site_models if model.site_models else [model]


def compile_batch(mixtures: Sequence[Sequence[Tuple[AmineModel, float]]]) -> Batch:
    """mixtures: list of [(AmineModel, molality mol/kg water), ...]."""
    names: List[str] = []
    name_idx = {}
    rows = []
    for mix in mixtures:
        row = []
        for model, molality in mix:
            if model.name not in name_idx:
                name_idx[model.name] = len(names)
                names.append(model.name)
            for k, site in enumerate(_sites(model)):
                row.append((name_idx[model.name], k, site, molality))
        rows.append(row)

    N = len(rows)
    J = max(1, max(len(r) for r in rows))
    S = max([len(site.species) for r in rows for _, _, site, _ in r] or [1])

    m = np.zeros((N, J))
    logK25 = np.zeros((N, J, S))
    dH = np.zeros((N, J, S))
    sdK = np.zeros((N, J, S))
    sdH = np.zeros((N, J, S))
    dCp = np.zeros((N, J, S))
    bcon = np.zeros((N, J, S))
    sd_dCp = np.zeros((N, J, S))
    sd_b = np.zeros((N, J, S))
    h = np.zeros((N, J, S))
    c = np.zeros((N, J, S))
    valid = np.zeros((N, J, S), dtype=bool)
    aid = -np.ones((N, J), dtype=int)
    sidx = np.zeros((N, J), dtype=int)

    for i, row in enumerate(rows):
        for j, (a, k, site, molality) in enumerate(row):
            m[i, j] = molality
            aid[i, j] = a
            sidx[i, j] = k
            for s, sp in enumerate(site.species):
                logK25[i, j, s] = sp.logK25
                dH[i, j, s] = sp.dH
                sdK[i, j, s] = sp.sd_logK
                sdH[i, j, s] = sp.sd_dH
                dCp[i, j, s] = sp.dCp
                bcon[i, j, s] = sp.b_conc
                sd_dCp[i, j, s] = sp.sd_dCp
                sd_b[i, j, s] = sp.sd_b_conc
                h[i, j, s] = sp.h
                c[i, j, s] = sp.c
                valid[i, j, s] = True
        # padding sites (and pure water) get a dummy free species with m = 0
        valid[i, len(row):, 0] = True

    m_tot = np.array([sum(mol for _, mol in mix) for mix in mixtures], dtype=float)
    solvent = np.array(
        [1.0 + sum(mol * model.mw / 1000.0 for model, mol in mix) for mix in mixtures],
        dtype=float,
    )
    return Batch(m, logK25, dH, sdK, sdH, h, c, valid, aid, sidx, names, m_tot, solvent,
                 dCp, bcon, sd_dCp, sd_b)


MAX_SITES, MAX_SPECIES = 6, 8


def _amine_draws(name: str, k: int, seed: int) -> np.ndarray:
    """Standard-normal draws for one amine, keyed by (seed, amine name) only."""
    rng = np.random.default_rng([seed, zlib.crc32(name.encode())])
    # channels: logK25, dH, dCp, b_conc. C-order fill keeps channels 0-1 identical to the
    # earlier 2-channel draws, so adding channels did not change existing samples.
    return rng.standard_normal((4, k, MAX_SITES, MAX_SPECIES))


def sample_batch(batch: Batch, k: int, seed: int) -> Tuple[Batch, np.ndarray]:
    """
    Monte Carlo: tile each system k times and perturb logK25 / dH by their 1-sigma.
    Draws depend only on (seed, amine name, sample, site, species), so an amine gets
    the SAME constants in sample k of every mixture and every batch (common random
    numbers). Rank comparisons and top-N probabilities across the whole screen are
    therefore consistent. Sample 0 is always the unperturbed (nominal) model.
    Returns the tiled batch and the sample index of each row.
    """
    S = batch.logK25.shape[2]
    A = len(batch.amine_names)
    n_site = int(batch.site_idx.max()) + 1
    draws = np.zeros((4, k, A + 1, n_site, S))
    for a, name in enumerate(batch.amine_names):
        draws[:, :, a] = _amine_draws(name, k, seed)[:, :, :n_site, :S]
    draws[:, 0] = 0.0
    epsK, epsH, epsC, epsB = draws
    tiled = batch.repeat(k)
    sample_idx = np.tile(np.arange(k), batch.n)
    aid = np.where(tiled.amine_id < 0, A, tiled.amine_id)          # (N*k, J)
    site = tiled.site_idx
    eK = epsK[sample_idx[:, None], aid, site]                      # (N*k, J, S)
    eH = epsH[sample_idx[:, None], aid, site]
    tiled.logK25 = tiled.logK25 + tiled.sd_logK * eK
    tiled.dH = tiled.dH + tiled.sd_dH * eH
    tiled.dCp = tiled.dCp + tiled.sd_dCp * epsC[sample_idx[:, None], aid, site]
    tiled.b_conc = tiled.b_conc + tiled.sd_b_conc * epsB[sample_idx[:, None], aid, site]
    return tiled, sample_idx


# ---------------------------------------------------------------------------
# Core solve
# ---------------------------------------------------------------------------
def _species_lnK(b: Batch, T: np.ndarray) -> np.ndarray:
    Tc = T[:, None, None]
    return (b.logK25 * LN10
            - b.dH / R_KJ * (1.0 / Tc - 1.0 / T_REF)
            + b.dCp / R_KJ * (np.log(Tc / T_REF) + T_REF / Tc - 1.0)
            + b.b_conc * b.m_sites[:, None, None] * LN10)


def _charge(base, z, m, lnH, lnK2, lnKw, lnHCO3c):
    """Charge balance f and df/dlnH. base = lnK_S + c*ln(K1 [CO2]) (+ -inf padding),
    so ln w_S = base + z*lnH and [HCO3-] = exp(lnHCO3c - lnH)."""
    lnw = base + z * lnH[:, None, None]
    mx = lnw.max(axis=2, keepdims=True)
    e = np.exp(lnw - mx)
    frac = e / e.sum(axis=2, keepdims=True)
    ez = np.sum(frac * z, axis=2)
    varz = np.sum(frac * z * z, axis=2) - ez * ez
    lnHCO3 = lnHCO3c - lnH
    H = np.exp(lnH)
    HCO3 = np.exp(lnHCO3)
    CO3 = np.exp(lnK2 + lnHCO3 - lnH)
    OH = np.exp(lnKw - lnH)
    f = H + np.sum(m * ez, axis=1) - HCO3 - 2.0 * CO3 - OH
    df = H + np.sum(m * varz, axis=1) + HCO3 + 4.0 * CO3 + OH
    return f, df, frac


def solve(b: Batch, T, pco2_kpa, n_iter: int = 80, tol: float = 1e-10, lnH0=None) -> dict:
    """
    Speciate N systems at (T [K], pCO2 [kPa]).
    Returns dict with lnH, total dissolved CO2 molality `n_co2`, loading per mol amine,
    and per-site carbamate / protonation fractions.
    `lnH0` warm-starts Newton (e.g. from a nearby state); only unconverged systems
    are iterated (active set), so cost scales with the hard cases, not the batch.
    """
    T = np.broadcast_to(np.asarray(T, dtype=float), (b.n,)).copy()
    lnp = np.log(np.broadcast_to(np.asarray(pco2_kpa, dtype=float), (b.n,)))
    lnK1, lnK2, lnKw, lnHco2 = ln_water_constants(T)
    lnCO2 = lnp - lnHco2
    lnHCO3c = lnK1 + lnCO2                                    # ln[HCO3-] + ln[H+]
    z = b.h - b.c
    base = (_species_lnK(b, T) + b.c * lnHCO3c[:, None, None]
            + np.where(b.valid, 0.0, -np.inf))

    x = np.full(b.n, -20.0) if lnH0 is None else np.clip(np.asarray(lnH0, float), LNH_LO + 1, LNH_HI - 1).copy()
    lo = np.full(b.n, LNH_LO)
    hi = np.full(b.n, LNH_HI)
    act = np.arange(b.n)
    for _ in range(n_iter):
        f, df, _ = _charge(base[act], z[act], b.m[act], x[act], lnK2[act], lnKw[act], lnHCO3c[act])
        xa = x[act]
        lo[act] = np.where(f < 0, xa, lo[act])
        hi[act] = np.where(f > 0, xa, hi[act])
        xn = xa - f / np.maximum(df, 1e-300)
        bad = (xn < lo[act]) | (xn > hi[act]) | ~np.isfinite(xn)
        xn = np.where(bad, 0.5 * (lo[act] + hi[act]), xn)
        moving = np.abs(xn - xa) >= tol
        x[act] = xn
        act = act[moving]
        if act.size == 0:
            break

    lnH = x
    _, _, frac = _charge(base, z, b.m, lnH, lnK2, lnKw, lnHCO3c)
    lnHCO3 = lnHCO3c - lnH
    CO2aq = np.exp(lnCO2)
    HCO3 = np.exp(lnHCO3)
    CO3 = np.exp(lnK2 + lnHCO3 - lnH)
    carb = np.sum(b.m * np.sum(frac * b.c, axis=2), axis=1)
    n_co2 = CO2aq + HCO3 + CO3 + carb
    with np.errstate(divide="ignore", invalid="ignore"):
        loading = n_co2 / b.m_amine_total
    return {
        "lnH": lnH,
        "pH": -lnH / LN10,
        "n_co2": n_co2,
        "loading": loading,
        "carbamate_co2": carb,
        "bicarbonate_co2": HCO3 + CO3,
        "physical_co2": CO2aq,
    }


def pco2_at_loading(b: Batch, T, n_co2_target, n_iter: int = 45,
                    lnp_lo: float = np.log(1e-6), lnp_hi: float = np.log(1e6)) -> np.ndarray:
    """Inverse problem: CO2 partial pressure (kPa) giving a target total CO2 molality.
    n_co2 is strictly increasing in pCO2, so plain bisection on ln p."""
    T = np.broadcast_to(np.asarray(T, dtype=float), (b.n,)).copy()
    target = np.broadcast_to(np.asarray(n_co2_target, dtype=float), (b.n,))
    lo = np.full(b.n, lnp_lo)
    hi = np.full(b.n, lnp_hi)
    for _ in range(n_iter):
        mid = 0.5 * (lo + hi)
        n = solve(b, T, np.exp(mid))["n_co2"]
        below = n < target
        lo = np.where(below, mid, lo)
        hi = np.where(below, hi, mid)
    return np.exp(0.5 * (lo + hi))


def heat_of_absorption(b: Batch, T, pco2_kpa, dT: float = 1.0, dlnp: float = 0.01,
                       lnH0=None) -> np.ndarray:
    """
    Differential heat of absorption (kJ / mol CO2, reported positive) at the state
    (T, pCO2), from Gibbs-Helmholtz at constant total CO2:

        dH_abs = R d ln p / d(1/T) |_n = -R T^2 (d ln p / dT)|_n
        (d ln p / dT)|_n = -(dn/dT)|_p / (dn/d ln p)|_T

    using central finite differences on forward solves only (no inverse needed).
    """
    T = np.broadcast_to(np.asarray(T, dtype=float), (b.n,)).copy()
    p = np.broadcast_to(np.asarray(pco2_kpa, dtype=float), (b.n,)).copy()
    if lnH0 is None:
        lnH0 = solve(b, T, p)["lnH"]
    n_Tp = solve(b, T + dT, p, lnH0=lnH0)["n_co2"]
    n_Tm = solve(b, T - dT, p, lnH0=lnH0)["n_co2"]
    n_pp = solve(b, T, p * np.exp(dlnp), lnH0=lnH0)["n_co2"]
    n_pm = solve(b, T, p * np.exp(-dlnp), lnH0=lnH0)["n_co2"]
    dn_dT = (n_Tp - n_Tm) / (2 * dT)
    dn_dlnp = (n_pp - n_pm) / (2 * dlnp)
    dlnp_dT = -dn_dT / np.maximum(dn_dlnp, 1e-300)
    return R_KJ * T ** 2 * dlnp_dT


def pco2_at_loading_newton(b: Batch, T, n_co2_target, lnp0, n_iter: int = 40,
                           tol: float = 1e-6, dlnp: float = 1e-3) -> tuple:
    """
    Faster inverse: safeguarded Newton on ln p starting from `lnp0` (e.g. a
    Clausius-Clapeyron estimate). n_co2 is increasing in ln p, so a running bracket
    keeps every step valid; falls back to bisection when Newton leaves the bracket.
    Only unconverged systems are re-solved, each warm-started from its last ln[H+].
    Returns (pCO2 kPa, ln[H+] at the solution).
    """
    T = np.broadcast_to(np.asarray(T, dtype=float), (b.n,)).copy()
    target = np.broadcast_to(np.asarray(n_co2_target, dtype=float), (b.n,)).copy()
    lo = np.full(b.n, np.log(1e-6))
    hi = np.full(b.n, np.log(1e6))
    x = np.clip(np.asarray(lnp0, dtype=float), lo + 1, hi - 1).copy()
    lnH = np.full(b.n, -20.0)
    act = np.arange(b.n)
    for _ in range(n_iter):
        sub = b.take(act)
        r0 = solve(sub, T[act], np.exp(x[act]), lnH0=lnH[act])
        lnH[act] = r0["lnH"]
        n1 = solve(sub, T[act], np.exp(x[act] + dlnp), lnH0=r0["lnH"])["n_co2"]
        xa = x[act]
        g = r0["n_co2"] - target[act]
        lo[act] = np.where(g < 0, xa, lo[act])
        hi[act] = np.where(g > 0, xa, hi[act])
        slope = (n1 - r0["n_co2"]) / dlnp
        xn = xa - g / np.maximum(slope, 1e-300)
        bad = (xn < lo[act]) | (xn > hi[act]) | ~np.isfinite(xn)
        xn = np.where(bad, 0.5 * (lo[act] + hi[act]), xn)
        moving = np.abs(xn - xa) >= tol
        x[act] = xn
        act = act[moving]
        if act.size == 0:
            break
    return np.exp(x), lnH
