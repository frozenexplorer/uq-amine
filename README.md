# amine-co2-uq

Uncertainty-aware ML for identifying amine solvents across the CO₂ absorption–regeneration loop.

**Anchor paper:** HQNN-Amine (Cho, Kim, No & Lim, 2025) — [github.com/hclim0213/HQNN-Amine](https://github.com/hclim0213/HQNN-Amine)

## What this is

HQNN-Amine predicts five proxy physicochemical properties with a classical + quantum regressor.
This project predicts the actual loop quantities — **CO₂ solubility/loading** and **regeneration
energy (heat of absorption / cyclic capacity)** — with **calibrated uncertainty** (conformal
intervals, aleatoric/epistemic decomposition), and uses that uncertainty to drive **active-learning-guided
candidate screening**. Kinetics and degradation are scoped out this semester (see `BACKLOG.md`).

## Status

**Current deliverable:** a ranked, uncertainty-aware list of amine **mixtures** to test in the lab.
Yellow = mixtures of MEA / MDEA / PZ / AMP only; blue = at least one of those + another amine.
Ranked on cyclic capacity + regeneration energy (cost and corrosion/physical factors come next).
See `LOG.md` for session-by-session progress.

```
VLE data ──► src/thermo/calibrate.py ──► calibrated equilibrium model (+ conformal margin)
                                                │
partner amines (src/screening/partners.py) ─────┤
                                                ▼
              src/screening/run_screen.py  (≈23k mixtures × 48 MC samples × 2 scenarios)
                                                │
             ┌──────────────────────────────────┼───────────────────────────────┐
  reports/figures/screening/      reports/results/shortlist_top100.*     Neo4j (yellow/blue graph)
```

## Repo layout

```
data/{raw,interim,processed}/   # never edit raw; scripts only
src/{data,features,models,uq,eval,viz}/
notebooks/                      # exploration only; logic lives in src/
models/                         # saved checkpoints
reports/{results,figures}/      # results/*.md + publication figures
run_all.py                      # fresh clone -> key figures
environment.yml                 # locked env
data_sources.md                 # provenance ledger
```

## Setup

```bash
conda env create -f environment.yml
conda activate amine-co2-uq
python run_all.py
```

## Results

| Target | Model | Split | MAE | Coverage (90% PI) |
|---|---|---|---|---|
| CO₂ loading, MEA | calibrated equilibrium | fit (Wagner 2013 + Aronu 2011, 236 pts) | 0.014 mol/mol | – |
| CO₂ loading, MEA / PZ / MEA+PZ, 40–100 °C | calibrated equilibrium | **held out** (Dugas 2009, 50 / 43 / 12 pts) | 0.012 / 0.011 / 0.009 mol/mol alkalinity | MEA parameter-only 0.62 → 0.92 after inter-lab sd inflation (×2.25) |
| CO₂ loading, AMP | calibrated equilibrium | fit (Hartono 2020, 110 pts) | 0.028 mol/mol | – |
| CO₂ loading, PZ | calibrated equilibrium | fit (Ermatchkov 2006, 52 pts) | 0.008 mol/mol | – |
| CO₂ loading, MDEA | calibrated equilibrium | joint fit (Leontiadis 2019 + Dey 2018 + Xu 2011 MDEA+PZ, 112 pts; + Arcis 2008 heats) | 0.031 mol/mol; heats 1.7 kJ/mol | – |
| CO₂ loading, MDEA+PZ blends, 100–160 °C | calibrated equilibrium | **leave-one-blend-out** (Xu 2011) | 0.037 / 0.014 mol/mol alkalinity | 1.00 with conformal margin |
| CO₂ loading, AMP+PZ blend | calibrated equilibrium | **held out** (Dash 2011, 158 pts) | 0.052 mol/mol | 0.30 parameter-only → **0.92** with conformal margin |
| Capacity vs 7 m MEA (40 °C, 0.5→5 kPa), measured | calibrated equilibrium | like-for-like benchmark (Dugas 2009, held out) | 7 m MEA 0.338 vs 0.328 mol/kg; 8 m PZ 2.48× vs 2.57×; 7/2 MEA/PZ 1.59× vs 1.82× | – |
| Capacity vs 7 m MEA, MDEA/PZ | calibrated equilibrium | benchmark (Xu 2011 Table 2-12, empirical fits) | 7/2 MDEA/PZ 1.50× vs 1.68×; 5/5 2.08× vs 1.96× | – |

Screening (both scenarios, score vs 30 wt% MEA): best blue = PZ 5% + DETA 25%; best yellow = MEA 2.5% + PZ 27.5%
(overall #52; 6 yellow in the top 100). No mixture yet beats MEA at its conservative 90% lower bound.
Effect of the 2026-10-15 MEA recalibration: `reports/results/ranking_change_mea_recalibration.md`.
Known biases (absorber end, vs measured data): PZ and MEA+PZ are, if anything, slightly *under*-valued relative
to MEA (−4 % and −13 %); MDEA-rich blends are slightly under-valued. Xu's (2011) MEA capacity of 0.50 mol/kg,
which earlier suggested the opposite, comes from an empirical fit; measured 7 m MEA data give 0.30–0.33.

## Neo4j

```bash
python -m src.data.load_neo4j_graph       # experimental + candidate-amine graph
python -m src.data.load_neo4j_mixtures    # screened mixtures (Yellow / Blue / Reference labels)
```
Drag `reports/neo4j_mixtures.grass` onto Neo4j Browser for the yellow/blue colours, then run the
blocks in `reports/neo4j_mixtures_demo.cypher`.

## License

MIT — see `LICENSE`.
