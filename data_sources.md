**# Data sources / provenance ledger**

Log every source here before pulling rows into `data/raw/`. One entry per source, updated as sources are added.

**## Solubility / loading (α)**

- [~] **Piperazine solubility** — Sci Reports 2024, 517 points. DOI: 10.1038/s41598-024-73070-y
  - **Status:** Identified; 517-row databank not publicly downloadable. Paper states data are available from the corresponding author on reasonable request.
  - **Underlying literature:** See individual source entries below.

- [~] **Low-conc MEA/PZ/AMP/CESAR-1 solubility** — Francois et al. 2024, Results in Engineering 22, 102163. sciencedirect.com/science/article/pii/S2590123024004171
  - **Note (2026-10-15):** Tables 6-9 give T, *total* P, liquid mole fractions and the *amine* vapour fraction (y1/y2) -- **no CO2 partial pressure**, so they cannot calibrate a pCO2-loading model. Not used for calibration.

- [ ] **NEEDED: MEA pCO2-loading data (30 wt%, 40-120 C)** — e.g. Aronu et al. 2011 (J. Chem. Thermodyn., likely in NIST ThermoML); Jou, Mather & Otto 1995 (Can. J. Chem. Eng.)
- [ ] **NEEDED: MDEA pCO2-loading data** — e.g. Jou, Mather & Otto 1982 (Ind. Eng. Chem. Process Des. Dev.); Ma'mun et al. 2005

- [ ] **MDEA+PZ solubility review/compilation** — Barbieri & Moioli 2025, J. Chem. Eng. Data. DOI: 10.1021/acs.jced.5c00570

- [ ] **HQNN-Amine / SAGE-Amine repos** — structures + reference property sets. github.com/hclim0213/HQNN-Amine, github.com/hclim0213/SAGE-Amine

**## Regeneration energy / loop target (ΔH_abs or Cc)**

- [ ] **AMP/PZ thermodynamics incl. heat of absorption + speciation** — Morlando, Hartono & Knuutila 2025, Digital Chemical Engineering. sciencedirect.com/science/article/pii/S2772656825000971

- [ ] **Mechanism-based Ca/Cc** — parallel-reaction-mechanism ML, Chem. Eng. Sci. 2025. sciencedirect.com/science/article/abs/pii/S000925092501228X

**## σ-profile databases (free, no COSMOtherm needed)**

- [ ] **VT-2005**, 1432 compounds — design.che.vt.edu

- [ ] **LVPP open σ-profile DB** — github.com/lvpp/sigma

- [ ] **CHAOS large-scale σ-profile DB (2026, JCIM)** — coverage-gap fallback

**## Structures / general**

- [ ] **PubChem / ChEMBL** — SMILES for candidate screening list

- [ ] **NIST ThermoData Engine** — thermophysical cross-checks

---

**Status key:**  
- `[ ]` = identified, not yet pulled  
- `[~]` = identified, but original dataset unavailable; underlying source(s) being reconstructed  
- `[x]` = pulled into `data/raw/` and has a working ingestion script in `src/data/`

**### PZ — Ermatchkov et al. (2006)**

- **Status:** `[x]`
- **Source:** Ermatchkov, V.; Kamps, A. P.-S.; Speyer, D.; Maurer, G.
- **Title:** Solubility of Carbon Dioxide in Aqueous Solutions of Piperazine in the Low Gas Loading Region
- **DOI:** 10.1021/je0601917
- **Public data representation:** NIST ThermoML JSON
- **Raw file:** `data/raw/piperazine_ermatchkov_2006.json`
- **Ingestion:** `src/data/ingest_piperazine.py`
- **Output:** `data/interim/piperazine_ermatchkov_2006.csv`
- **Rows:** 52
- **Amine:** PZ
- **SMILES:** `C1CNCCN1`
- **Temperature:** K
- **PZ concentration:** mol/kg water (molality)
- **CO₂ pressure:** kPa
- **Target:** CO₂ loading, mol CO₂/mol PZ
- **License:** Not specified by the source
- **Provenance:** Original experimental source represented through NIST ThermoML

---

### Candidate amines — CO2_chemical_solvents (Zenodo, badge 430190456)

- **Status:** `[x]`
- **Title:** "Design of new chemical solvents for CO2 absorption using a combination of molecular simulations and machine learning"
- **DOI:** Zenodo badge 430190456 — exact DOI/author list not yet confirmed; verify at zenodo.org before citing in any writeup.
- **Local copy:** `our data/Amine_Earlier work/CO2_chemical_solvents-main/` (NOT copied into `data/raw/` — repo is ~500MB with 193x duplicated ISIDA-fragment-descriptor files; the ingestion script reads directly from `our data/`, which is gitignored)
- **Ingestion:** `src/data/ingest_co2_chemical_solvents.py`
- **Outputs:**
  - `data/processed/structured/candidate_amines_learning_set.csv` — 124 unique amines, MD-computed `CompRate_ylog` (kinetics — out of scope per BACKLOG.md, kept for completeness) and `dG_MD_ylog` (CO2 binding free energy — relevant to regeneration energy), plus 33 OPERA physicochemical descriptors (SMILES-derived: MolWeight, LogP, pKa, BP, etc.)
  - `data/processed/structured/candidate_amines_screening_library.csv` — 945 candidate amines with the same OPERA descriptors, plus the repo's own RF-ensemble predictions for CompRate/dG (`comprate_avg_pred`, `dg_avg_pred`) and my own ensemble-std columns (`comprate_rf_ensemble_std`, `dg_rf_ensemble_std`) as a ready-made epistemic-uncertainty signal. 124 of the 945 rows carry real ground truth (`RMD`, `dGMD`) — sourced from `100MDamines` (100 rows) and `Chowdhury` (24 rows, matches `chowdhury-et-al-2013...pdf` in the same data dump).
- **Why this matters:** fixes the chemical-diversity gap (3 amines → hundreds) for candidate screening; the ensemble-std columns double as a UQ baseline to compare our own conformal intervals against.

### Simulated blends — BlendCO2 in-house equilibrium solver

- **Status:** `[x]` (data type: **simulated, not experimental**)
- **Local copy:** `our data/Amine_Earlier work/BlendCO2 3/BlendCO2/all_blends_ranked.csv`
- **Ingestion:** `src/data/ingest_blendco2_simulation.py`
- **Output:** `data/processed/structured/blendco2_simulated_blends.csv` — 176 single/binary/ternary MEA/MDEA/AMP/PZ blend compositions ranked by `cyclic_capacity` and cost.
- **Caveat:** the solver's physics module (`equilibrium_solver.py`) is missing from both local copies of this project — only a compiled `.pyc` remains — so its assumptions are currently unauditable. Every row carries a `data_type=simulated` tag; do not merge into the same UQ-calibration pool as real experimental measurements without preserving that tag.

### Literature blend performance — NotebookLM-extracted tables

- **Status:** `[~]` (extracted by an AI summarization tool from PDFs, not hand-transcribed — needs verification against source PDFs before being trusted as ground truth)
- **Sources (see `References_Amine/` next to the originals):** 2026_Wang (ternary amine blends), 2025_Gupta (novel CO2 capture blend), 2025_Liang (bicarbonate pathways in blends), an AEP/DMEA thermodynamic-modeling paper, and an unlabeled "Source_1" behind the MEA/MDEA/AMP/PZ kinetics table.
- **Local copies:** three `.xlsx` + one `.docx` under `our data/Amine_Earlier work/Amine Blends_Computations_NotebookLM/`
- **Ingestion:** `src/data/ingest_literature_blend_performance.py`
- **Outputs:**
  - `data/processed/structured/literature_blend_performance.csv` — 109 rows, tidy long format (`blend_label, metric, value, value_min, value_max, raw_text, source_reference`). Left in long format deliberately: source units are heterogeneous (mol/mol vs mol/kg vs mol/L vs GJ/t CO2 vs kJ/mol) and converting them would require density/molar-mass assumptions not given in the sources.
  - `data/processed/structured/literature_blend_kinetics.csv` — 12 rows, MEA/MDEA/AMP/PZ/DEA blend absorption **rate** data (kinetics — out of scope per BACKLOG.md, kept separate rather than silently mixed into the performance table).
- **First real regeneration-energy data in this project** (`Heat of Absorption`, `Regeneration Efficiency`, `Regeneration Heat Duty (GJ/t CO2)` metrics) — previously zero rows existed for this target.