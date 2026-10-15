**# Data sources / provenance ledger**

Log every source here before pulling rows into `data/raw/`. One entry per source, updated as sources are added.

**## Solubility / loading (α)**

- [~] **Piperazine solubility** — Sci Reports 2024, 517 points. DOI: 10.1038/s41598-024-73070-y
  - **Status:** Identified; 517-row databank not publicly downloadable. Paper states data are available from the corresponding author on reasonable request.
  - **Underlying literature:** See individual source entries below.

- [~] **Low-conc MEA/PZ/AMP/CESAR-1 solubility** — Francois et al. 2024, Results in Engineering 22, 102163. sciencedirect.com/science/article/pii/S2590123024004171
  - **Note (2026-10-15):** Tables 6-9 give T, *total* P, liquid mole fractions and the *amine* vapour fraction (y1/y2) -- **no CO2 partial pressure**, so they cannot calibrate a pCO2-loading model. Not used for calibration.

- [x] **MEA and MDEA pCO2-loading + MDEA heat of absorption** — NIST ThermoML, see the dedicated section *"MEA / MDEA — NIST ThermoML (added 2026-10-15)"* below.

- [x] **MEA low-pressure VLE (Aronu 2011) and MEA / PZ / MEA+PZ wetted-wall data (Dugas 2009)**: see the dedicated sections below.

- [x] **MDEA+PZ solubility review/compilation** — Barbieri, C.; Moioli, S. "Solubility Data of CO2 in the MDEA+PZ Solvent: A Review of Experimental Data, Setups, and Procedures." *J. Chem. Eng. Data* **2025**, 70, 4861–4879. DOI: [10.1021/acs.jced.5c00570](https://doi.org/10.1021/acs.jced.5c00570). Open access, CC-BY 4.0.
  - **Local copy:** `data/raw/bottger 2009.pdf` — *note: the file name is misleading; the PDF is this 2025 review, not Böttger et al. 2009.*
  - Contains only summary ranges (Tables 1–4) and plots, no raw data tables, so nothing was digitised from it. Used as a **map of ~20 MDEA+PZ VLE sources**; that map led to the Xu (2011) thesis below. Its Table 3 point count for Xu (33) matches our transcription.

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

### MEA / MDEA — NIST ThermoML (added 2026-10-15)

All files were downloaded from the NIST Thermodynamics Research Center ThermoML archive,
`https://trc.nist.gov/ThermoML/<DOI>.json`, into `data/raw/thermoml/` (gitignored; the ingestion
script re-downloads any missing file). Ingestion: `src/data/ingest_thermoml_mea_mdea.py` →
`data/interim/mea_mdea_vle_thermoml.csv`, `data/interim/mdea_enthalpy_arcis2008.csv`.
Licence: ThermoML data are published by NIST TRC from the cited journal articles; cite the
original articles below.

- **Status:** `[x]` — **MEA, used for calibration**
  - Wagner, M.; von Harbou, I.; Kim, J.; Ermatchkova, I.; Maurer, G.; Hasse, H. "Solubility of Carbon Dioxide in Aqueous Solutions of Monoethanolamine in the Low and High Gas Loading Regions." *J. Chem. Eng. Data* **2013**, 58, 883–895. DOI: [10.1021/je301030z](https://doi.org/10.1021/je301030z)
  - 15 and 30 mass% MEA (2.8–7.3 mol/kg), 313–393 K. Block 1 (112 pts): measured pCO2 → CO2 molality. Block 0 (54 pts, synthetic method): total pressure; pCO2 = P − x_w·p_sat,H2O(T). Calibration uses pCO2 ≤ 2000 kPa → 98 points.

- **Status:** `[x]` — **MDEA, used for calibration**
  - Leontiadis, K.; Tzimpilis, E.; Aslanidou, D.; Tsivintzelis, I. "Solubility of CO2 in 3-amino-1-propanol and in N-methyldiethanolamine aqueous solutions: Experimental investigation and correlation using the CPA equation of state." *Fluid Phase Equilib.* **2019**, 500, 112254. DOI: [10.1016/j.fluid.2019.112254](https://doi.org/10.1016/j.fluid.2019.112254)
    - 72 pts, 15.2 and 23.4 mass% MDEA, 298–333 K, pCO2 11–1341 kPa. **Labelling note:** ThermoML labels the property "mole fraction", but the values (0.26–1.18) are the loading in mol CO2 / mol MDEA; a CO2 mole fraction of these liquids cannot exceed ~0.03.
  - Dey, A.; Dash, S. K.; Mandal, B. "Equilibrium CO2 solubility and thermophysical properties of aqueous blends of 1-(2-aminoethyl) piperazine and N-methyldiethanolamine." *Fluid Phase Equilib.* **2018**, 463, 91–105. DOI: [10.1016/j.fluid.2018.01.030](https://doi.org/10.1016/j.fluid.2018.01.030)
    - Block 7 only: 9 pts, 30 mass% MDEA, 313.2 K, pCO2 1.6–182 kPa (same loading labelling as above). The AEP+MDEA blend VLE is not in the ThermoML record; its density / viscosity / surface-tension blocks are kept for the later physical-properties stage.
  - **Limitation:** no MDEA data above 333 K in this set, so MDEA's temperature dependence (key for the 393 K stripper) rests on the protonation-enthalpy prior, kept at literature grade (−34.9 ± 3 kJ/mol); validated by the calorimetry below.

- **Status:** `[x]` — **MDEA heat of absorption, used in the joint MDEA fit** (was held out until 2026-10-15; it is what rejected the heat-capacity variant, see LOG.md)
  - Arcis, H.; Rodier, L.; Ballerat-Busserolles, K.; Coxam, J.-Y. "Enthalpy of solution of CO2 in aqueous solutions of methyldiethanolamine at T = 322.5 K and pressure up to 5 MPa." *J. Chem. Thermodyn.* **2008**, 40, 1022–1029. DOI: [10.1016/j.jct.2008.01.028](https://doi.org/10.1016/j.jct.2008.01.028)
  - 32 flow-calorimetry points, 15 and 30 mass% MDEA, all at or beyond CO2 saturation (integral enthalpy per mol CO2 fed). Model MAE 1.4 kJ/mol.

- **Status:** `[x]` (stored, not yet used) — **MDEA viscosity, for the later physical-factors stage**
  - Bernal-García, J. M.; Galicia-Luna, L. A.; Hall, K. R.; Ramos-Estrada, M.; Iglesias-Silva, G. A. "Viscosities for Aqueous Solutions of N-Methyldiethanolamine from 313.15 to 363.15 K." *J. Chem. Eng. Data* **2004**, 49, 864–866. DOI: [10.1021/je0302250](https://doi.org/10.1021/je0302250)

- **Checked and NOT usable** (recorded so nobody re-tries them):
  - Not in ThermoML (HTTP 404): Ma'mun et al. 2005 (10.1021/je0496490); Park & Sandall 2001 (10.1021/je000190t); Rho et al. 1997 (10.1021/je970097d); Sidi-Boumedine et al. 2004 (10.1016/j.fluid.2003.11.014); Mathonat et al. 1997 (10.1016/S0378-3812(97)00182-9); Ermatchkov et al. 2006 IECR (10.1021/ie0604270); Ermatchkov & Maurer 2011 (10.1016/j.fluid.2010.06.001). Ma'mun 2005 (30% MEA / 50% MDEA) and Jou, Mather & Otto (1982, 1995) remain good targets if the PDFs can be obtained and tabulated by hand.
  - In ThermoML but only densities, no CO2 solubility: Böttger et al. 2009 (10.1021/je900083k) and Speyer et al. 2010 (10.1021/je9003383), MDEA+PZ. The MDEA+PZ VLE tables in these papers would be an excellent second held-out blend test if transcribed from the PDFs.
  - Cheng et al. 2010 (10.1016/j.jct.2009.09.005): MDEA block lacks the MDEA concentration.
  - Zoghi et al. 2013 (10.1016/j.jct.2013.08.002), Mokraoui et al. 2014 (10.1021/je500130j): no MDEA–CO2 VLE in the record.

### MDEA + PZ blend VLE at stripper temperatures — Xu (2011) PhD thesis (added 2026-10-15)

- **Status:** `[x]` — **used in the joint MDEA calibration** (first used held out: it exposed a +0.073 mol/mol-alkalinity bias at 100–160 °C). Generalisation checked leave-one-blend-out (MAE 0.037 / 0.014). Table 2-12 capacity and heat values are used as benchmarks in `calibrate.py`.
- Xu, Q. "Thermodynamics of CO2 Loaded Aqueous Amines." PhD Dissertation, The University of Texas at Austin, **2011** (supervisor G. T. Rochelle). Open copy hosted by the Rochelle group: https://sites.utexas.edu/rochelle/wp-content/uploads/sites/3310/2015/02/Xu-2011-Thermodynamics-of-CO2-Loaded-Aqueous-Amines.pdf
- **Local copy:** `data/raw/xu_2011_thesis/` (gitignored). **Ingestion:** `src/data/ingest_xu2011_mdea_pz.py` holds a verbatim transcription of Tables 2-8 and 2-9 (each of the 33 rows checked programmatically against the PDF text) → `data/interim/mdea_pz_xu2011.csv`.
- Table 2-8: 7 m MDEA / 2 m PZ, 20 points; Table 2-9: 5 m MDEA / 5 m PZ, 13 points; 100–160 °C, pCO2 78–2477 kPa (calibration-style cap at 2000 kPa applies). In the thesis "Amine m" is total alkalinity and loading is per mol alkalinity; the script converts to MDEA / PZ molalities using the 7:2 and 5:5 mole ratios.
- Table 2-12 of the same thesis (heat of absorption and cyclic capacity for 7 m MEA, 8 m PZ, 7/2 and 5/5 MDEA/PZ; from Xu's empirical fits to measured VLE) → `XU_CAPACITY` / `XU_HEAT` benchmarks in `src/thermo/calibrate.py`.

### MEA low-pressure VLE — Aronu et al. (2011) (added 2026-10-15)

- **Status:** `[x]` — **used in the MEA calibration** (together with Wagner 2013).
- Aronu, U. E.; Gondal, S.; Hessen, E. T.; Haug-Warberg, T.; Hartono, A.; Hoff, K. A.; Svendsen, H. F. "Solubility of CO2 in 15, 30, 45 and 60 mass% MEA from 40 to 120 °C and model representation using the extended UNIQUAC framework." *Chem. Eng. Sci.* **2011**, 66, 6393–6406. DOI: [10.1016/j.ces.2011.08.042](https://doi.org/10.1016/j.ces.2011.08.042)
- **Local copy:** `data/raw/aronu2011.pdf` (gitignored; supplied by the user, identity confirmed from the PDF's title page and DOI). **Ingestion:** `src/data/ingest_aronu2011_mea.py` → `data/interim/mea_aronu2011.csv`; every column checked programmatically against the pdftotext output (276 numbers).
- Used: Tables 3–6, 40 / 60 / 80 °C, low-temperature apparatus with **measured** pCO2 (IR analyser): 138 points, 15/30/45/60 mass% MEA (2.9–24.6 m), pCO2 0.0007–19 kPa.
- Not used: the 60–120 °C total-pressure columns. Their printed pCO2 is the authors' e-UNIQUAC *model* value (fitting to it would be circular), and Ptot → pCO2 at 45–60 mass% MEA needs water/MEA activities. Wagner (2013) already covers the stripper side.

### MEA, PZ and MEA+PZ — Dugas (2009) PhD thesis (added 2026-10-15)

- **Status:** `[x]` — **held out** (never fitted). It is the like-for-like capacity benchmark (MEA and PZ measured in the same apparatus) and a held-out MEA+PZ blend test.
- Dugas, R. E. "Carbon Dioxide Absorption, Desorption, and Diffusion in Aqueous Piperazine and Monoethanolamine." PhD Dissertation, The University of Texas at Austin, **2009** (supervisor G. T. Rochelle). Open copy: https://sites.utexas.edu/rochelle/wp-content/uploads/sites/3310/2015/02/Dugas-2009-Carbon-Dioxide-Absorption-Desorption-and-Diffusion-in-Aqueous-Piperazine-and-Monoethanolamine.pdf (repository record: https://tdl-ir.tdl.org/items/f3f9b496-117d-4fa2-90fa-bee493493a12)
- **Local copy:** `data/raw/dugas_2009_thesis/` (gitignored). **Ingestion:** `src/data/ingest_dugas2009_mea_pz.py` → `data/interim/dugas2009_wwc.csv`; all 210 numbers checked against the PDF text.
- Table 4.4: 7/9/11/13 m MEA (50 pts); Table 4.5: 2/5/8/12 m PZ (43 pts); Table 4.6: 7 m MEA / 2 m PZ (12 pts); 40–100 °C, P*CO2 0.01–39 kPa. Wetted-wall column (P* bracketed by absorption/desorption at six inlet pressures, interpolated to zero flux). Loading is per mol alkalinity.

### Checked for the MEA capacity question, not used (2026-10-15)

- **Xu (2011) Table 2-12 MEA capacity (0.50 mol/kg) — retired as an MEA benchmark.** It comes from Xu's Table 2-10 empirical correlation ln P(Pa) = 38.6 − 12379/T − 16.0α² + 3556α/T + 8702α²/T, which has no concentration dependence and was regressed over 2.9–24.6 m MEA and 40–150 °C (Xu's own data plus Jou 1995, Hilliard 2008, Dugas 2008, Ma'mun 2005, Aronu 2011). At 40 °C it reads 7 m MEA 0.01–0.03 mol/mol too high. Its slope from 0.5 to 5 kPa is 0.101 per decade, against 0.061–0.067 measured, so its capacity of 0.50 mol/kg is about 50 % above the measured 0.30–0.33 (Aronu, Wagner, Dugas). Xu's MDEA/PZ entries are still reported in `calibrate.py`, as ratios to his own MEA value.
- **Hilliard (2008) PhD thesis**, UT Austin, "A Predictive Thermodynamic Model for an Aqueous Blend of Potassium Carbonate, Piperazine, and Monoethanolamine for Carbon Dioxide Capture from Flue Gas." Open copy: https://sites.utexas.edu/rochelle/wp-content/uploads/sites/3310/2015/02/Hilliard-2008-A-Predictive-Thermodynamic-Model-for-an-Aqueous-Blend-of-Potassium-Carbonate-Piperazine-and-Monoethanolamine-for-Car.pdf. Downloaded to `data/raw/hilliard_2008_thesis/` and **not yet transcribed**. It has 3.5/7/11 m MEA and MEA/PZ VLE at 40–60 °C (FTIR equilibrium cell) and would be a fourth independent MEA set plus more MEA+PZ data if needed.
- Jou, Mather & Otto (1995, *Can. J. Chem. Eng.* 73, 140) is still not obtained (paywalled, not in ThermoML).

### MDEA + PZ sources checked and NOT usable yet (2026-10-15)
- Not in NIST ThermoML (HTTP 404): Derks et al. 2010 *J. Chem. Thermodyn.* 42, 151 (10.1016/j.jct.2009.07.025); Vahidi et al. 2009 *J. Chem. Thermodyn.* 41, 1272 (10.1016/j.jct.2009.05.017); Hosseini Jenab et al. 2005 *J. Chem. Eng. Data* 50, 583 (10.1021/je049666p); Najibi & Maleki 2013 *Fluid Phase Equilib.* 354, 298 (10.1016/j.fluid.2013.06.022); Ali & Aroua 2004 *Int. J. Thermophys.* 25, 1863 (10.1007/s10765-004-7740-7).
- In ThermoML but no blend data: Suleman et al. 2018 *Fluid Phase Equilib.* 463, 142 (10.1016/j.fluid.2018.02.016) — only 4 single-MDEA and 4 single-PZ points.
- Böttger et al. 2009 (10.1021/je900083k) and Speyer et al. 2010 (10.1021/je9003383): paywalled; ThermoML holds densities only. Speyer would add 149 low-loading points at 313–393 K if a copy becomes available (e.g. via the BITS library).
- Further open UT Austin theses with MDEA/PZ data (not yet pulled): Chen 2011 (https://tdl-ir.tdl.org/handle/2152/ETD-UT-2011-08-4312), Nguyen 2013, Li 2015, Du 2016.

