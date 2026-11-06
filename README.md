# amine-co2-uq

Uncertainty-aware screening of amine mixtures for CO₂ capture: which blends are worth testing
in the lab, for cement and coal flue gas.

**Starting point:** HQNN-Amine (Cho, Kim, No & Lim, 2025) — [github.com/hclim0213/HQNN-Amine](https://github.com/hclim0213/HQNN-Amine)

## What this is

A calibrated equilibrium model predicts cyclic capacity and regeneration energy for about 23,000
mixtures at 30 wt% total amine, with Monte Carlo and conformal uncertainty. A practical stage then
adds amine price and physical factors, all as running cost in $ per tonne CO₂.

- **Yellow** = mixtures of MEA / MDEA / PZ / AMP only.
- **Blue** = at least one of those + another amine.

## Status

**Deliverable:** three lab lists in `reports/results/`, ordered by saving against 30 wt% MEA:
`lab_list_combined` (top 100), `lab_list_yellow` (top 50), `lab_list_blue` (top 50).
See `LOG.md` for session-by-session progress and `BACKLOG.md` for what is parked.

```
VLE, heat and viscosity data ──► src/thermo/calibrate.py ──► calibrated model (+ conformal margin)
                                                                       │
partner amines (src/screening/partners.py) ────────────────────────────┤
                                                                       ▼
                     src/screening/run_screen.py   (≈23k mixtures × 48 MC samples × 2 scenarios)
                                                                       │
prices, degradation, corrosion, viscosity, vendors ────────────────────┤
                                                                       ▼
                     src/screening/practical.py    ($ / t CO₂, practical filter, ranks)
                                                                       │
                ┌──────────────────────────────────────────────────────┼────────────────┐
     reports/figures/                                    reports/results/lab_list_*     Neo4j
```

## Repo layout

```
data/{raw,interim,processed}/   # raw is gitignored; interim tables are tracked, so NIST can be down
data/processed/practical/       # amine_inputs.csv: every price and index with its basis
src/data/                       # ingestion, verification, Neo4j loaders
src/thermo/                     # equilibrium model and calibration
src/screening/                  # partner pool, process model, screen, practical stage
src/viz/                        # figures and lab lists
tests/                          # sanity checks (python -m tests.test_practical)
reports/{results,figures}/      # lists, tables and figures
run_all.py                      # fresh clone -> lists and figures
environment.yml                 # pinned environment
data_sources.md                 # provenance ledger
```

## Setup

```bash
conda env create -f environment.yml
conda activate amine-co2-uq
python run_all.py
```

## Results

Lab lists (both scenarios, 30 wt% MEA = $20.7/t on this basis):

| List | Best mixture | Saving vs MEA, $/t [90 %] | P(cheaper than MEA) |
|---|---|---|---|
| Blue | PZ 25% + DEA 5% | +1.92 [-0.70, +5.34] | 0.92 |
| Yellow | MEA 2.5% + PZ 27.5% | +1.80 [-0.97, +5.31] | 0.92 |
| Reference | PZ 30% | +1.85 [-1.26, +5.70] | 0.85 |

- The leaders are PZ-rich and their differences are smaller than the uncertainty: read the top of each list as a group, not an exact order. The best yellow mixtures are effectively PZ alone.
- **Read the saving as about $0.8-1.9/t.** Calorimetry (Hilliard 2008) puts PZ's heat at 120 °C about 22 kJ/mol above the model, whose heat comes from VLE. Published CESAR1 : MEA energy ratios allow at most +7.7 kJ/mol: at that limit the same mixtures lead and PZ still saves $0.81/t. At the full calorimetric value PZ would cost $2.05/t more than MEA, but CESAR1 : MEA would then be 1.02, outside the reported 0.79-0.94. A measured PZ against MEA reboiler duty would settle this.
- 216 of the 20,475 mixtures that pass the practical filter are cheaper than MEA. Moving any assumption to the end of its range keeps at least 16 of each colour's top 20.
- **PZ-rich solvents need handling care.** Unloaded 30 wt% PZ solidifies below about 42 °C and 15 wt% below about 25 °C (measured for PZ + water); the lists give this per mixture.
- On capacity + energy alone, AMP 25% + 1-methyl-3-pyrrolidinol 5% leads, but at an assumed $30/kg for the partner it is not a cheap option. No mixture beats MEA at its 90 % lower bound in both scenarios.
- **DETA fell.** Direct data (Chang 2013) cut 30 wt% DETA's capacity from 2.9 to 1.55 mol/kg. The former #1, PZ 5% + DETA 25%, is now #4694 and slightly worse than MEA. See `reports/results/ranking_change_deta_dea_mpa.md`.

Model validation:

| Target | Model | Split | MAE | Coverage (90% PI) |
|---|---|---|---|---|
| CO₂ loading, MEA | calibrated equilibrium | fit (Wagner 2013 + Aronu 2011, 236 pts) | 0.014 mol/mol | – |
| CO₂ loading, MEA / PZ / MEA+PZ, 40–100 °C | calibrated equilibrium | **held out** (Dugas 2009, 50 / 43 / 12 pts) | 0.012 / 0.011 / 0.009 mol/mol alkalinity | MEA parameter-only 0.62 → 0.92 after inter-lab sd inflation (×2.25) |
| CO₂ loading, AMP | calibrated equilibrium | fit (Hartono 2020, 110 pts) | 0.028 mol/mol | – |
| CO₂ loading, PZ | calibrated equilibrium | fit (Ermatchkov 2006, 52 pts) | 0.008 mol/mol | – |
| CO₂ loading, MDEA | calibrated equilibrium | joint fit (Leontiadis 2019 + Dey 2018 + Xu 2011 MDEA+PZ, 112 pts; + Arcis 2008 heats) | 0.031 mol/mol; heats 1.8 kJ/mol | – |
| CO₂ loading, DETA | calibrated equilibrium | fit (Chang 2013, 84 pts); leave-one-concentration-out 0.02–0.06 | 0.029 mol/mol (old estimate: 0.44 vs 0.70 measured at 80 °C, 2 kPa) | – |
| CO₂ loading, DEA | calibrated equilibrium | fit (Ghalib 2016, 15 pts; + Arcis 2012 heats) | 0.015 mol/mol (estimate was 0.126) | – |
| CO₂ loading, MPA | calibrated equilibrium | fit (Leontiadis 2019, 60 pts) | 0.016 mol/mol (estimate was 0.047) | – |
| CO₂ loading, MEA / PZ / MEA+PZ, 40–60 °C | calibrated equilibrium | **held out** (Hilliard 2008, 55 / 62 / 41 pts) | 0.020 / 0.012 / 0.011 mol/mol N (MEA+PZ bias −0.001) | – |
| CO₂ loading, MDEA+PZ blends, 100–160 °C | calibrated equilibrium | **leave-one-blend-out** (Xu 2011) | 0.035 / 0.014 mol/mol alkalinity | 1.00 with conformal margin |
| CO₂ loading, AMP+PZ blend | calibrated equilibrium | **held out** (Dash 2011, 158 pts) | 0.052 mol/mol | 0.30 parameter-only → **0.92** with conformal margin |
| Capacity vs 7 m MEA (40 °C, 0.5→5 kPa), measured | calibrated equilibrium | like-for-like benchmark (Dugas 2009, held out) | 7 m MEA 0.338 vs 0.328 mol/kg; 8 m PZ 2.48× vs 2.57×; 7/2 MEA/PZ 1.59× vs 1.82× | – |
| Capacity vs 7 m MEA, MDEA/PZ | calibrated equilibrium | benchmark (Xu 2011 Table 2-12, empirical fits) | 7/2 MDEA/PZ 1.50× vs 1.68×; 5/5 2.08× vs 1.96× | – |
| Reboiler duty, CESAR1 : MEA | short-cut process model | benchmark (three studies) | 0.90–0.91 vs 0.79–0.94 reported | – |

Known limits:

- Absolute reboiler duty reads about 40 % low, so the practical stage scales it to a 30 wt% MEA duty of 3.7 GJ/t and keeps the ratios between solvents.
- DETA, DEA and MPA have no loading data above 353 K, so the 393 K stripper is an extrapolation.
- Wang (2026) measures DETA ternary capacities about 30 % above the model; those values also sit above Chang's pure-DETA data, so the laboratories disagree.
- DIPA, AEP and the library amines still use structure-based estimates. Those estimates were wrong for DETA, DEA and MPA, so treat them as provisional (the lists mark them `partner estimated`).
- Many prices, and the corrosion and viscosity cost scales, are assumptions: see `data/processed/practical/amine_inputs.csv` and `SCALARS` in `src/screening/practical.py`.
- Dugas's 7/2 MEA/PZ capacity is 13 % above the model, but Hilliard's MEA+PZ data show no bias, so no blend term was added. AMP+PZ keeps its −0.05 mol/mol bias, covered by the conformal margin.
- The practical stage is not a plant design: absorption rate, foaming and nitrosamine formation are not costed.

## Neo4j

```bash
python -m src.data.load_neo4j_graph       # experimental + candidate-amine graph
python -m src.data.load_neo4j_mixtures    # screened mixtures (Yellow / Blue / Reference, LabList)
```
Drag `reports/neo4j_mixtures.grass` onto Neo4j Browser for the yellow/blue colours, then run the
blocks in `reports/neo4j_mixtures_demo.cypher`.

## License

MIT — see `LICENSE`.
