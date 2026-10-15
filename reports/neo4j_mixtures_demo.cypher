// amine-co2-uq -- mixture screening graph. Run each block on its own in Neo4j Browser.
// FIRST: drag reports/neo4j_mixtures.grass onto the Browser window for the colours:
//   yellow = MEA/MDEA/PZ/AMP-only mixtures, blue = mixtures with another amine,
//   grey = single-amine references, orange = the four core amines, light blue = partners.
// Rebuild after a new screening run:  python -m src.data.load_neo4j_mixtures

// ---------------------------------------------------------------
// 1. The headline picture: top 25 yellow + top 25 blue, with their amines
// ---------------------------------------------------------------
MATCH (m:Mixture)
WHERE m.color IN ['yellow', 'blue'] AND m.rank_in_color <= 25
MATCH p = (a:Amine)-[:IN_MIXTURE]->(m)
RETURN p;

// ---------------------------------------------------------------
// 2. Yellow only: how the four core amines combine (top 40 yellow)
// ---------------------------------------------------------------
MATCH p = (a:Core)-[:IN_MIXTURE]->(m:Yellow)
WHERE m.rank_in_color <= 40
RETURN p;

// ---------------------------------------------------------------
// 3. The overall shortlist (top 100 by combined score) as a graph
// ---------------------------------------------------------------
MATCH p = (a:Amine)-[:IN_MIXTURE]->(m:Shortlist)
RETURN p;

// ---------------------------------------------------------------
// 4. Diverse shortlist: at most 2 proportions per amine combination
// ---------------------------------------------------------------
MATCH (m:Mixture) WHERE 0 < m.diverse_rank <= 50
MATCH p = (a:Amine)-[:IN_MIXTURE]->(m)
RETURN p;

// Table version of the diverse top 50
MATCH (m:Mixture) WHERE 0 < m.diverse_rank <= 50
RETURN m.diverse_rank AS rank, m.color AS colour, m.composition AS mixture,
       round(m.score_both, 3) AS score_vs_MEA, round(m.p_top50, 2) AS P_top50,
       round(m.cement_cyclic, 2) AS cyclic_cement, round(m.cement_q_reb, 2) AS Qreb_cement
ORDER BY rank;

// ---------------------------------------------------------------
// 5. Which amines are the hubs of the shortlist
// ---------------------------------------------------------------
MATCH (a:Amine)-[:IN_MIXTURE]->(m:Shortlist)
RETURN a.name AS amine, coalesce(a.role, '-') AS role, count(m) AS mixtures_in_top100,
       round(avg(m.score_both), 3) AS mean_score
ORDER BY mixtures_in_top100 DESC;

// ---------------------------------------------------------------
// 6. Cement vs coal: does the ranking change with the flue gas?
// ---------------------------------------------------------------
MATCH (m:Mixture)-[r:SCORED_IN]->(s:Scenario)
WHERE m.rank_both <= 20
RETURN m.label AS mixture, s.name AS scenario, r.rank AS rank,
       round(r.cyclic, 2) AS cyclic, round(r.q_reb, 2) AS Qreb_GJ_per_t,
       round(r.score_lo90, 3) AS score_lo90, round(r.score_hi90, 3) AS score_hi90
ORDER BY mixture, scenario;

// Graph view of the same thing
MATCH p = (m:Mixture)-[:SCORED_IN]->(:Scenario)
WHERE m.rank_both <= 15
RETURN p;

// ---------------------------------------------------------------
// 7. Robust vs speculative picks (uncertainty-aware)
// ---------------------------------------------------------------
// robust: most often in the top 50 across Monte Carlo samples
MATCH (m:Mixture) WHERE m.p_top50 > 0
RETURN m.composition, m.color, round(m.score_both, 3) AS score, round(m.p_top50, 2) AS P_top50,
       round(m.robust_score, 3) AS score_lower_bound
ORDER BY P_top50 DESC LIMIT 25;

// ---------------------------------------------------------------
// 8. Everything around one amine (e.g. PZ): all mixtures it appears in, best first
// ---------------------------------------------------------------
MATCH p = (:Amine {name: 'PZ'})-[:IN_MIXTURE]->(m:Mixture)
WHERE m.rank_both <= 60
RETURN p;

// ---------------------------------------------------------------
// 9. Benchmarks: where the single amines land
// ---------------------------------------------------------------
MATCH (m:Reference)
RETURN m.label AS amine, m.rank_both AS overall_rank, round(m.score_both, 3) AS score,
       round(m.cement_cyclic, 2) AS cyclic_cement, round(m.cement_q_reb, 2) AS Qreb_cement
ORDER BY overall_rank;

// ---------------------------------------------------------------
// 10. Link back to the experimental data: shortlist amines that also have VLE measurements
// ---------------------------------------------------------------
MATCH (a:Amine)-[:IN_MIXTURE]->(m:Shortlist)
MATCH (a)-[:PART_OF]->(sys:System)
RETURN DISTINCT a.name AS amine, collect(DISTINCT sys.name) AS measured_systems;
