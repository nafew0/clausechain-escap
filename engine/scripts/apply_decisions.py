"""Atomic, file-authoritative decision writers (App Dev Plan Rev B #5, Rev C).

The ONLY sanctioned way to mutate the engine's decision artifacts. Django (or
any caller) pipes a JSON batch; the CLI acquires a cross-process lock, merges
latest-wins, validates the COMPLETE file, writes tmp+fsync+atomic-rename, and
prints the resulting SHA-256. DB state must mirror this output, never precede it.

Domains and files (under <root>/data/review/):
  findings -> decisions.json          (template-complete; engine C2 contract)
  recall   -> recall_decisions.json   (key: sha256(economy|indicator|act|ref))
  zone3    -> zone3_decisions.json    (key: economy|indicator)

Input (stdin or --input): {"decisions": [...]} — shapes per domain below.
Optimistic concurrency: --expected-sha <sha256 of the file the caller last saw>;
mismatch exits 3 and prints the current sha (no write).
Bundling (Rev C, debounced by the caller): --bundle-after copies all three
files + manifest to data/review/bundles/<utc>-<hash8>/.

Exit codes: 0 ok · 2 validation error · 3 concurrency conflict.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT))

RECALL_VERDICTS = {"REAL_MISS", "GOLD_WRONG", "GOLD_AMBIGUOUS",
                   "CORRECT_ABSTENTION", "NEEDS_CORRECTION"}
ZONE3_SCORES = {0, 0.5, 1}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_write(path: Path, payload) -> str:
    data = json.dumps(payload, indent=1, ensure_ascii=False).encode()
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    written = path.read_bytes()
    digest = _sha(written)
    if written != data:  # verify the rename landed intact
        raise RuntimeError("post-rename verification failed")
    return digest


def _validate_findings(items: list[dict], template_subjects: dict[str, str]) -> None:
    from packages.core.schemas import ReviewDecision

    for item in items:
        key, review = item.get("finding_key"), item.get("review") or {}
        if key not in template_subjects:
            raise ValueError(f"unknown finding_key {str(key)[:16]}…")
        subject_hash = item.get("review_subject_hash")
        if subject_hash != template_subjects[key]:
            raise ValueError(
                f"{str(key)[:12]}: stale or missing review_subject_hash; refresh authoritative evidence"
            )
        decision = review.get("decision")
        if decision not in {"approved", "rejected"}:
            raise ValueError(f"{str(key)[:12]}: decision must be approved|rejected "
                             "(needs-correction is app-only, never exported)")
        ReviewDecision.model_validate(review)
        if decision == "approved":
            cit, map_ = review.get("citation_reviewer_name", ""), review.get("mapping_reviewer_name", "")
            if not cit or not map_:
                raise ValueError(f"{str(key)[:12]}: approved requires named citation AND mapping reviewers")
            if cit.strip().lower() == map_.strip().lower():
                raise ValueError(f"{str(key)[:12]}: citation and mapping reviewers must be different people")
            if not review.get("reviewed_at"):
                raise ValueError(f"{str(key)[:12]}: approved requires reviewed_at")


def _validate_recall(items: list[dict]) -> None:
    for item in items:
        if not item.get("recall_key"):
            raise ValueError("recall decision missing recall_key")
        if item.get("verdict") not in RECALL_VERDICTS:
            raise ValueError(f"invalid recall verdict {item.get('verdict')!r}")
        if not item.get("reviewer_name") or not item.get("reviewed_at"):
            raise ValueError("recall decision requires reviewer_name and reviewed_at")


def _validate_zone3(items: list[dict]) -> None:
    for item in items:
        if not item.get("economy") or not item.get("indicator"):
            raise ValueError("zone3 decision requires economy and indicator")
        if item.get("action") not in {"approve", "override"}:
            raise ValueError("zone3 action must be approve|override")
        if item.get("action") == "override" and item.get("score") not in ZONE3_SCORES:
            raise ValueError("zone3 override requires score in {0, 0.5, 1}")
        if not item.get("reviewer_name") or not item.get("reviewed_at"):
            raise ValueError("zone3 decision requires reviewer_name and reviewed_at")


def apply(root: Path, domain: str, decisions: list[dict],
          expected_sha: str | None) -> dict:
    review_dir = root / "data/review"
    review_dir.mkdir(parents=True, exist_ok=True)
    lock_path = review_dir / ".decisions.lock"
    with open(lock_path, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if domain == "findings":
            path = review_dir / "decisions.json"
            template = json.loads((root / "submission/review/decisions.template.json").read_text())
            current = json.loads(path.read_text()) if path.is_file() else template
            if expected_sha and path.is_file() and _sha(path.read_bytes()) != expected_sha:
                return {"ok": False, "conflict": True, "sha256": _sha(path.read_bytes())}
            template_subjects = {
                t["finding_key"]: t["review_subject_hash"] for t in template
            }
            _validate_findings(decisions, template_subjects)
            # Template-refresh migration: seed from the CURRENT template (new keys
            # start as pending template rows), overlay any existing decisions whose
            # keys survive, then apply this batch. Rows for keys no longer in the
            # template drop out of the live file — their receipts are preserved in
            # the exported bundles (append-only history).
            by_key = {t["finding_key"]: t for t in template}
            by_key.update({
                d["finding_key"]: d for d in current
                if d.get("finding_key") in by_key
                and d.get("review_subject_hash") == template_subjects[d["finding_key"]]
            })
            for item in decisions:  # latest-wins supersession (append-only history lives in the DB)
                by_key[item["finding_key"]] = {"finding_key": item["finding_key"],
                                               "review_subject_hash": item["review_subject_hash"],
                                               "review": item["review"]}
            merged = [by_key[t["finding_key"]] for t in template]  # template order + completeness
        else:
            name = "recall_decisions.json" if domain == "recall" else "zone3_decisions.json"
            path = review_dir / name
            current = json.loads(path.read_text()) if path.is_file() else []
            if expected_sha and path.is_file() and _sha(path.read_bytes()) != expected_sha:
                return {"ok": False, "conflict": True, "sha256": _sha(path.read_bytes())}
            (_validate_recall if domain == "recall" else _validate_zone3)(decisions)
            keyf = ((lambda d: d["recall_key"]) if domain == "recall"
                    else (lambda d: f"{d['economy']}|{d['indicator']}"))
            by_key = {keyf(d): d for d in current}
            for item in decisions:
                by_key[keyf(item)] = item
            merged = list(by_key.values())
        digest = _atomic_write(path, merged)
        return {"ok": True, "path": str(path), "sha256": digest, "applied": len(decisions)}


def export_bundle(root: Path) -> dict:
    review_dir = root / "data/review"
    files = [review_dir / n for n in
             ("decisions.json", "recall_decisions.json", "zone3_decisions.json")]
    manifest = {"exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "files": {f.name: _sha(f.read_bytes()) for f in files if f.is_file()}}
    stamp = manifest["exported_at"].replace(":", "").replace("-", "")[:15]
    combined = _sha(json.dumps(manifest["files"], sort_keys=True).encode())[:8]
    bundle = review_dir / "bundles" / f"{stamp}-{combined}"
    bundle.mkdir(parents=True, exist_ok=True)
    for f in files:
        if f.is_file():
            (bundle / f.name).write_bytes(f.read_bytes())
    (bundle / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return {"bundle": str(bundle), "manifest": manifest}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", required=True, choices=["findings", "recall", "zone3"])
    parser.add_argument("--root", default=str(ENGINE_ROOT))
    parser.add_argument("--input", help="JSON file (default: stdin)")
    parser.add_argument("--expected-sha", dest="expected_sha")
    parser.add_argument("--bundle-after", action="store_true")
    args = parser.parse_args()

    raw = Path(args.input).read_text() if args.input else sys.stdin.read()
    try:
        decisions = json.loads(raw).get("decisions", [])
        result = apply(Path(args.root), args.domain, decisions, args.expected_sha)
    except (ValueError, KeyError) as error:
        print(json.dumps({"ok": False, "error": str(error)}))
        return 2
    if not result.get("ok"):
        print(json.dumps(result))
        return 3
    if args.bundle_after:
        result["bundle"] = export_bundle(Path(args.root))["bundle"]
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
