# Log

Format per session: date / shipped / blocked / next action.

---

**2026-08-24**
- Shipped: repo scaffolded (folders, environment.yml, README, LICENSE, data_sources.md); RDKit smoke test passing.
- Blocked: none.
- Next action: log 5+ data sources with real links in `data_sources.md`, then start pulling solubility rows into `data/raw/`.

**2026-09-17**
- Shipped: Neo4j graph (`amineco2uq` db) visualizing the existing VLE measurement data (Amine/System/Source/SourceTable/Measurement schema, `src/data/load_neo4j_graph.py`). Ingested a large personal research dump (`our data/`, gitignored) — unzipped in place, analyzed, and folded into the structured pipeline via three new ingestion scripts: `ingest_co2_chemical_solvents.py` (Zenodo dataset: 124-compound learning set + 945-compound screening library with OPERA descriptors and dG/CompRate labels), `ingest_blendco2_simulation.py` (176 simulated MEA/MDEA/AMP/PZ blend compositions, tagged `data_type=simulated`), `ingest_literature_blend_performance.py` (109-row tidy performance table + 12-row kinetics table extracted from NotebookLM-summarized literature — first regeneration-energy data in the project).
- Blocked: none, but flagged an open scope conflict — `BACKLOG.md` currently excludes amine blends and kinetics, while every new personal-data source (and `Our Amine combination details.docx`) is about blends and includes kinetics. Not resolved yet.
- Next action: decide on the blends/kinetics scope question; reload the Neo4j graph with the new candidate/blend data; verify the NotebookLM-extracted literature tables against their source PDFs before treating them as ground truth.

**2026-10-15**
- Scope decided (with ma'am): final deliverable = ranked list of amine **mixtures** to test in the lab (top 50/75/100, cut chosen after seeing the ranking). Yellow = mixtures of MEA/MDEA/PZ/AMP only; blue = >= 1 of those four + any other amine. Rank on cyclic capacity + regeneration energy first; cost, then corrosion/degradation/physical factors come later, in that order. Blends are now core scope (BACKLOG updated).
- Env: fresh `amine-co2-uq` conda env on this laptop (Miniforge). MKL's OpenMP layer is missing on Windows and crashed every LAPACK call -> `MKL_THREADING_LAYER=TBB` (env config var + `environment.yml` `variables:`). Neo4j rebuilt from the CSVs (`load_neo4j_graph.py`), nothing copied from the old laptop.
- Shipped: `src/thermo/` -- temperature-dependent Kent-Eisenberg-style equilibrium model (vectorised, ~200k solves/s) with species for carbamate / protonated carbamate / dicarbamate. MAP-calibrated on Hartono AMP (110 pts, MAE 0.028 mol/mol) and Ermatchkov PZ (52 pts, MAE 0.008); **AMP+PZ (Dash, 158 pts) held out** -> MAE 0.100 (priors) -> 0.052 (calibrated), systematic -0.05 bias = AMP/PZ synergy the single-amine model misses. Parameter-only 90 % intervals covered 30 %; conformalized quantile regression margin (+/-0.067 mol/mol) gives 92 % leave-group-out coverage.
- Shipped: `src/screening/` -- partner pool (8 literature + 448 library amines after CHNO / pKa >= 8 / BP >= 165 C / solubility filters; RDKit site classes, polyamine protonation order by max separation), short-cut reboiler duty (desorption + sensible + stripping steam), cement (20 kPa) and coal (13 kPa) scenarios, 48-sample Monte Carlo with common random numbers keyed by amine name, score vs 30 wt% MEA, P(top-N), diverse ranks. 23,075 mixtures in ~5 min. Figures in `reports/figures/`, shortlist in `reports/results/`, Neo4j yellow/blue graph via `load_neo4j_mixtures.py` + `reports/neo4j_mixtures.grass`.
- Findings: DETA-containing blue mixtures lead (best: PZ 5 % + DETA 25 %, P(top 50) = 0.77); best yellow = MEA 5 % + PZ 25 % (overall #37). PZ-rich, MDEA-poor is where yellow beats MEA. **No mixture beats MEA at its 90 % lower bound** -- uncertainty is as large as the differences, dominated by MEA/MDEA being uncalibrated.
- Found / fixed: `models/` and `results/` in .gitignore also hid `src/models/` and `reports/results/` (anchored now); Francois 2024 tables have no CO2 partial pressure (y1 = amine vapour fraction), so the RF baseline on `modeling_dataset.csv` was effectively predicting from water vapour pressure -- not a CO2 solubility model; legacy BlendCO2 `pz.py` blend numbers are hand-set anchors + hand-set interaction bonuses, not simulation.
- Blocked: **MEA and MDEA pCO2-loading data** (no calibration data in repo) -- their absolute regeneration numbers are off (MEA lean loading 0.09 vs ~0.2 in plants).
- Next action: get MEA (e.g. Aronu et al. 2011, J. Chem. Thermodyn.; Jou, Mather & Otto 1995) and MDEA (Jou, Mather & Otto 1982; Ma'mun et al. 2005) VLE data -> calibrate -> rerun; then add cost.
