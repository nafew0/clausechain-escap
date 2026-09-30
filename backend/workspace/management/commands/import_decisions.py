"""Load the signed review decisions from the engine's authoritative files.

The engine files under data/review/ (decisions.json, zone3_decisions.json,
recall_decisions.json) are the signed record; the database rows are what the
review queues, matrix and ledger read. A fresh install imports the snapshot but
starts with no decision rows, so every queue would show 0 decided. This command
recreates those rows from the files for the active snapshot of each mode.

Idempotent: a finding, score or recall item that already has a decision row is
left alone, so decisions recorded in the app are never overwritten.
"""

import hashlib
import json
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.dateparse import parse_datetime

from workspace.keys import zone3_key
from workspace.mode import MODES, review_dir
from workspace.models import (
    EngineSnapshot,
    FindingDecision,
    RecallDecision,
    ReviewItem,
    Zone3Decision,
)

IMPORT_USERNAME = "ledger-import"
PROVENANCE = "Signed engine ledger, loaded by manage.py import_decisions"
FINDING_QUEUES = (ReviewItem.Queue.NEW, ReviewItem.Queue.KNOWN, ReviewItem.Queue.ABSENCE)
ROLE_LENGTH = FindingDecision._meta.get_field("reviewer_role").max_length


def import_user():
    """The account recorded as created_by on imported rows; it cannot sign in."""
    user, created = get_user_model().objects.get_or_create(
        username=IMPORT_USERNAME,
        defaults={
            "email": "ledger-import@clausechain.local",
            "first_name": "Engine",
            "last_name": "ledger",
            "is_active": False,
        },
    )
    if created:
        user.set_unusable_password()
        user.save(update_fields=["password"])
    return user


def read_ledger(path):
    if not path.exists():
        return [], ""
    raw = path.read_bytes()
    rows = json.loads(raw.decode("utf-8") or "[]")
    return (rows if isinstance(rows, list) else []), hashlib.sha256(raw).hexdigest()


def when(value, fallback):
    parsed = parse_datetime(str(value or "")) if value else None
    if parsed is None:
        return fallback
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt_timezone.utc)


def role(value, fallback):
    return (str(value or "").strip() or fallback)[:ROLE_LENGTH]


def receipt(path, sha256):
    return {"provenance": PROVENANCE, "imported_from": f"engine ledger {path}", "sha256": sha256}


def item_cell(snapshot, item, header):
    row = item.row_json
    if isinstance(row, dict):
        return row.get(header)
    headers = snapshot.headers_json.get(item.queue, [])
    return row[headers.index(header)] if header in headers and headers.index(header) < len(row) else None


def import_findings(snapshot, user, path, stamp):
    rows, sha256 = read_ledger(path)
    items = {
        item.finding_key: item
        for item in ReviewItem.objects.filter(snapshot=snapshot, queue__in=FINDING_QUEUES)
        if item.finding_key
    }
    counts = {"created": 0, "kept": 0, "unsigned": 0, "not_in_snapshot": 0}
    for row in rows:
        review = row.get("review") or {}
        decision = review.get("decision")
        name = str(review.get("reviewer_name") or "").strip()
        if decision not in FindingDecision.Verdict.values or not name:
            counts["unsigned"] += 1
            continue
        item = items.get(row.get("finding_key"))
        if item is None:
            counts["not_in_snapshot"] += 1
            continue
        subject = row.get("review_subject_hash") or item.review_subject_hash
        if FindingDecision.objects.filter(finding_key=item.finding_key, review_subject_hash=subject).exists():
            counts["kept"] += 1
            continue
        common = {
            "mode": snapshot.mode,
            "finding_key": item.finding_key,
            "review_subject_hash": subject,
            "queue": item.queue,
            "decision": decision,
            "reviewer_role": role(review.get("reviewer_role"), "admin"),
            "reviewed_at": when(review.get("reviewed_at"), stamp),
            "note": review.get("correction_note") or "",
            "created_by": user,
            "authoritative_file_hash": sha256,
            "writer_receipt_json": receipt(path.name, sha256),
        }
        if decision == FindingDecision.Verdict.REJECTED:
            stages = [(FindingDecision.Stage.CITATION, name)]
        else:
            stages = [
                (stage, str(review.get(f"{stage}_reviewer_name") or "").strip() or name)
                for stage in FindingDecision.Stage.values
            ]
        for stage, reviewer in stages:
            FindingDecision.objects.create(
                **common,
                review_stage=stage,
                reviewer_name=reviewer,
                citation_checked=bool(review.get("citation_checked")) and stage == "citation",
                mapping_checked=bool(review.get("mapping_checked")) and stage == "mapping",
                status_checked=bool(review.get("status_checked")) and stage == "status",
            )
        counts["created"] += 1
    return counts


def import_zone3(snapshot, user, path, stamp):
    rows, sha256 = read_ledger(path)
    items = {
        item.stable_key: item
        for item in ReviewItem.objects.filter(snapshot=snapshot, queue=ReviewItem.Queue.ZONE3)
    }
    counts = {"created": 0, "kept": 0, "not_in_snapshot": 0, "no_score": 0}
    existing = set(Zone3Decision.objects.values_list("score_key", flat=True))
    for row in sorted(rows, key=lambda row: str(row.get("reviewed_at") or "")):
        key = zone3_key(row.get("economy"), row.get("indicator"), snapshot.mode)
        item = items.get(key)
        if item is None:
            counts["not_in_snapshot"] += 1
            continue
        if key in existing:
            counts["kept"] += 1
            continue
        score = row.get("score")
        if score in (None, ""):
            # An approval without a score ratifies the engine's deterministic score.
            score = item_cell(snapshot, item, "Deterministic score")
        try:
            score = Decimal(str(score))
        except (InvalidOperation, TypeError):
            counts["no_score"] += 1
            continue
        latest = Zone3Decision.objects.filter(score_key=key).order_by("-created_at").first()
        Zone3Decision.objects.create(
            mode=snapshot.mode,
            score_key=key,
            verdict=(
                Zone3Decision.Verdict.APPROVED
                if row.get("action") == "approve"
                else Zone3Decision.Verdict.OVERRIDDEN
            ),
            score=score,
            reasoning=row.get("reasoning") or row.get("note") or "",
            reviewer_name=str(row.get("reviewer_name") or "").strip() or IMPORT_USERNAME,
            reviewer_role=role(row.get("reviewer_role"), "mapping"),
            reviewed_at=when(row.get("reviewed_at"), stamp),
            created_by=user,
            supersedes=latest,
            authoritative_file_hash=sha256,
            writer_receipt_json=receipt(path.name, sha256),
        )
        counts["created"] += 1
    return counts


def import_recall(snapshot, user, path, stamp):
    rows, sha256 = read_ledger(path)
    items = set(
        ReviewItem.objects.filter(snapshot=snapshot, queue=ReviewItem.Queue.RECALL).values_list(
            "stable_key", flat=True
        )
    )
    counts = {"created": 0, "kept": 0, "not_in_snapshot": 0}
    existing = set(RecallDecision.objects.values_list("recall_key", flat=True))
    for row in sorted(rows, key=lambda row: str(row.get("reviewed_at") or "")):
        key = row.get("recall_key")
        if key not in items or row.get("verdict") not in RecallDecision.Verdict.values:
            counts["not_in_snapshot"] += 1
            continue
        if key in existing:
            counts["kept"] += 1
            continue
        RecallDecision.objects.create(
            mode=snapshot.mode,
            recall_key=key,
            verdict=row["verdict"],
            reasoning=row.get("note") or row.get("reasoning") or "",
            reviewer_name=str(row.get("reviewer_name") or "").strip() or IMPORT_USERNAME,
            reviewer_role=role(row.get("reviewer_role"), "mapping"),
            reviewed_at=when(row.get("reviewed_at"), stamp),
            created_by=user,
            authoritative_file_hash=sha256,
            writer_receipt_json=receipt(path.name, sha256),
        )
        existing.add(key)
        counts["created"] += 1
    return counts


class Command(BaseCommand):
    help = "Load signed decisions from the engine's data/review files into the database (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--mode", choices=MODES, action="append",
                            help="mode to import (repeatable; default: all modes)")

    def handle(self, *args, **options):
        summary = {}
        stamp = datetime.now(dt_timezone.utc)
        for mode in options["mode"] or MODES:
            snapshot = EngineSnapshot.objects.filter(mode=mode, active=True).first()
            if snapshot is None:
                summary[mode] = "no active snapshot"
                continue
            folder = review_dir(mode)
            with transaction.atomic():
                user = import_user()
                summary[mode] = {
                    "findings": import_findings(snapshot, user, folder / "decisions.json", stamp),
                    "zone3": import_zone3(snapshot, user, folder / "zone3_decisions.json", stamp),
                    "recall": import_recall(snapshot, user, folder / "recall_decisions.json", stamp),
                }
        self.stdout.write(json.dumps(summary, sort_keys=True))
