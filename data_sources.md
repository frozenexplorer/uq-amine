**# Data sources / provenance ledger**

Log every source here before pulling rows into `data/raw/`. One entry per source, updated as sources are added.

**## Solubility / loading (α)**

- [~] **Piperazine solubility** — Sci Reports 2024, 517 points. DOI: 10.1038/s41598-024-73070-y
  - **Status:** Identified; 517-row databank not publicly downloadable. Paper states data are available from the corresponding author on reasonable request.
  - **Underlying literature:** See individual source entries below.

- [ ] **Low-conc MEA/PZ/AMP/CESAR-1 solubility** — 2024. sciencedirect.com/science/article/pii/S2590123024004171

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