// ClauseChain — live-demo Cypher queries (GraphRAG §10: "why this row?")
// Run against the Neo4j backend (GRAPH_BACKEND=neo4j).

// 1. Why does this row map to P6-I4? — full audit path for SG PDPA s. 26
MATCH (i:Instrument)-[:HAS_SECTION]->(s:Section)-[:HAS_PROVISION]->(p:Provision)
WHERE p.article_section STARTS WITH 's. 26' AND p.law_name CONTAINS 'Personal Data Protection Act 2012'
OPTIONAL MATCH (s)-[m:MAPS_TO]->(ind)
RETURN i.law_name, s.article_section, left(p.text, 160) AS verbatim, ind.id AS indicator, m.tag AS discovery;

// 2. The cross-reference web around a provision (exceptions & dependencies)
MATCH (p:Provision {economy: 'Singapore'})-[r:CROSS_REFERENCES]->(target)
WHERE p.law_name CONTAINS 'Personal Data Protection'
RETURN p.article_section, r.raw AS reference_text, target.id AS points_to LIMIT 25;

// 3. Everything the engine found for one indicator, with NEW/KNOWN provenance
MATCH (f:VerifiedFinding {indicator: 'P7-I5'})-[:EVIDENCED_BY]->(s)
RETURN f.economy, f.law, f.article, f.tag ORDER BY f.economy;

// 4. NEW discoveries relative to ESCAP's master baseline
MATCH (s)-[:NEW_RELATIVE_TO]->(b)
RETURN s.id AS provision_section, b.id AS baseline LIMIT 25;

// 5. Dangling references (G8 evidence): cross-refs whose target section has no text
MATCH (p:Provision)-[r:CROSS_REFERENCES]->(t)
WHERE NOT (t)-[:HAS_PROVISION]->() AND t.article_section IS NULL
RETURN p.law_name, p.article_section, r.raw LIMIT 25;
