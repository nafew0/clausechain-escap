CREATE CONSTRAINT economy_code IF NOT EXISTS
FOR (n:Economy) REQUIRE n.code IS UNIQUE;

CREATE CONSTRAINT instrument_id IF NOT EXISTS
FOR (n:Instrument) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT instrument_version_id IF NOT EXISTS
FOR (n:InstrumentVersion) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT section_id IF NOT EXISTS
FOR (n:Section) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT provision_id IF NOT EXISTS
FOR (n:Provision) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT source_span_id IF NOT EXISTS
FOR (n:SourceSpan) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT indicator_id IF NOT EXISTS
FOR (n:Indicator) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT candidate_finding_id IF NOT EXISTS
FOR (n:CandidateFinding) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT verified_finding_id IF NOT EXISTS
FOR (n:VerifiedFinding) REQUIRE n.id IS UNIQUE;

