"""Application-owned evidence identity and rerun reconciliation.

The engine remains an immutable input producer.  This module gives the ESCAP
application a durable identity that does not depend on an extractor's exact
snippet or source-artifact revision.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

from django.utils import timezone

from .keys import content_hash, normalized_part
from .models import (
    EngineSnapshot,
    EvidenceChange,
    EvidenceChangeDecision,
    EvidenceChangeSet,
    EvidenceIdentity,
    EvidenceRegistryEntry,
    EvidenceRevision,
)


def _text(value) -> str:
    return " ".join(str(value or "").split())


def _citation_key(value) -> str:
    value = unicodedata.normalize("NFKC", _text(value)).casefold()
    value = re.sub(
        r"^(?:section|sec(?:tion)?\.?|s\.?|article|art\.?|regulation|reg\.?)\s*",
        "",
        value,
    )
    return re.sub(r"\s+", "", value) or "n/a"


def finding_type(row: dict) -> str:
    snippet = str(row.get("Verbatim Snippet") or "")
    return (
        "absence"
        if "NO_EVIDENCE_FOUND" in snippet or row.get("search_coverage_manifest")
        else "provision"
    )


def technically_blocked(blocked: bool, row: dict) -> bool:
    """Is this evidence blocked by a technical fault (e.g. an unaligned citation)?

    Engine key maps exported before 30 Sep 2026 also flag every absence placeholder
    ("no evidence found") as blocked, because it has no citable snippet. That is not
    a fault: an absence conclusion is gated by its search-coverage manifest instead.
    """
    return bool(blocked) and finding_type(row) != "absence"


def identity_payload(row: dict, mode: str = "hybrid") -> dict:
    law_name = _text(row.get("Law Name") or row.get("Law/instrument"))
    instrument = _text(
        row.get("instrument_identity")
        or row.get("register_id")
        or row.get("Law Number / Ref")
    ) or law_name
    return {
        "contract": "clausechain-evidence-identity-v1",
        "economy": normalized_part(row.get("Economy")),
        "indicator_id": normalized_part(
            row.get("Indicator ID") or row.get("Indicator")
        ),
        "instrument_key": normalized_part(instrument),
        "citation_key": _citation_key(
            row.get("Article / Section") or row.get("Article/section")
        ),
        "finding_type": finding_type(row),
    } | ({"mode": mode} if mode != "hybrid" else {})  # hybrid hashes stay as they were


def evidence_identity_hash(row: dict, mode: str = "hybrid") -> str:
    return content_hash(identity_payload(row, mode))


def component_hashes(row: dict) -> dict[str, str]:
    absence = finding_type(row) == "absence"
    proof = row.get("citation_proof")
    if isinstance(proof, dict):
        proof = dict(proof)
        proof.pop("verified_at", None)
    coverage = row.get("search_coverage_manifest") if absence else None
    citation = {
        "contract": "clausechain-citation-review-v1",
        "law_name": row.get("Law Name"),
        "article_section": row.get("Article / Section"),
        "snippet": row.get("Verbatim Snippet"),
        "source_url": row.get("Source URL"),
        "source_artifact_id": row.get("source_artifact_id"),
        "citation_proof": proof,
        "absence_coverage": coverage,
    }
    mapping = {
        "contract": "clausechain-mapping-review-v1",
        "indicator_id": row.get("Indicator ID"),
        "mapping_rationale": row.get("Mapping Rationale"),
        "coverage": row.get("Coverage"),
        "discovery_tag": row.get("Discovery Tag"),
    }
    status = {
        "contract": "clausechain-status-review-v1",
        "status": row.get("Status"),
        "status_evidence": row.get("status_evidence"),
        "status_evidence_record": row.get("status_evidence_record"),
    }
    return {
        "citation": content_hash(citation),
        "mapping": content_hash(mapping),
        "status": content_hash(status),
        "coverage": content_hash(coverage) if coverage is not None else "",
    }


def _identity_defaults(row: dict, mode: str = "hybrid") -> dict:
    payload = identity_payload(row, mode)
    return {
        "economy": _text(row.get("Economy")),
        "indicator_id": _text(row.get("Indicator ID") or row.get("Indicator")),
        "instrument_key": payload["instrument_key"],
        "law_name": _text(row.get("Law Name") or row.get("Law/instrument")),
        "citation_key": payload["citation_key"],
        "finding_type": payload["finding_type"],
        "mode": mode,
    }


def reconcile_snapshot(snapshot: EngineSnapshot, previous_snapshot=None):
    """Create immutable revisions and a scoped old/new reconciliation report."""

    # Each model backend keeps its own registry: a Local import never marks
    # Hybrid evidence "not reproduced", and vice versa.
    mode = snapshot.mode
    existing = {
        entry.identity_id: entry
        for entry in EvidenceRegistryEntry.objects.select_related(
            "identity", "active_revision"
        ).filter(identity__mode=mode)
    }
    bootstrap = not existing
    declared_scope = snapshot.manifest_json.get("evaluated_scopes") or []
    scope = {
        (_text(item.get("economy")), _text(item.get("indicator_id")))
        for item in declared_scope
        if isinstance(item, dict) and item.get("economy") and item.get("indicator_id")
    }
    seen_identities = set()
    changes = []
    counts = Counter()
    change_set = EvidenceChangeSet.objects.create(
        snapshot=snapshot,
        previous_snapshot=previous_snapshot,
        scope_json=[],
        counts_json={},
    )

    for evidence in snapshot.evidence_rows.order_by("position"):
        row = evidence.row_json
        identity_hash = evidence_identity_hash(row, mode)
        identity, _ = EvidenceIdentity.objects.get_or_create(
            identity_hash=identity_hash, defaults=_identity_defaults(row, mode)
        )
        if identity.pk in seen_identities:
            raise ValueError(
                "Engine output contains more than one row for stable evidence identity "
                f"{identity_hash[:12]} ({identity.economy} {identity.indicator_id} "
                f"{identity.law_name} {identity.citation_key})."
            )
        seen_identities.add(identity.pk)
        scope.add((identity.economy, identity.indicator_id))
        hashes = component_hashes(row)
        revision = EvidenceRevision.objects.create(
            identity=identity,
            snapshot=snapshot,
            finding_key=evidence.finding_key,
            review_subject_hash=evidence.review_subject_hash,
            revision_hash=evidence.review_subject_hash or content_hash(row),
            citation_hash=hashes["citation"],
            mapping_hash=hashes["mapping"],
            status_hash=hashes["status"],
            coverage_hash=hashes["coverage"],
            row_json=row,
            proof_asset=evidence.proof_asset,
            blocked=evidence.blocked,
        )
        entry = existing.get(identity.pk)
        previous = entry.active_revision if entry else None
        if previous is None:
            kind = EvidenceChange.Kind.NEW
            invalidated = ["citation", "mapping", "status"]
        elif previous.revision_hash == revision.revision_hash:
            kind = EvidenceChange.Kind.UNCHANGED
            invalidated = []
        else:
            kind = EvidenceChange.Kind.REVISED
            invalidated = [
                stage
                for stage, field in (
                    ("citation", "citation_hash"),
                    ("mapping", "mapping_hash"),
                    ("status", "status_hash"),
                )
                if getattr(previous, field) != getattr(revision, field)
            ]
        counts[kind] += 1
        changes.append(
            EvidenceChange(
                change_set=change_set,
                identity=identity,
                previous_revision=previous,
                current_revision=revision,
                kind=kind,
                invalidated_stages_json=invalidated,
            )
        )
        if bootstrap:
            EvidenceRegistryEntry.objects.create(
                identity=identity,
                active_revision=revision,
                state=EvidenceRegistryEntry.State.CURRENT,
            )

    # A partial run is authoritative only for the economy/indicator pairs that
    # actually appear in it.  Evidence in every other scope remains current.
    for identity_id, entry in existing.items():
        identity = entry.identity
        if identity_id in seen_identities:
            continue
        if (identity.economy, identity.indicator_id) not in scope:
            continue
        counts[EvidenceChange.Kind.NOT_REPRODUCED] += 1
        changes.append(
            EvidenceChange(
                change_set=change_set,
                identity=identity,
                previous_revision=entry.active_revision,
                current_revision=None,
                kind=EvidenceChange.Kind.NOT_REPRODUCED,
                invalidated_stages_json=["citation", "mapping", "status"],
            )
        )
    EvidenceChange.objects.bulk_create(changes)
    change_set.scope_json = [
        {"economy": economy, "indicator_id": indicator}
        for economy, indicator in sorted(scope)
    ]
    change_set.counts_json = {
        key: counts.get(key, 0) for key in EvidenceChange.Kind.values
    }
    if bootstrap:
        change_set.state = EvidenceChangeSet.State.PUBLISHED
        change_set.published_at = timezone.now()
    change_set.save(
        update_fields=["scope_json", "counts_json", "state", "published_at"]
    )
    return change_set


def revision_for(finding_key: str, review_subject_hash: str = ""):
    queryset = EvidenceRevision.objects.filter(finding_key=finding_key)
    if review_subject_hash:
        queryset = queryset.filter(review_subject_hash=review_subject_hash)
    return queryset.select_related("identity").order_by("-created_at").first()


def latest_change_decision(change):
    return change.decisions.order_by("-created_at").first()


def publish_change_set(change_set: EvidenceChangeSet, user):
    """Atomically promote a reviewed candidate set into the current registry."""

    from django.core.exceptions import ValidationError
    from django.db import transaction

    from .decision_state import effective_finding_review

    if change_set.state == EvidenceChangeSet.State.PUBLISHED:
        return change_set
    changes = list(
        change_set.changes.select_related(
            "identity", "previous_revision", "current_revision"
        ).prefetch_related("decisions")
    )
    unresolved = []
    resolutions = []
    for change in changes:
        if change.kind == EvidenceChange.Kind.UNCHANGED:
            resolutions.append((change, "accept"))
            continue
        if change.kind in (EvidenceChange.Kind.NEW, EvidenceChange.Kind.REVISED):
            revision = change.current_revision
            if revision is None or technically_blocked(revision.blocked, revision.row_json):
                unresolved.append(f"{change.identity.identity_hash[:12]} is blocked")
                continue
            review = effective_finding_review(
                revision.finding_key,
                review_subject_hash=revision.review_subject_hash,
            )
            if review["decision"] not in {"approved", "rejected"}:
                unresolved.append(
                    f"{change.identity.identity_hash[:12]} has no final legal decision"
                )
                continue
            resolutions.append((change, review["decision"]))
            continue
        decision = latest_change_decision(change)
        if decision is None or decision.verdict not in {
            EvidenceChangeDecision.Verdict.RETAIN,
            EvidenceChangeDecision.Verdict.RETIRE,
        }:
            unresolved.append(
                f"{change.identity.identity_hash[:12]} needs a missing-evidence disposition"
            )
            continue
        resolutions.append((change, decision.verdict))
    if unresolved:
        raise ValidationError({"changes": unresolved})

    with transaction.atomic():
        for change, resolution in resolutions:
            entry = EvidenceRegistryEntry.objects.filter(
                identity=change.identity
            ).first()
            if resolution in {"accept", "approved"}:
                EvidenceRegistryEntry.objects.update_or_create(
                    identity=change.identity,
                    defaults={
                        "active_revision": change.current_revision,
                        "state": EvidenceRegistryEntry.State.CURRENT,
                    },
                )
            elif resolution == EvidenceChangeDecision.Verdict.RETIRE and entry:
                EvidenceRegistryEntry.objects.filter(pk=entry.pk).update(
                    state=EvidenceRegistryEntry.State.RETIRED
                )
            elif resolution == EvidenceChangeDecision.Verdict.RETAIN and entry:
                EvidenceRegistryEntry.objects.filter(pk=entry.pk).update(
                    state=EvidenceRegistryEntry.State.CURRENT
                )
            # A rejected new row never enters the registry; a rejected revision
            # leaves the last accepted revision current.
        EvidenceChangeSet.objects.filter(pk=change_set.pk).update(
            state=EvidenceChangeSet.State.PUBLISHED,
            published_at=timezone.now(),
            published_by=user,
        )
    change_set.refresh_from_db()
    return change_set
