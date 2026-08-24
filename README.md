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

🚧 Early build. See `LOG.md` for session-by-session progress.

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

| Target | Model | Split | R² | MAE | Coverage (90% PI) |
|---|---|---|---|---|---|
| _TBD_ | | | | | |

## License

MIT — see `LICENSE`.
