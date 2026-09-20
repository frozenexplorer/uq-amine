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
