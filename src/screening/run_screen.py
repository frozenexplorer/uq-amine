"""
Enumerate, score and rank candidate amine mixtures (total amine fixed at 30 wt%).

    REFERENCE  single core amines (MEA, MDEA, AMP, PZ) - benchmarks
    YELLOW     >= 2 of the core four (MEA, MDEA, PZ, AMP) only, 2.5 wt% grid
    BLUE       >= 1 core amine + >= 1 partner amine (curated literature + library)
                 stage 1: 1 core + 1 partner, partner at 5..25 wt% (5 wt% steps)
                 stage 2: best purchasable partners -> 2 core + 1 partner and 1 core +
                          2 partners, 5 wt% grid, every component >= 5 wt%

Each mixture is evaluated with Monte Carlo over model parameters (common random
numbers: sample k uses the same draw of every amine's constants in every mixture),
under both scenarios. Score per sample, relative to 30 wt% MEA in the same sample:

    score = 0.5 ln(cyclic / cyclic_MEA) + 0.5 ln(Q_reb_MEA / Q_reb)    (> 0 beats MEA)

Outputs (data/processed/screening/):
    mixtures_ranked.csv   one row per mixture, both scenarios, intervals, ranks
    partners.csv          the partner pool with structure classes and pKa sources
    run_meta.json         settings, counts, timing
    mc_samples.npz        per-sample capacity and reboiler duty, for the practical stage

Run:  python -m src.screening.run_screen
"""

from __future__ import annotations

import itertools
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from src.thermo.calibrated import load_core_models, load_partner_models
from src.thermo.chemistry import CORE_NAMES
from src.thermo.equilibrium import compile_batch, sample_batch

from .partners import build_model, build_pool
from .practical import load_availability, purchasable
from .process import PROCESS, SCENARIOS, evaluate

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "processed" / "screening"

TOTAL_WT = 30.0
YELLOW_STEP = 2.5
BLUE_STEP = 5.0
N_STAGE2_PARTNERS = 25
K_SAMPLES = 48
CHUNK = 60_000          # systems per evaluation chunk (memory)
SEED = 2026
TOP_N = (25, 50, 75, 100)
MAX_PER_COMPONENT_SET = 2


# ---------------------------------------------------------------------------
# Enumeration
# ---------------------------------------------------------------------------
def compositions(n_parts: int, units: int, min_units: int = 0):
    """All integer vectors of length n_parts summing to units, each >= min_units."""
    for cut in itertools.combinations(range(units + n_parts - 1), n_parts - 1):
        parts = np.diff((-1,) + cut + (units + n_parts - 1,)) - 1
        if parts.min() >= min_units:
            yield parts


def yellow_and_reference():
    units = int(round(TOTAL_WT / YELLOW_STEP))
    out = []
    for parts in compositions(4, units):
        comp = {n: p * YELLOW_STEP for n, p in zip(CORE_NAMES, parts) if p > 0}
        color = "reference" if len(comp) == 1 else "yellow"
        out.append((color, comp))
    return out


def blue_stage1(partner_names):
    out = []
    for core in CORE_NAMES:
        for p in partner_names:
            for w in np.arange(BLUE_STEP, TOTAL_WT, BLUE_STEP):
                out.append(("blue", {core: TOTAL_WT - w, p: float(w)}))
    return out


def blue_stage2(partner_names):
    units = int(round(TOTAL_WT / BLUE_STEP))
    out = []
    for c1, c2 in itertools.combinations(CORE_NAMES, 2):
        for p in partner_names:
            for parts in compositions(3, units, 1):
                out.append(("blue", dict(zip((c1, c2, p), parts * BLUE_STEP))))
    for core in CORE_NAMES:
        for p1, p2 in itertools.combinations(partner_names, 2):
            for parts in compositions(3, units, 1):
                out.append(("blue", dict(zip((core, p1, p2), parts * BLUE_STEP))))
    return out


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------
def to_molality(comp: dict, models: dict):
    water = 100.0 - sum(comp.values())
    return [(models[n], w / models[n].mw * 1000.0 / water) for n, w in comp.items()]


def evaluate_mixtures(mixes, models, k, seed):
    """Returns {scenario: {metric: (n_mix, k) array}} plus the batch (nominal)."""
    batch = compile_batch([to_molality(c, models) for _, c in mixes])
    tiled, _ = sample_batch(batch, k, seed)
    res = {}
    for sname, sc in SCENARIOS.items():
        parts = []
        for start in range(0, tiled.n, CHUNK):
            parts.append(evaluate(tiled.take(slice(start, start + CHUNK)), sc))
        res[sname] = {key: np.concatenate([p[key] for p in parts]).reshape(batch.n, k)
                      for key in parts[0]}
    return res, batch


def summarise(mixes, res, batch, mea_ref, q_disc):
    rows = []
    m_tot = batch.m_amine_total
    solvent = batch.solvent_kg_per_kg_water
    delta_cap = q_disc * m_tot / solvent        # loading discrepancy -> mol/kg
    scores = {}
    for sname, r in res.items():
        cap, q = r["cyclic_mol_per_kg"], r["q_reb_kj_per_mol"]
        cap_mea, q_mea = mea_ref[sname]
        with np.errstate(divide="ignore", invalid="ignore"):
            s = 0.5 * np.log(cap / cap_mea[None, :]) + 0.5 * np.log(q_mea[None, :] / q)
        s = np.where(np.isfinite(s), s, -np.inf)
        scores[sname] = s
    for i, (color, comp) in enumerate(mixes):
        row = {"color": color, "n_components": len(comp),
               "composition": " + ".join(f"{n} {w:g}%" for n, w in comp.items())}
        for n in CORE_NAMES:
            row[f"wt_{n}"] = comp.get(n, 0.0)
        partners = [n for n in comp if n not in CORE_NAMES]
        row["partners"] = "|".join(partners)
        row["partner_wt"] = "|".join(f"{comp[n]:g}" for n in partners)
        for sname, r in res.items():
            pre = f"{sname}_"
            cap, q = r["cyclic_mol_per_kg"][i], r["q_reb_gj_per_t"][i]
            s = scores[sname][i]
            q_sens = r["q_sens"][i, 0] / 44.01
            row[pre + "rich_loading"] = r["rich_loading"][i, 0]
            row[pre + "lean_loading"] = r["lean_loading"][i, 0]
            row[pre + "cyclic"] = cap[0]
            row[pre + "cyclic_lo90"] = np.nanquantile(cap, 0.05) - delta_cap[i]
            row[pre + "cyclic_hi90"] = np.nanquantile(cap, 0.95) + delta_cap[i]
            row[pre + "q_reb"] = q[0]
            row[pre + "q_reb_lo90"] = np.nanquantile(q, 0.05)
            row[pre + "q_reb_hi90"] = np.nanquantile(q, 0.95) + q_sens * delta_cap[i] / max(cap[0], 1e-6)
            row[pre + "dH_abs_40C"] = r["dH_abs_40C"][i, 0]
            row[pre + "q_des"] = r["q_des"][i, 0]
            row[pre + "q_sens"] = r["q_sens"][i, 0]
            row[pre + "q_strip"] = r["q_strip"][i, 0]
            fin = np.isfinite(s)
            disc = 0.5 * delta_cap[i] / max(cap[0], 1e-6) * (1 + q_sens / max(q[0], 1e-6))
            row[pre + "score"] = s[0]
            row[pre + "score_median"] = np.median(s[fin]) if fin.any() else -np.inf
            row[pre + "score_lo90"] = (np.quantile(s[fin], 0.05) if fin.any() else -np.inf) - disc
            row[pre + "score_hi90"] = (np.quantile(s[fin], 0.95) if fin.any() else -np.inf) + disc
            row[pre + "p_beats_mea"] = float(np.mean(s > 0))
            row[pre + "infeasible_frac"] = float(np.mean(r["infeasible"][i]))
        rows.append(row)
    return pd.DataFrame(rows), scores


def top_n_probability(scores: np.ndarray, n: int) -> np.ndarray:
    """Fraction of MC samples in which each mixture ranks inside the top n."""
    order = np.argsort(-scores, axis=0)
    hit = np.zeros(scores.shape[0])
    for k in range(scores.shape[1]):
        hit[order[:n, k]] += 1
    return hit / scores.shape[1]


def component_set(row) -> str:
    names = [n for n in CORE_NAMES if row[f"wt_{n}"] > 0]
    names += [p for p in str(row["partners"]).split("|") if p]
    return "+".join(sorted(names))


def diverse_ranks(df: pd.DataFrame, per_set: int = MAX_PER_COMPONENT_SET) -> np.ndarray:
    """Greedy, score-ordered rank that keeps at most `per_set` proportions of the same
    amine combination, so a lab shortlist covers different chemistries. Mixtures beyond
    the cap get rank 0 (not in the diverse list)."""
    order = df["score_both"].to_numpy().argsort()[::-1]
    sets = df.apply(component_set, axis=1).to_numpy()
    seen, out, k = {}, np.zeros(len(df), dtype=int), 0
    for i in order:
        if seen.get(sets[i], 0) < per_set:
            seen[sets[i]] = seen.get(sets[i], 0) + 1
            k += 1
            out[i] = k
    return out


# ---------------------------------------------------------------------------
def main():
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    core, q_disc = load_core_models()
    partners, pool_log, _ = build_pool({k: v.smiles for k, v in core.items()})
    calibrated = load_partner_models()
    pmodels = {p.name: calibrated.get(p.name) or build_model(p) for p in partners}
    models = {**core, **pmodels}

    # 30 wt% MEA is evaluated at the head of every batch as the per-sample benchmark.
    def run(mixes, tag):
        t = time.time()
        allmix = [("reference", {"MEA": TOTAL_WT})] + mixes
        res, batch = evaluate_mixtures(allmix, models, K_SAMPLES, SEED)
        mea = {s: (r["cyclic_mol_per_kg"][0], r["q_reb_kj_per_mol"][0]) for s, r in res.items()}
        res = {s: {key: v[1:] for key, v in r.items()} for s, r in res.items()}
        batch = batch.take(slice(1, None))
        df, scores = summarise(mixes, res, batch, mea, q_disc)
        print(f"  {tag}: {len(mixes)} mixtures x {K_SAMPLES} samples in {time.time() - t:.0f}s")
        raw = {s: (r["cyclic_mol_per_kg"].astype(np.float32), r["q_reb_gj_per_t"].astype(np.float32))
               for s, r in res.items()}
        return df, scores, raw

    print("Stage Y (yellow + reference)")
    df_y, sc_y, raw_y = run(yellow_and_reference(), "yellow/reference")

    print("Stage B1 (1 core + 1 partner)")
    df_b1, sc_b1, raw_b1 = run(blue_stage1(list(pmodels)), "blue stage 1")

    df_b1["_mean_score"] = df_b1[[f"{s}_score_median" for s in SCENARIOS]].mean(axis=1)
    best_partner = (df_b1.groupby("partners")["_mean_score"].max()
                    .sort_values(ascending=False))
    # ternaries are only worth building from amines the lab can actually buy
    avail = load_availability()
    smiles = {p.name: p.smiles for p in partners}
    buyable = [n for n in best_partner.index if purchasable(smiles[n], avail)]
    stage2_partners = buyable[:N_STAGE2_PARTNERS]
    df_b1 = df_b1.drop(columns="_mean_score")
    print("  stage-2 partners:", ", ".join(stage2_partners))

    print("Stage B2 (ternary blue)")
    df_b2, sc_b2, raw_b2 = run(blue_stage2(stage2_partners), "blue stage 2")

    # Draws are keyed by amine name (common random numbers across batches), so the
    # per-sample score matrices of all stages can be stacked for top-N probabilities.
    df = pd.concat([df_y, df_b1, df_b2], ignore_index=True)
    all_scores = {s: np.vstack([sc_y[s], sc_b1[s], sc_b2[s]]) for s in SCENARIOS}
    keep = ~df.duplicated(subset="composition").to_numpy()
    df = df[keep].reset_index(drop=True)
    all_scores = {s: v[keep] for s, v in all_scores.items()}
    samples = {}
    for s in SCENARIOS:
        samples[f"{s}_cyclic"] = np.vstack([raw_y[s][0], raw_b1[s][0], raw_b2[s][0]])[keep]
        samples[f"{s}_q_reb"] = np.vstack([raw_y[s][1], raw_b1[s][1], raw_b2[s][1]])[keep]
    df["_row"] = np.arange(len(df))
    both = 0.5 * (all_scores["cement"] + all_scores["coal"])
    for n in TOP_N:
        df[f"p_top{n}"] = top_n_probability(both, n)
    for s in SCENARIOS:
        df[f"{s}_rank"] = df[f"{s}_score_median"].rank(ascending=False, method="min").astype(int)
    df["score_both"] = df[[f"{s}_score_median" for s in SCENARIOS]].mean(axis=1)
    df["rank_both"] = df["score_both"].rank(ascending=False, method="min").astype(int)
    df["robust_score"] = df[[f"{s}_score_lo90" for s in SCENARIOS]].mean(axis=1)
    df["rank_robust"] = df["robust_score"].rank(ascending=False, method="min").astype(int)
    df = df.sort_values("rank_both").reset_index(drop=True)
    samples = {k: v[df["_row"].to_numpy()] for k, v in samples.items()}
    df = df.drop(columns="_row")
    df["rank_in_color"] = df.groupby("color")["score_both"].rank(ascending=False, method="first").astype(int)
    df["diverse_rank"] = diverse_ranks(df)
    df["diverse_rank_in_color"] = 0
    for color, g in df.groupby("color"):
        df.loc[g.index, "diverse_rank_in_color"] = diverse_ranks(g)
    df.insert(0, "mixture_id", [f"MX{i:05d}" for i in range(len(df))])

    # partner metadata
    pinfo = pd.DataFrame([{
        "name": p.name, "smiles": p.smiles, "origin": p.origin, "mw": p.mw,
        "pka1": p.pka1, "pka1_sd": p.pka1_sd, "n_sites": len(p.site_classes),
        "site_classes": ",".join(p.site_classes),
        "site_pkas": ",".join(f"{x:.2f}" for x in p.site_pkas),
        "stage2": p.name in stage2_partners, "calibrated_on_co2_data": p.name in calibrated,
        **p.props} for p in partners])
    origin = dict(zip(pinfo.name, pinfo.origin))
    df["partner_origin"] = df["partners"].map(
        lambda s: "|".join(origin[x] for x in s.split("|")) if s else "")

    df.to_csv(OUT / "mixtures_ranked.csv", index=False)
    np.savez_compressed(OUT / "mc_samples.npz", mixture_id=df["mixture_id"].to_numpy(dtype="U8"), **samples)
    pinfo.to_csv(OUT / "partners.csv", index=False)
    meta = {
        "total_wt_pct": TOTAL_WT, "yellow_step": YELLOW_STEP, "blue_step": BLUE_STEP,
        "mc_samples": K_SAMPLES, "seed": SEED, "scenarios": SCENARIOS, "process": PROCESS,
        "loading_discrepancy_q90": q_disc, "partner_pool": pool_log,
        "stage2_partners": stage2_partners,
        "counts": df["color"].value_counts().to_dict(),
        "runtime_s": round(time.time() - t0, 1),
        "caveats": [
            "MDEA in blends: valued within -11 % (7/2 MDEA/PZ) .. +6 % (5/5) of Xu (2011) empirical fits relative to MEA; no measured 40 C MDEA+PZ capacity data yet; model-form sd on the MDEA concentration term covers the remaining ambiguity",
            "DETA, DEA and MPA are calibrated on direct CO2 data, but none above 353 K: the stripper at 393 K is an extrapolation",
            "PZ vs MEA checked like-for-like on measured data (Dugas 2009, held out; 40 C, 0.5-5 kPa): 8 m PZ 2.48x vs 2.57x measured, 7/2 MEA/PZ 1.59x vs 1.82x -- PZ and MEA+PZ mixtures are, if anything, slightly UNDER-valued vs MEA (the earlier 'PZ over-valued ~35 %' caveat came from Xu's empirical MEA fit, which over-states 7 m MEA capacity: 0.50 vs 0.30-0.33 measured)",
            "all other partners use literature or OPERA pKa + structure-class priors",
            "equilibrium short-cut process model: for ranking, not plant design",
            "this file ranks capacity + energy only; cost and physical factors are added by src/screening/practical.py",
        ],
    }
    (OUT / "run_meta.json").write_text(json.dumps(meta, indent=2, default=str))
    print(f"done in {time.time() - t0:.0f}s -> {OUT.relative_to(ROOT)}")
    print(df["color"].value_counts().to_string())


if __name__ == "__main__":
    main()
