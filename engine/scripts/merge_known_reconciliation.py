"""Merge zero-LLM KNOWN-anchor reconciliation rows into an existing run.

Only rows that close a currently adjudicated REAL_MISS are eligible.  NEW rows
and every unrelated finding remain byte-for-byte model-equivalent; current
corpus fingerprints come from the deterministic reconciliation receipt.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.core.finalization import finding_key
from packages.core.schemas import MappedFinding, RunEnvelope
from packages.discovery.diff import laws_match, section_base, section_matches
from packages.export.csv_writer import write_csv
from packages.export.json_writer import write_json


def _law_parts(value: str) -> list[str]:
    return [part.strip() for part in re.split(r";|\n\s*\n", value or "") if part.strip()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--reconciled", required=True)
    parser.add_argument("--recall", default="data/review/recall_adjudication.json")
    args = parser.parse_args()

    target_dir, reconciled_dir = Path(args.target), Path(args.reconciled)
    target = RunEnvelope.model_validate_json((target_dir / "output.json").read_text())
    reconciled = RunEnvelope.model_validate_json((reconciled_dir / "output.json").read_text())
    if reconciled.metadata.get("live_llm_calls") is not False:
        raise SystemExit("reconciliation envelope is not certified zero-LLM")

    economy = {"SG": "Singapore", "MY": "Malaysia", "AU": "Australia"}.get(
        target.country.upper(), target.country
    )
    misses = json.loads(Path(args.recall).read_text()).get("misses", [])
    closed_verdicts = {"GOLD_WRONG", "GOLD_AMBIGUOUS", "CORRECT_ABSTENTION"}
    active = [miss for miss in misses
              if miss.get("economy") == economy
              and str(miss.get("pillar")) == str(target.pillar)
              and miss.get("reviewer_verdict") not in closed_verdicts
              and ((miss.get("reviewer_verdict") or miss.get("proposed_verdict")) == "REAL_MISS"
                   or (miss.get("evidence") or {}).get("technical_class")
                   == "IN_CORPUS_NOT_EMITTED")]

    def closes(finding: MappedFinding) -> bool:
        for miss in active:
            if finding.indicator_id != miss.get("gold_indicator"):
                continue
            if not section_matches(section_base(miss.get("ref", "")),
                                   section_base(finding.article_section)):
                continue
            parts = _law_parts(miss.get("act", ""))
            if not parts or any(laws_match(part, finding.law_name) for part in parts):
                return True
        return False

    additions = [finding for finding in reconciled.findings
                 if finding.citation_proof and closes(finding)]
    if not additions:
        raise SystemExit("no current REAL_MISS was closed by the reconciliation envelope")

    addition_keys = {finding_key(finding) for finding in additions}
    recovered_indicators = {finding.indicator_id for finding in additions}
    retained = [finding for finding in target.findings
                if finding_key(finding) not in addition_keys
                and not (finding.indicator_id in recovered_indicators
                         and "NO_EVIDENCE_FOUND_PENDING_REVIEW" in finding.verbatim_snippet)]
    target.findings = retained + additions
    target.findings.sort(key=lambda finding: (finding.indicator_id, finding.law_name,
                                               finding.article_section))
    for key in ("corpus_fingerprint", "known_index_sha256", "expected_anchor_ledger_sha256"):
        target.metadata[key] = reconciled.metadata.get(key)
    target.metadata["known_reconciliation"] = {
        "contract": "zero-llm-known-anchor-reconciliation-v1",
        "source_run_id": reconciled.run_id,
        "added_finding_keys": [finding_key(finding) for finding in additions],
        "live_llm_calls": False,
        "cost_usd": (reconciled.metadata.get("cost_report") or {}).get("total_usd", 0),
    }
    write_csv(target.findings, target_dir / "output.csv")
    write_json(target, target_dir / "output.json")
    write_csv(target.findings, target_dir / "candidate_rows.csv")
    write_csv([finding for finding in target.findings
               if finding.discovery_tag == "NEW"
               or finding.status != "in_force"
               or "PENDING_REVIEW" in finding.verbatim_snippet],
              target_dir / "legal_review.csv")
    print(json.dumps({"target": str(target_dir), "added": len(additions),
                      "rows": len(target.findings),
                      "articles": [finding.article_section for finding in additions],
                      "cost_usd": 0}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
