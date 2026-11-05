# Backlog — explicitly out of scope this semester

New ideas go here, not into the current sprint. Scope is a contract.

## Cut from core scope (this semester)
- Absorption kinetics as a modeled target
- Degradation / toxicity as a modeled target (degradation enters the cost as literature indices, not a model)
- ~~Amine blends — pure amines only for now~~ **moved INTO core scope 2026-10-15** (ma'am: final output is a ranked list of mixtures to test)
- Novel-amine σ-profile QM (running COSMOtherm/DFT ourselves) — restrict to covered amines only
- Screening vs. optimization as competing framings — this project screens/ranks candidate amines, not operating-condition optimization
- Wet-lab or process-simulation validation of top candidates

## Parked 2026-11-05 (finish the lab lists first)
- Active-learning-guided screening
- Aleatoric / epistemic uncertainty decomposition
- ML property models (the old random-forest baseline was removed: its features had no CO2 partial pressure)
- HQNN comparison and deeper quantum ablation
- Generative (SAGE-style) candidate design

## Done
- ~~Cost of the mixture~~ and ~~corrosion, degradation, viscosity, volatility, PZ precipitation~~: `src/screening/practical.py` (2026-11-05)

## Model improvements worth doing next
- DETA + PZ blend VLE and the 333 K points (Chang 2013 tables; the ThermoML record omits them)
- DETA above 353 K (Hartono 2009 thesis / 2011 Energy Procedia paper) so the stripper end stops being an extrapolation
- MEA + PZ blend term: fit on Hilliard (2008) so Dugas (2009) stays held out
- AMP + PZ interaction (systematic -0.05 mol/mol bias, currently covered by the conformal margin)
- MDEA + PZ at 40 °C (Speyer 2010, via the BITS library)
- Real supplier quotes in place of market-index and assumed prices
