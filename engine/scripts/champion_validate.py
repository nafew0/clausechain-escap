"""Independent machine-readable champion-gate audit. Never approves legal rows."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from packages.core.finalization import validate_final_finding  # noqa: E402
from packages.core.corpus_fingerprint import corpus_fingerprint  # noqa: E402
from packages.core.schemas import MappedFinding, SourceArtifact, TextSpan  # noqa: E402


RUNS = [f"outputs/final_{cc}_p{p}" for cc in ("si", "ma", "au") for p in (6, 7)]


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args(); failures: list[str] = []
    report: dict = {"status": "FAIL", "failures": failures, "runs": {}}
    if not args.skip_tests:
        test = subprocess.run([sys.executable, "-m", "pytest", "-q"], capture_output=True, text=True)
        test_lines = (test.stdout + test.stderr).strip().splitlines()
        test_summary = next(
            (line for line in reversed(test_lines)
             if " passed" in line or " failed" in line or " error" in line.lower()),
            test_lines[-1] if test_lines else "no test output",
        )
        report["tests"] = {"passed": test.returncode == 0,
                           "summary": [test_summary]}
        if test.returncode:
            failures.append("automated test suite failed")

    graph = subprocess.run([sys.executable, "scripts/validate_graph.py"], capture_output=True, text=True)
    report["graph"] = json.loads(Path("reports/graph_validation.json").read_text())
    if graph.returncode:
        failures.append("graph validation failed")

    from packages.graph.sqlite_graph import SqliteGraphStore
    from packages.retrieval.hybrid import load_corpus

    store = SqliteGraphStore()
    current_known_hash = hashlib.sha256(Path("data/known_index.json").read_bytes()).hexdigest()
    expected_ledger_path = Path("configs/expected_anchors.json")
    current_expected_hash = hashlib.sha256(expected_ledger_path.read_bytes()).hexdigest()
    for run_path in RUNS:
        path = Path(run_path) / "output.json"
        if not path.is_file():
            continue
        envelope = json.loads(path.read_text())
        economy = ({"SG": "Singapore", "MY": "Malaysia", "AU": "Australia"}
                   .get(str(envelope.get("country", "")).upper(), envelope.get("country")))
        expected = corpus_fingerprint(load_corpus(store, economy))
        recorded = (envelope.get("metadata") or {}).get("corpus_fingerprint")
        if recorded != expected:
            report["runs"].setdefault(run_path, {})["corpus_fingerprint"] = {
                "recorded": recorded, "current": expected, "status": "STALE"}
            failures.append(f"{run_path} is stale against the current evidence corpus")
        recorded_known_hash = (envelope.get("metadata") or {}).get("known_index_sha256")
        if recorded_known_hash != current_known_hash:
            report["runs"].setdefault(run_path, {})["known_index_sha256"] = {
                "recorded": recorded_known_hash, "current": current_known_hash,
                "status": "STALE"}
            failures.append(f"{run_path} is stale against the current KNOWN baseline")
        recorded_expected_hash = (envelope.get("metadata") or {}).get(
            "expected_anchor_ledger_sha256"
        )
        if recorded_expected_hash != current_expected_hash:
            report["runs"].setdefault(run_path, {})["expected_anchor_ledger_sha256"] = {
                "recorded": recorded_expected_hash, "current": current_expected_hash,
                "status": "STALE",
            }
            failures.append(f"{run_path} is stale against the expected-anchor ledger")

    gold_path = Path("tests/fixtures/extraction_gold_v1.json")
    draft_path = Path("tests/fixtures/extraction_gold_v1.draft.json")
    gold = json.loads((gold_path if gold_path.is_file() else draft_path).read_text())
    report["extraction_gold"] = {"path": str(gold_path if gold_path.is_file() else draft_path),
        "status": gold.get("status"), "pages": len(gold.get("pages", [])),
        "human_checked": sum(bool(p.get("human_checked")) for p in gold.get("pages", []))}
    if not gold_path.is_file() or report["extraction_gold"]["human_checked"] != 30:
        failures.append("30-page extraction gold lacks named human sign-off")

    for run_path in RUNS:
        path = Path(run_path) / "output.json"
        if not path.is_file():
            failures.append(f"missing run {run_path}"); continue
        env = json.loads(path.read_text()); stats = env.get("metadata", {}).get("pipeline_stats", {})
        report["runs"].setdefault(run_path, {}).update({
            "candidates": len(env.get("findings", [])),
            "warnings": len(env.get("warnings", [])), "pipeline_stats": stats})

    recall_path = Path("data/review/recall_adjudication.json")
    recall = json.loads(recall_path.read_text()) if recall_path.is_file() else {"misses": []}
    decision_path = Path("data/review/recall_decisions.json")
    recall_decisions = ({d["recall_key"]: d for d in json.loads(decision_path.read_text())}
                        if decision_path.is_file() else {})
    pending_adjudications = []
    unresolved_real_misses = []
    adjudicated_gold_issues = []
    for miss in recall.get("misses", []):
        import hashlib as _recall_hash

        key = miss.get("recall_key") or _recall_hash.sha256("\x1f".join((
            str(miss.get("economy")), str(miss.get("gold_indicator")),
            str(miss.get("act")), str(miss.get("ref")),
        )).encode()).hexdigest()
        verdict = (recall_decisions.get(key) or {}).get("verdict") \
            or miss.get("reviewer_verdict")
        if not verdict:
            pending_adjudications.append(miss)
        elif verdict in {"REAL_MISS", "NEEDS_CORRECTION"}:
            unresolved_real_misses.append({"recall_key": key, "verdict": verdict,
                                           "economy": miss.get("economy"),
                                           "indicator": miss.get("gold_indicator"),
                                           "act": miss.get("act"), "ref": miss.get("ref")})
        else:
            adjudicated_gold_issues.append({"recall_key": key, "verdict": verdict})
    report["recall"] = {"stats": recall.get("stats", {}), "misses": len(recall.get("misses", [])),
                        "pending_adjudications": len(pending_adjudications),
                        "unresolved_real_misses": unresolved_real_misses,
                        "adjudicated_gold_or_abstention": adjudicated_gold_issues}
    if pending_adjudications:
        failures.append(f"{len(pending_adjudications)} recall misses await adjudication")
    if unresolved_real_misses:
        failures.append(f"{len(unresolved_real_misses)} unresolved REAL_MISS recall gaps remain")

    candidate_path = Path("submission/consolidated.json")
    candidates = json.loads(candidate_path.read_text()).get("rows", []) if candidate_path.is_file() else []
    citation_rows = [r for r in candidates if r.get("citation_proof")]
    absence_rows = [r for r in candidates if not r.get("citation_proof")
                    and r.get("search_coverage_manifest")
                    and str(r.get("Article / Section", r.get("article_section", ""))).lower() == "n/a"]
    incomplete_evidence = [r for r in candidates if not r.get("citation_proof") and not (
        r.get("search_coverage_manifest")
        and str(r.get("Article / Section", r.get("article_section", ""))).lower() == "n/a")]
    report["candidates"] = {"rows": len(candidates),
        "pending_review": sum(r.get("reviewer_decision", "pending") != "approved" for r in candidates),
        "citation_proof_rows": len(citation_rows),
        "absence_manifest_rows": len(absence_rows),
        "complete_evidence_contract": len(candidates) - len(incomplete_evidence),
        "in_force": sum(r.get("Status", r.get("status")) == "in_force" for r in candidates)}
    closure_failures = []
    for row in citation_rows:
        proof = row.get("citation_proof") or {}
        g9 = [gate for gate in proof.get("gate_results", []) if gate.get("gate_id") == "G9"]
        code = (g9[-1].get("metadata", {}).get("closure_code") if g9 else None)
        offsets_ok = (
            isinstance(proof.get("source_start_char"), int)
            and isinstance(proof.get("source_end_char"), int)
            and proof["source_end_char"] > proof["source_start_char"]
        )
        if code not in {"PASS_CLOSED", "PASS_LONG_BUT_CLOSED"} or not offsets_ok:
            closure_failures.append({
                "economy": row.get("Economy"), "indicator": row.get("Indicator ID"),
                "law": row.get("Law Name"), "article": row.get("Article / Section"),
                "closure_code": code, "offsets_ok": offsets_ok,
            })
    report["candidates"]["snippet_closure_failures"] = closure_failures
    if incomplete_evidence:
        failures.append(f"{len(incomplete_evidence)} candidates lack CitationProof or an absence manifest")
    if closure_failures:
        failures.append(f"{len(closure_failures)} citation snippets lack structural closure proof")
    if report["candidates"]["pending_review"]:
        failures.append("candidate findings still require named human decisions")

    zone_pending = 0
    for path in Path("data/zone3").glob("*_scores.json"):
        payload = json.loads(path.read_text())
        zone_pending += sum(v.get("reviewer_decision") != "approved"
                            for v in payload.get("indicators", {}).values())
    report["zone3_pending"] = zone_pending
    if zone_pending:
        failures.append(f"{zone_pending} Zone-3 scores await explicit approval/override")

    final_json, final_csv = Path("submission/consolidated_final.json"), Path("submission/consolidated_final.csv")
    report["final_artifacts_present"] = final_json.is_file() and final_csv.is_file()
    if not report["final_artifacts_present"]:
        failures.append("approval-only submission replay has not produced final artifacts")

    report["status"] = "PASS" if not failures else "FAIL"
    Path("reports").mkdir(exist_ok=True)
    Path("reports/champion_validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "failures": failures,
                      "candidate_rows": len(candidates)}, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
