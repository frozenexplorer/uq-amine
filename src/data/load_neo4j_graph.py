"""
Load all current structured datasets into the Neo4j graph
(amine-co2-uq DBMS, `amineco2uq` database) for visual exploration.

Graph model:
    (:Amine {smiles, name?, ...descriptors})-[:PART_OF]->(:System {name})
    (:Measurement)-[:MEASURED_IN]->(:System)
    (:Measurement)-[:FROM_TABLE]->(:SourceTable {id})-[:PART_OF]->(:Source {name, year})

    (:Amine)-[:IN_DATASET]->(:Dataset {name})
        -- candidate amines from the CO2_chemical_solvents Zenodo dataset

    (:Amine)-[:COMPONENT_OF {fraction}]->(:Blend {label, data_type})
    (:Blend)-[:FROM_TABLE]->(:SourceTable)-[:PART_OF]->(:Source)
        -- BlendCO2 in-house simulated blends (data_type="simulated")

    (:Blend)-[:REPORTED_METRIC {metric, value, value_min, value_max, raw_text}]->(:Source)
    (:Blend)-[:REPORTED_KINETICS {...}]->(:Source)
        -- NotebookLM-extracted literature blend tables (data_type="literature_ai_extracted")

Amine nodes are always MERGEd on canonical (RDKit) SMILES, never on name/code,
so the same molecule reported under different sources/labels collapses to one
node (e.g. MDEA appears in both the VLE data and the Zenodo candidate sets).

Re-running is safe: all nodes are MERGEd on their natural keys.
"""

import math
import os
import re
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from neo4j import GraphDatabase
from rdkit import Chem

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

URI = os.environ["NEO4J_URI"]
USER = os.environ["NEO4J_USER"]
PASSWORD = os.environ["NEO4J_PASSWORD"]
DATABASE = os.environ.get("NEO4J_DATABASE", "neo4j")

STRUCTURED = ROOT / "data/processed/structured"
UNIFIED_CSV = STRUCTURED / "unified_vle_dataset_with_hartono_dash.csv"
ERMATCHKOV_CSV = ROOT / "data/interim/piperazine_ermatchkov_2006.csv"
LEARNING_CSV = STRUCTURED / "candidate_amines_learning_set.csv"
SCREENING_CSV = STRUCTURED / "candidate_amines_screening_library.csv"
BLENDCO2_CSV = STRUCTURED / "blendco2_simulated_blends.csv"
LIT_PERFORMANCE_CSV = STRUCTURED / "literature_blend_performance.csv"
LIT_KINETICS_CSV = STRUCTURED / "literature_blend_kinetics.csv"

# code -> SMILES. Secondary-amine SMILES (DEA and below) are best-effort from
# common structures, not verified against PubChem -- double check before
# relying on them for anything beyond graph exploration.
AMINE_SMILES = {
    "MEA": "NCCO",
    "AMP": "CC(C)(N)CO",
    "PZ": "C1CNCCN1",
    "MDEA": "CN(CCO)CCO",
    "DEA": "OCCNCCO",
    "DIPA": "CC(O)CNCC(O)C",
    "TEA": "OCCN(CCO)CCO",
    "DMEA": "CN(C)CCO",
    "AEP": "NCCN1CCNCC1",
    "TMPDA": "CN(C)CCCN(C)C",
    "DETA": "NCCNCCN",
    "HEPZ": "OCCN1CCNCC1",
    "HMPD": "CN1CCC(O)CC1",
    "DMAPA": "CN(C)CCCN",
}

# token (as it appears split out of a blend label) -> AMINE_SMILES key
TOKEN_TO_CODE = {code: code for code in AMINE_SMILES}
TOKEN_TO_CODE["3-DMAPA"] = "DMAPA"

# source_table -> (source display name, year)
SOURCE_TABLE_META = {
    "table_6_MEA_CO2_H2O": ("Francois 2024 (low-conc VLE)", 2024),
    "table_7_AMP_PZ_CO2_H2O": ("Francois 2024 (low-conc VLE)", 2024),
    "table_8_PZ_CO2_H2O": ("Francois 2024 (low-conc VLE)", 2024),
    "table_9_AMP_CO2_H2O": ("Francois 2024 (low-conc VLE)", 2024),
    "Hartono_2020_Table4": ("Hartono 2020", 2020),
    "Hartono_2020_Table5": ("Hartono 2020", 2020),
    "Hartono_2020_Table6": ("Hartono 2020", 2020),
    "Hartono_2020_Table7": ("Hartono 2020", 2020),
    "Hartono_2020_Table8": ("Hartono 2020", 2020),
    "Hartono_2020_Table9": ("Hartono 2020", 2020),
    "Dash_2011_Table7": ("Dash 2011", 2011),
}


def n(value):
    """NaN/None -> None, otherwise plain float. Neo4j rejects NaN properties."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, float) and math.isnan(value):
        return None
    return float(value)


_SMILES_CACHE = {}


def canonical_smiles(smiles):
    if smiles is None or (isinstance(smiles, float) and math.isnan(smiles)):
        return None
    if smiles in _SMILES_CACHE:
        return _SMILES_CACHE[smiles]
    mol = Chem.MolFromSmiles(smiles)
    result = Chem.MolToSmiles(mol) if mol else None
    _SMILES_CACHE[smiles] = result
    return result


CANON_AMINE_SMILES = {code: canonical_smiles(smi) for code, smi in AMINE_SMILES.items()}


def amine_obj(code):
    return {"code": code, "smiles": CANON_AMINE_SMILES[code]}


def amines_from_system(system: str) -> list:
    codes = system.replace("-CO2-H2O", "").split("-")
    return [amine_obj(c) for c in codes]


def amine_codes_from_label(label: str) -> list:
    """Best-effort: split a free-text blend label into known amine codes."""
    tokens = re.split(r"[^A-Za-z0-9\-]+", label)
    found = []
    for tok in tokens:
        tok = tok.strip("*")
        if tok in TOKEN_TO_CODE and TOKEN_TO_CODE[tok] not in found:
            found.append(TOKEN_TO_CODE[tok])
    return found


# ---------------------------------------------------------------------------
# VLE measurements (existing)
# ---------------------------------------------------------------------------


def build_unified_rows() -> list:
    df = pd.read_csv(UNIFIED_CSV)
    rows = []

    for _, r in df.iterrows():
        source_table = r["source_table"]
        source_name, source_year = SOURCE_TABLE_META[source_table]

        rows.append(
            {
                "uid": f"{source_table}_{int(r['measurement_id'])}",
                "system": r["system"],
                "amines": amines_from_system(r["system"]),
                "source_table": source_table,
                "source_name": source_name,
                "source_year": source_year,
                "T_C": n(r.get("T_C")),
                "T_K": n(r.get("T_K")),
                "P_kPa": n(r.get("P_kPa")),
                "P_MPa": n(r.get("P_MPa")),
                "x1": n(r.get("x1")),
                "y1": n(r.get("y1")),
                "x2": n(r.get("x2")),
                "y2": n(r.get("y2")),
                "x3": n(r.get("x3")),
                "wt_percent": n(r.get("wt_percent")),
                "molarity": n(r.get("molarity")),
                "molality": None,
                "co2_to_amine_ratio": n(r.get("co2_to_amine_ratio")),
                "loading_alpha": None,
            }
        )

    return rows


def build_ermatchkov_rows() -> list:
    df = pd.read_csv(ERMATCHKOV_CSV)
    rows = []

    for i, r in df.iterrows():
        rows.append(
            {
                "uid": f"Ermatchkov_2006_{i + 1}",
                "system": "PZ-CO2-H2O",
                "amines": amines_from_system("PZ-CO2-H2O"),
                "source_table": "Ermatchkov_2006_ThermoML",
                "source_name": "Ermatchkov 2006",
                "source_year": 2006,
                "T_C": None,
                "T_K": n(r["T"]),
                "P_kPa": n(r["P_CO2"]),
                "P_MPa": None,
                "x1": None,
                "y1": None,
                "x2": None,
                "y2": None,
                "x3": None,
                "wt_percent": None,
                "molarity": None,
                "molality": n(r["conc"]),
                "co2_to_amine_ratio": None,
                "loading_alpha": n(r["loading_alpha"]),
            }
        )

    return rows


# ---------------------------------------------------------------------------
# Candidate amines (CO2_chemical_solvents Zenodo dataset)
# ---------------------------------------------------------------------------


def build_candidate_rows() -> list:
    rows = []

    learning = pd.read_csv(LEARNING_CSV)
    for _, r in learning.iterrows():
        smiles = canonical_smiles(r["std_smiles"])
        if smiles is None:
            continue
        rows.append(
            {
                "smiles": smiles,
                "cid": str(r.get("cid")),
                "MolWeight": n(r.get("MolWeight")),
                "LogP_pred": n(r.get("LogP_pred")),
                "BP_pred": n(r.get("BP_pred")),
                "pKa_b_pred": n(r.get("pKa_b_pred")),
                "dG_MD_ylog": n(r.get("dG_MD_ylog")),
                "CompRate_ylog": n(r.get("CompRate_ylog")),
                "comprate_avg_pred": None,
                "dg_avg_pred": None,
                "dataset": "co2_chemical_solvents_learning_set",
            }
        )

    screening = pd.read_csv(SCREENING_CSV)
    for _, r in screening.iterrows():
        smiles = canonical_smiles(r["std_smiles"])
        if smiles is None:
            continue
        rows.append(
            {
                "smiles": smiles,
                "cid": None,
                "MolWeight": n(r.get("MolWeight")),
                "LogP_pred": n(r.get("LogP_pred")),
                "BP_pred": n(r.get("BP_pred")),
                "pKa_b_pred": n(r.get("pKa_b_pred")),
                "dG_MD_ylog": n(r.get("dGMD")),
                "CompRate_ylog": n(r.get("RMD")),
                "comprate_avg_pred": n(r.get("comprate_avg_pred")),
                "dg_avg_pred": n(r.get("dg_avg_pred")),
                "dataset": f"co2_chemical_solvents_screening_library:{r.get('source')}",
            }
        )

    return rows


# ---------------------------------------------------------------------------
# BlendCO2 simulated blends
# ---------------------------------------------------------------------------


def build_blendco2_rows() -> list:
    df = pd.read_csv(BLENDCO2_CSV)
    comp_cols = {"comp_MEA": "MEA", "comp_MDEA": "MDEA", "comp_AMP": "AMP", "comp_PZ": "PZ"}

    rows = []
    for _, r in df.iterrows():
        components = []
        for col, code in comp_cols.items():
            frac = n(r.get(col))
            if frac and frac > 0:
                components.append({**amine_obj(code), "fraction": frac})

        rows.append(
            {
                "label": r["blend_label"],
                "blend_type": r["blend_type"],
                "cyclic_capacity": n(r.get("cyclic_capacity")),
                "solvent_cost_per_kg": n(r.get("solvent_cost_per_kg")),
                "cost_efficiency": n(r.get("cost_efficiency")),
                "score": n(r.get("score")),
                "components": components,
            }
        )

    return rows


# ---------------------------------------------------------------------------
# Literature blend performance (long format) + kinetics
# ---------------------------------------------------------------------------


def build_literature_performance_rows() -> list:
    df = pd.read_csv(LIT_PERFORMANCE_CSV)
    rows = []

    for _, r in df.iterrows():
        label = r["blend_label"]
        rows.append(
            {
                "label": label,
                "amines": [amine_obj(c) for c in amine_codes_from_label(label)],
                "metric": r["metric"],
                "value": n(r.get("value")),
                "value_min": n(r.get("value_min")),
                "value_max": n(r.get("value_max")),
                "raw_text": r.get("raw_text"),
                "source_document": r["source_document"],
            }
        )

    return rows


def build_literature_kinetics_rows() -> list:
    df = pd.read_csv(LIT_KINETICS_CSV)
    rows = []

    for _, r in df.iterrows():
        label = r["blend_label"]
        rows.append(
            {
                "label": label,
                "amines": [amine_obj(c) for c in amine_codes_from_label(label)],
                "absorption_capacity": n(r.get("absorption_capacity_mol_co2_per_mol_amine")),
                "absorption_rate": n(r.get("absorption_rate_mmol_per_mol_s")),
                "cyclic_loading": n(r.get("cyclic_loading_mol_co2_per_mol_amine")),
                "temperature_K": n(r.get("temperature_K")),
                "source_document": r["source_document"],
            }
        )

    return rows


CONSTRAINTS = [
    "CREATE CONSTRAINT amine_smiles IF NOT EXISTS FOR (a:Amine) REQUIRE a.smiles IS UNIQUE",
    "CREATE CONSTRAINT system_name IF NOT EXISTS FOR (s:System) REQUIRE s.name IS UNIQUE",
    "CREATE CONSTRAINT source_name IF NOT EXISTS FOR (s:Source) REQUIRE s.name IS UNIQUE",
    "CREATE CONSTRAINT table_id IF NOT EXISTS FOR (t:SourceTable) REQUIRE t.id IS UNIQUE",
    "CREATE CONSTRAINT measurement_uid IF NOT EXISTS FOR (m:Measurement) REQUIRE m.uid IS UNIQUE",
    "CREATE CONSTRAINT dataset_name IF NOT EXISTS FOR (d:Dataset) REQUIRE d.name IS UNIQUE",
    "CREATE CONSTRAINT blend_label IF NOT EXISTS FOR (b:Blend) REQUIRE b.label IS UNIQUE",
]

LOAD_MEASUREMENTS = """
UNWIND $rows AS row
MERGE (sys:System {name: row.system})
MERGE (src:Source {name: row.source_name})
  ON CREATE SET src.year = row.source_year
MERGE (tbl:SourceTable {id: row.source_table})
MERGE (tbl)-[:PART_OF]->(src)
MERGE (m:Measurement {uid: row.uid})
SET m.T_C = row.T_C,
    m.T_K = row.T_K,
    m.P_kPa = row.P_kPa,
    m.P_MPa = row.P_MPa,
    m.x1 = row.x1,
    m.y1 = row.y1,
    m.x2 = row.x2,
    m.y2 = row.y2,
    m.x3 = row.x3,
    m.wt_percent = row.wt_percent,
    m.molarity = row.molarity,
    m.molality = row.molality,
    m.co2_to_amine_ratio = row.co2_to_amine_ratio,
    m.loading_alpha = row.loading_alpha
MERGE (m)-[:MEASURED_IN]->(sys)
MERGE (m)-[:FROM_TABLE]->(tbl)
WITH row, sys
UNWIND row.amines AS amineObj
MERGE (a:Amine {smiles: amineObj.smiles})
SET a.name = amineObj.code
MERGE (a)-[:PART_OF]->(sys)
"""

LOAD_CANDIDATES = """
UNWIND $rows AS row
MERGE (a:Amine {smiles: row.smiles})
SET a.cid = coalesce(row.cid, a.cid),
    a.MolWeight = row.MolWeight,
    a.LogP_pred = row.LogP_pred,
    a.BP_pred = row.BP_pred,
    a.pKa_b_pred = row.pKa_b_pred,
    a.dG_MD_ylog = coalesce(row.dG_MD_ylog, a.dG_MD_ylog),
    a.CompRate_ylog = coalesce(row.CompRate_ylog, a.CompRate_ylog),
    a.comprate_avg_pred = coalesce(row.comprate_avg_pred, a.comprate_avg_pred),
    a.dg_avg_pred = coalesce(row.dg_avg_pred, a.dg_avg_pred)
MERGE (d:Dataset {name: row.dataset})
MERGE (a)-[:IN_DATASET]->(d)
"""

LOAD_BLENDCO2 = """
UNWIND $rows AS row
MERGE (src:Source {name: "BlendCO2 in-house solver"})
  ON CREATE SET src.data_type = "simulated"
MERGE (tbl:SourceTable {id: "BlendCO2_all_blends_ranked"})
MERGE (tbl)-[:PART_OF]->(src)
MERGE (b:Blend {label: row.label})
SET b.blend_type = row.blend_type,
    b.data_type = "simulated",
    b.cyclic_capacity = row.cyclic_capacity,
    b.solvent_cost_per_kg = row.solvent_cost_per_kg,
    b.cost_efficiency = row.cost_efficiency,
    b.score = row.score
MERGE (b)-[:FROM_TABLE]->(tbl)
WITH row, b
UNWIND row.components AS comp
MERGE (a:Amine {smiles: comp.smiles})
SET a.name = comp.code
MERGE (a)-[:COMPONENT_OF {fraction: comp.fraction}]->(b)
"""

LOAD_LITERATURE_PERFORMANCE = """
UNWIND $rows AS row
MERGE (src:Source {name: row.source_document})
  ON CREATE SET src.data_type = "literature_ai_extracted"
MERGE (b:Blend {label: row.label})
  ON CREATE SET b.data_type = "literature"
MERGE (b)-[rm:REPORTED_METRIC {metric: row.metric}]->(src)
SET rm.value = row.value,
    rm.value_min = row.value_min,
    rm.value_max = row.value_max,
    rm.raw_text = row.raw_text
WITH row, b
UNWIND row.amines AS amineObj
MERGE (a:Amine {smiles: amineObj.smiles})
SET a.name = amineObj.code
MERGE (a)-[:COMPONENT_OF]->(b)
"""

LOAD_LITERATURE_KINETICS = """
UNWIND $rows AS row
MERGE (src:Source {name: row.source_document})
  ON CREATE SET src.data_type = "literature_ai_extracted"
MERGE (b:Blend {label: row.label})
  ON CREATE SET b.data_type = "literature"
MERGE (b)-[rk:REPORTED_KINETICS]->(src)
SET rk.absorption_capacity = row.absorption_capacity,
    rk.absorption_rate = row.absorption_rate,
    rk.cyclic_loading = row.cyclic_loading,
    rk.temperature_K = row.temperature_K
WITH row, b
UNWIND row.amines AS amineObj
MERGE (a:Amine {smiles: amineObj.smiles})
SET a.name = amineObj.code
MERGE (a)-[:COMPONENT_OF]->(b)
"""


def main():
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    driver.verify_connectivity()

    with driver.session(database=DATABASE) as session:
        for stmt in CONSTRAINTS:
            session.run(stmt)

        vle_rows = build_unified_rows() + build_ermatchkov_rows()
        session.run(LOAD_MEASUREMENTS, rows=vle_rows)
        print(f"VLE measurements loaded: {len(vle_rows)}")

        candidate_rows = build_candidate_rows()
        session.run(LOAD_CANDIDATES, rows=candidate_rows)
        print(f"Candidate amines loaded: {len(candidate_rows)}")

        blend_rows = build_blendco2_rows()
        session.run(LOAD_BLENDCO2, rows=blend_rows)
        print(f"BlendCO2 simulated blends loaded: {len(blend_rows)}")

        lit_perf_rows = build_literature_performance_rows()
        session.run(LOAD_LITERATURE_PERFORMANCE, rows=lit_perf_rows)
        print(f"Literature performance records loaded: {len(lit_perf_rows)}")

        lit_kin_rows = build_literature_kinetics_rows()
        session.run(LOAD_LITERATURE_KINETICS, rows=lit_kin_rows)
        print(f"Literature kinetics records loaded: {len(lit_kin_rows)}")

        result = session.run(
            "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS n ORDER BY label"
        )
        print("\nNode counts:")
        for record in result:
            print(f"  {record['label']:<14} {record['n']}")

        result = session.run(
            "MATCH ()-[r]->() RETURN type(r) AS rel, count(*) AS n ORDER BY rel"
        )
        print("\nRelationship counts:")
        for record in result:
            print(f"  {record['rel']:<20} {record['n']}")

    driver.close()
    print("\nDone. Open Neo4j Browser and run:  MATCH (n) RETURN n LIMIT 300")


if __name__ == "__main__":
    main()
