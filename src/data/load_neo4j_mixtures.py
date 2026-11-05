"""
Load the screened mixtures into Neo4j (same `amineco2uq` database as load_neo4j_graph.py).

Graph model (added on top of the existing VLE / candidate graph):

    (:Mixture:Yellow)      >= 2 of MEA / MDEA / PZ / AMP only
    (:Mixture:Blue)        >= 1 core amine + >= 1 partner amine
    (:Mixture:Reference)   single core amine at 30 wt% (benchmarks)
    (:Mixture:Shortlist)   extra label on the current top-N (default 100) by rank_both
    (:Mixture:LabList)     extra label on the lab lists: top-100 combined, top-50 yellow
                           and top-50 blue by running cost (rank_practical)

    (:Amine {smiles})-[:IN_MIXTURE {wt_pct}]->(:Mixture)
        Amine nodes are MERGEd on canonical SMILES, so they are the same nodes the VLE
        and candidate-library loaders created; role = core | partner is set on them.
    (:Mixture)-[:SCORED_IN {rank, score, cyclic, q_reb, ...}]->(:Scenario {name})

Every run deletes all :Mixture nodes first, so the graph always matches the latest
data/processed/screening/mixtures_practical.csv.

Colours: drag reports/neo4j_mixtures.grass onto the Neo4j Browser window
(yellow = core-only mixtures, blue = mixtures with other amines).

Run:  python -m src.data.load_neo4j_mixtures [--shortlist 100] [--max-blue 5000]
"""

from __future__ import annotations

import argparse
import math
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from neo4j import GraphDatabase
from rdkit import Chem

from src.screening.process import SCENARIOS
from src.thermo.chemistry import CORE_NAMES, core_amines

ROOT = Path(__file__).resolve().parents[2]
SCREEN = ROOT / "data" / "processed" / "screening"
load_dotenv(ROOT / ".env")

BATCH = 2000
SCENARIO_FIELDS = ["rank", "score", "score_median", "score_lo90", "score_hi90", "cyclic",
                   "cyclic_lo90", "cyclic_hi90", "q_reb", "q_reb_lo90", "q_reb_hi90",
                   "rich_loading", "lean_loading", "dH_abs_40C", "p_beats_mea"]


def canon(smi):
    mol = Chem.MolFromSmiles(smi)
    return Chem.MolToSmiles(mol) if mol else None


def clean(v):
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return v


def as_rank(v):
    return None if pd.isna(v) or v == "" else int(float(v))


def short_label(row, names):
    parts = []
    for n in CORE_NAMES:
        if row[f"wt_{n}"] > 0:
            parts.append(f"{n}{row[f'wt_{n}']:g}")
    if row["partners"]:
        for p, w in zip(row["partners"].split("|"), row["partner_wt"].split("|")):
            parts.append(f"{names.get(p, p)}{w}")
    return "/".join(parts)


def build_rows(df, pinfo):
    smiles = {n: canon(m.smiles) for n, m in core_amines().items()}
    smiles.update({r.name: canon(r.smiles) for r in pinfo.itertuples()})
    names = {r.name: r.name for r in pinfo.itertuples()}
    rows = []
    for r in df.to_dict("records"):
        comps = [{"smiles": smiles[n], "code": n, "wt": float(r[f"wt_{n}"])}
                 for n in CORE_NAMES if r[f"wt_{n}"] > 0]
        if r["partners"]:
            for p, w in zip(r["partners"].split("|"), r["partner_wt"].split("|")):
                comps.append({"smiles": smiles[p], "code": p, "wt": float(w)})
        props = {
            "id": r["mixture_id"], "composition": r["composition"],
            "label": short_label(r, names), "color": r["color"],
            "n_components": int(r["n_components"]), "rank_both": int(r["rank_both"]),
            "score_both": clean(r["score_both"]), "rank_robust": int(r["rank_robust"]),
            "robust_score": clean(r["robust_score"]),
            "rank_in_color": int(r["rank_in_color"]),
            "diverse_rank": int(r["diverse_rank"]),
            "diverse_rank_in_color": int(r["diverse_rank_in_color"]),
            "partner_origin": r.get("partner_origin") or None,
            "practical_ok": str(r["practical_ok"]) == "True",
            "excluded_because": r["excluded_because"] or None,
            "warnings": r["warnings"] or None,
            "rank_practical": as_rank(r["rank_practical"]),
            "rank_practical_in_color": as_rank(r["rank_practical_in_color"]),
            "cost_usd_per_t": clean(r["cost_both"]), "saving_vs_mea": clean(r["saving_vs_mea"]),
            "p_cheaper_than_mea": clean(r["p_cheaper_than_mea"]),
            "corrosion_index": clean(r["corrosion_index"]),
            "oxidation_index": clean(r["oxidation_index"]),
            "rich_viscosity_mpas": clean(r["mu_rich_mpas"]),
        }
        for k in r:
            if k.startswith("p_top"):
                props[k] = clean(r[k])
        scored = []
        for s in SCENARIOS:
            scored.append({"scenario": s, **{f: clean(r.get(f"{s}_{f}")) for f in SCENARIO_FIELDS}})
            props[f"{s}_cyclic"] = clean(r[f"{s}_cyclic"])
            props[f"{s}_q_reb"] = clean(r[f"{s}_q_reb"])
            props[f"{s}_rank"] = int(r[f"{s}_rank"])
        rows.append({"props": props, "components": comps, "scored": scored})
    return rows


def run_batches(session, query, rows, **params):
    for i in range(0, len(rows), BATCH):
        session.run(query, rows=rows[i:i + BATCH], **params).consume()


Q_MIXTURE = """
UNWIND $rows AS row
CREATE (m:Mixture:%s)
SET m = row.props
"""

Q_COMPONENTS = """
UNWIND $rows AS row
MATCH (m:Mixture {id: row.props.id})
UNWIND row.components AS c
MERGE (a:Amine {smiles: c.smiles})
ON CREATE SET a.name = c.code
MERGE (a)-[:IN_MIXTURE {wt_pct: c.wt}]->(m)
"""

Q_SCORED = """
UNWIND $rows AS row
MATCH (m:Mixture {id: row.props.id})
UNWIND row.scored AS s
MATCH (sc:Scenario {name: s.scenario})
CREATE (m)-[r:SCORED_IN]->(sc)
SET r = s
REMOVE r.scenario
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shortlist", type=int, default=100)
    ap.add_argument("--max-blue", type=int, default=5000,
                    help="load only the best N blue mixtures (all yellow are loaded)")
    args = ap.parse_args()

    df = pd.read_csv(SCREEN / "mixtures_practical.csv", keep_default_na=False,
                     na_values=["", "nan"], low_memory=False)
    for col in ("partners", "partner_wt", "excluded_because", "warnings"):
        df[col] = df[col].fillna("").astype(str)
    pinfo = pd.read_csv(SCREEN / "partners.csv")
    # keep the blue mixtures that are best on either ranking, so every lab-list entry is loaded
    practical = pd.to_numeric(df["rank_practical"], errors="coerce")
    blue = df[(df.color == "blue") & ((df["rank_both"] <= args.max_blue) | (practical <= args.max_blue))]
    df = pd.concat([df[df.color != "blue"], blue]).sort_values("rank_both")
    rows = build_rows(df, pinfo)

    driver = GraphDatabase.driver(os.environ["NEO4J_URI"],
                                  auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]))
    with driver.session(database=os.environ.get("NEO4J_DATABASE", "neo4j")) as s:
        s.run("CREATE CONSTRAINT mixture_id IF NOT EXISTS FOR (m:Mixture) REQUIRE m.id IS UNIQUE").consume()
        s.run("CREATE CONSTRAINT amine_smiles IF NOT EXISTS FOR (a:Amine) REQUIRE a.smiles IS UNIQUE").consume()
        s.run("MATCH (m:Mixture) DETACH DELETE m").consume()
        s.run("MATCH (sc:Scenario) DETACH DELETE sc").consume()
        for name, sc in SCENARIOS.items():
            s.run("CREATE (:Scenario {name: $name, label: $label, T_abs_C: $Ta, p_feed_kPa: $pf, "
                  "T_strip_C: $Ts, p_lean_kPa: $pl})", name=name, label=sc["label"],
                  Ta=sc["T_abs"] - 273.15, pf=sc["p_feed"], Ts=sc["T_strip"] - 273.15,
                  pl=sc["p_lean"]).consume()

        for color, label in (("yellow", "Yellow"), ("blue", "Blue"), ("reference", "Reference")):
            part = [r for r in rows if r["props"]["color"] == color]
            run_batches(s, Q_MIXTURE % label, part)
        run_batches(s, Q_COMPONENTS, rows)
        run_batches(s, Q_SCORED, rows)
        s.run("MATCH (m:Mixture) WHERE m.rank_both <= $n SET m:Shortlist", n=args.shortlist).consume()
        s.run("MATCH (m:Mixture) WHERE m.rank_practical <= 100 OR "
              "(m.color IN ['yellow', 'blue'] AND m.rank_practical_in_color <= 50) "
              "SET m:LabList").consume()

        # roles + readable names on amine nodes
        core = [{"smiles": canon(m.smiles), "code": n} for n, m in core_amines().items()]
        s.run("UNWIND $rows AS r MATCH (a:Amine {smiles: r.smiles}) "
              "SET a.role = 'core', a.name = r.code, a:Core", rows=core).consume()
        names = pd.read_csv(SCREEN / "amines_practical.csv").set_index("name")["chem_name"].to_dict()
        prow = [{"smiles": canon(r.smiles), "code": r.name, "origin": r.origin,
                 "pka1": float(r.pka1), "sites": r.site_classes,
                 "chem_name": names[r.name] if isinstance(names.get(r.name), str) else None}
                for r in pinfo.itertuples()]
        run_batches(s, "UNWIND $rows AS r MATCH (a:Amine {smiles: r.smiles}) "
                       "WHERE (a)-[:IN_MIXTURE]->() "
                       "SET a.role = 'partner', a.partner_code = r.code, "
                       "a.name = coalesce(a.name, r.code), a.partner_origin = r.origin, "
                       "a.pka1_model = r.pka1, a.site_classes = r.sites, a.chem_name = r.chem_name, "
                       "a:Partner", prow)

        counts = s.run("MATCH (m:Mixture) RETURN m.color AS c, count(*) AS n ORDER BY c").data()
        short = s.run("MATCH (m:Shortlist) RETURN m.color AS c, count(*) AS n ORDER BY c").data()
        lab = s.run("MATCH (m:LabList) RETURN m.color AS c, count(*) AS n ORDER BY c").data()
    driver.close()
    print("mixtures loaded:", {r["c"]: r["n"] for r in counts})
    print(f"shortlist (top {args.shortlist}):", {r["c"]: r["n"] for r in short})
    print("lab lists:", {r["c"]: r["n"] for r in lab})


if __name__ == "__main__":
    main()
