// amine-co2-uq -- Neo4j demo script. Run each block in order; blocks are separated by ';'.
// Tip: in the style panel, give each label its own colour (Amine, System, Measurement, Source, SourceTable, Dataset, Blend).

// ---------------------------------------------------------------
// 0. The data model
// ---------------------------------------------------------------
CALL db.schema.visualization();

// ---------------------------------------------------------------
// 1. Real experimental core: which amines, which systems, which sources
// ---------------------------------------------------------------
MATCH p=(a:Amine)-[:PART_OF]->(s:System)
RETURN p;

MATCH p=(t:SourceTable)-[:PART_OF]->(src:Source)
WHERE src.year IS NOT NULL
RETURN p;

// Table view: measurements per system and source (shows the coverage imbalance)
MATCH (m:Measurement)-[:MEASURED_IN]->(s:System)
MATCH (m)-[:FROM_TABLE]->(:SourceTable)-[:PART_OF]->(src:Source)
RETURN s.name AS system, src.name AS source, count(m) AS measurements
ORDER BY system, measurements DESC;

// Drill into one system
MATCH p=(m:Measurement)-[:MEASURED_IN]->(:System {name: 'MEA-CO2-H2O'})
RETURN p LIMIT 40;

// ---------------------------------------------------------------
// 2. Candidate amine library (Zenodo CO2_chemical_solvents)
// ---------------------------------------------------------------
MATCH (a:Amine)-[:IN_DATASET]->(d:Dataset)
RETURN d.name AS dataset, count(a) AS amines
ORDER BY amines DESC;

MATCH p=(a:Amine)-[:IN_DATASET]->(d:Dataset)
RETURN p LIMIT 150;

// Properties are queryable on the node (descriptors + MD free energy + RF-ensemble predictions)
MATCH (a:Amine)
WHERE a.dg_avg_pred IS NOT NULL
RETURN a.smiles AS smiles, a.MolWeight AS mol_weight, a.pKa_b_pred AS pKa_b, a.dg_avg_pred AS predicted_dG
ORDER BY predicted_dG
LIMIT 10;

// ---------------------------------------------------------------
// 3. Simulated blends (in-house BlendCO2 solver -- simulated, not experimental)
// ---------------------------------------------------------------
MATCH p=(a:Amine)-[:COMPONENT_OF]->(b:Blend {data_type: 'simulated'})
WHERE b.cyclic_capacity > 95
RETURN p;

// ---------------------------------------------------------------
// 4. Literature regeneration-energy / heat-of-absorption data (AI-extracted, unverified)
// ---------------------------------------------------------------
MATCH p=(a:Amine)-[:COMPONENT_OF]->(b:Blend {data_type: 'literature'})-[r:REPORTED_METRIC]->(:Source)
WHERE r.metric CONTAINS 'Regen' OR r.metric CONTAINS 'Heat of'
RETURN p;

MATCH (b:Blend {data_type: 'literature'})-[r:REPORTED_METRIC]->(:Source)
WHERE r.metric CONTAINS 'Regen' OR r.metric CONTAINS 'Heat of'
RETURN b.label AS blend, r.metric AS metric, r.raw_text AS reported_value
ORDER BY blend;

// ---------------------------------------------------------------
// 5. Integration: named amines that appear in several data layers
// ---------------------------------------------------------------
MATCH (a:Amine)
WHERE a.name IS NOT NULL
RETURN a.name AS amine,
       size([(a)-[:PART_OF]->(:System) | 1]) AS vle_systems,
       size([(a)-[:IN_DATASET]->(:Dataset) | 1]) AS candidate_sets,
       size([(a)-[:COMPONENT_OF]->(:Blend) | 1]) AS blends
ORDER BY blends DESC;

MATCH p=(a:Amine {name: 'MDEA'})-[*1..2]-(n)
RETURN p LIMIT 80;

// ---------------------------------------------------------------
// 6. The gap this project targets: candidates with no experimental VLE data
// ---------------------------------------------------------------
MATCH (a:Amine)-[:IN_DATASET]->(:Dataset)
WITH DISTINCT a
RETURN count(a) AS candidate_amines,
       sum(CASE WHEN EXISTS { (a)-[:PART_OF]->(:System) } THEN 1 ELSE 0 END) AS with_experimental_vle;
