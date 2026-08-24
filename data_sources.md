# Data sources / provenance ledger

Log every source here before pulling rows into `data/raw/`. One entry per source, updated as sources are added.

## Solubility / loading (α)

- [ ] **Piperazine solubility** — Sci Reports 2024, 517 points. DOI: 10.1038/s41598-024-73070-y
- [ ] **Low-conc MEA/PZ/AMP/CESAR-1 solubility** — 2024. sciencedirect.com/science/article/pii/S2590123024004171
- [ ] **MDEA+PZ solubility review/compilation** — Barbieri & Moioli 2025, J. Chem. Eng. Data. DOI: 10.1021/acs.jced.5c00570
- [ ] **HQNN-Amine / SAGE-Amine repos** — structures + reference property sets. github.com/hclim0213/HQNN-Amine, github.com/hclim0213/SAGE-Amine

## Regeneration energy / loop target (ΔH_abs or Cc)

- [ ] **AMP/PZ thermodynamics incl. heat of absorption + speciation** — Morlando, Hartono & Knuutila 2025, Digital Chemical Engineering. sciencedirect.com/science/article/pii/S2772656825000971
- [ ] **Mechanism-based Ca/Cc** — parallel-reaction-mechanism ML, Chem. Eng. Sci. 2025. sciencedirect.com/science/article/abs/pii/S000925092501228X

## σ-profile databases (free, no COSMOtherm needed)

- [ ] **VT-2005**, 1432 compounds — design.che.vt.edu
- [ ] **LVPP open σ-profile DB** — github.com/lvpp/sigma
- [ ] **CHAOS large-scale σ-profile DB (2026, JCIM)** — coverage-gap fallback

## Structures / general

- [ ] **PubChem / ChEMBL** — SMILES for candidate screening list
- [ ] **NIST ThermoData Engine** — thermophysical cross-checks

---
**Status key:** unchecked = identified, not yet pulled. Check off once ingested into `data/raw/` with a working ingestion script in `src/data/`.
