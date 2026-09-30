from decimal import Decimal
import csv
import hashlib
import io
import json
import re
from urllib.parse import urlparse

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.permissions import BasePermission
from rest_framework.views import APIView

from .decision_state import bulk_effective_finding_decisions, effective_finding_review
from .decision_writer import (
    DecisionWriterConflict,
    DecisionWriterError,
    apply_authoritative_decision,
    current_authoritative_hash,
    decision_domain_lock,
)
from .engine_worker import EngineWorkerError, load_allowlist
from .importer import ALL_HYBRID_RUN_NAMES
from .mode import bundle_dir, current_mode, submission_dir
from .worker_supervisor import ensure_worker, worker_status
from .models import (
    CorrectionRequest,
    EngineSnapshot,
    EngineAction,
    EvidenceChange,
    EvidenceChangeDecision,
    EvidenceChangeSet,
    EvidenceRegistryEntry,
    EvidenceRevision,
    EvidenceRow,
    FindingDecision,
    RecallDecision,
    ReviewItem,
    Release,
    RunRecord,
    SnapshotArtifact,
    Zone3Decision,
)
from .pagination import WorkspacePagination
from .roles import (
    decision_reviewer_role,
    has_review_role,
    is_admin,
    reviewer_identity,
    reviewer_roles,
)
from .registry import publish_change_set, technically_blocked
from .serializers import (
    CorrectionRequestWriteSerializer,
    EvidenceChangeDecisionWriteSerializer,
    FindingBulkDecisionWriteSerializer,
    FindingDecisionWriteSerializer,
    RecallDecisionWriteSerializer,
    Zone3DecisionWriteSerializer,
)


class AuthoritativeWriterUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_code = "authoritative_writer_unavailable"


class DecisionConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "decision_conflict"


class IsSuperuserPermission(BasePermission):
    """Engine actions (runs, replay, refresh, sources, cancels): the Admin role only."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and is_admin(request.user))


def active_snapshot(mode=None):
    """The active snapshot of the request's model backend (?mode=, default hybrid)."""
    mode = mode or current_mode()
    snapshot = EngineSnapshot.objects.filter(active=True, mode=mode).first()
    if snapshot is None:
        raise APIException(
            "No Local snapshot yet: open Runs (Local tab) and click Refresh snapshot."
            if mode == "local" else "No engine snapshot has been imported.",
            code="snapshot_unavailable",
        )
    return snapshot


def snapshot_identity(snapshot):
    return {
        "id": str(snapshot.pk),
        "schema_version": snapshot.schema_version,
        "generated_at": snapshot.generated_at.isoformat(),
        "imported_at": snapshot.imported_at.isoformat(),
        "source_hash": snapshot.source_hash,
        "bundle_hash": snapshot.bundle_hash,
        "engine_git_sha": snapshot.engine_git_sha,
        "stale": snapshot.stale,
        "mode": snapshot.mode,
    }


def latest_for(model, key_name, key):
    return model.objects.filter(**{key_name: key}).order_by("-created_at").first()


def serialize_decision(row, *, value_field):
    if row is None:
        return None
    payload = {
        "id": str(row.pk),
        value_field: str(getattr(row, value_field)),
        "reviewer_name": row.reviewer_name,
        "reviewer_role": row.reviewer_role,
        "reviewed_at": row.reviewed_at.isoformat(),
        "authoritative_file_hash": row.authoritative_file_hash,
        "supersedes_id": str(row.supersedes_id) if row.supersedes_id else None,
    }
    if isinstance(row, RecallDecision):
        payload.update(
            reasoning=row.reasoning,
            official_source_url=row.official_source_url,
        )
    elif isinstance(row, Zone3Decision):
        payload.update(score=str(row.score), reasoning=row.reasoning)
    return payload


def review_item_payload(item):
    result = {
        "id": item.pk,
        "position": item.position,
        "row": item.row_json,
        "stable_key": item.stable_key,
        "finding_key": item.finding_key or None,
        "review_subject_hash": item.review_subject_hash or None,
        "blocked": item.blocked,
        "block_reason": item.block_reason,
        "source_hash": item.source_hash,
    }
    if item.queue in (
        ReviewItem.Queue.NEW,
        ReviewItem.Queue.KNOWN,
        ReviewItem.Queue.ABSENCE,
    ):
        result["review_state"] = effective_finding_review(
            item.finding_key, review_subject_hash=item.review_subject_hash
        )
        revision = EvidenceRevision.objects.filter(
            snapshot=item.snapshot,
            finding_key=item.finding_key,
            review_subject_hash=item.review_subject_hash,
        ).first()
        change = (
            EvidenceChange.objects.filter(
                change_set__snapshot=item.snapshot,
                current_revision=revision,
            ).first()
            if revision
            else None
        )
        result["registry_change"] = (
            {
                "kind": change.kind,
                "invalidated_stages": change.invalidated_stages_json,
                "identity_hash": change.identity.identity_hash,
            }
            if change
            else None
        )
        eligibility_reason = finding_ineligibility(item, item.snapshot)
        result["approval_eligibility"] = {
            "eligible": not bool(eligibility_reason),
            "reason": eligibility_reason,
        }
        correction = (
            CorrectionRequest.objects.filter(
                finding_key=item.finding_key,
                review_subject_hash=item.review_subject_hash,
            )
            .order_by("-requested_at")
            .first()
        )
        result["latest_correction"] = (
            {
                "id": str(correction.pk),
                "explanation": correction.explanation,
                "requested_by": correction.requested_by.full_name,
                "requested_at": correction.requested_at.isoformat(),
            }
            if correction
            else None
        )
    elif item.queue == ReviewItem.Queue.RECALL:
        result["latest_decision"] = serialize_decision(
            latest_for(RecallDecision, "recall_key", item.stable_key),
            value_field="verdict",
        )
    else:
        result["latest_decision"] = serialize_decision(
            latest_for(Zone3Decision, "score_key", item.stable_key),
            value_field="verdict",
        )
    return result


def item_is_decided(item):
    if item.queue in (
        ReviewItem.Queue.NEW,
        ReviewItem.Queue.KNOWN,
        ReviewItem.Queue.ABSENCE,
    ):
        return effective_finding_review(
            item.finding_key, review_subject_hash=item.review_subject_hash
        )["decision"] is not None
    model, key_name = (
        (RecallDecision, "recall_key")
        if item.queue == ReviewItem.Queue.RECALL
        else (Zone3Decision, "score_key")
    )
    return model.objects.filter(**{key_name: item.stable_key}).exists()


def registry_summary(snapshot):
    entries = list(
        EvidenceRegistryEntry.objects.select_related("identity", "active_revision")
        .filter(identity__mode=snapshot.mode)
    )
    current_revisions = [
        entry.active_revision
        for entry in entries
        if entry.state == EvidenceRegistryEntry.State.CURRENT
    ]
    verdicts = bulk_effective_finding_decisions(current_revisions)
    states = {
        "approved": 0,
        "rejected": 0,
        "decision_unrecorded": 0,
        "blocked": 0,
    }
    for entry in entries:
        if entry.state != EvidenceRegistryEntry.State.CURRENT:
            continue
        revision = entry.active_revision
        if technically_blocked(revision.blocked, revision.row_json):
            states["blocked"] += 1
            continue
        decision = verdicts.get((revision.finding_key, revision.review_subject_hash))
        if decision == "approved":
            states["approved"] += 1
        elif decision == "rejected":
            states["rejected"] += 1
        else:
            states["decision_unrecorded"] += 1
    try:
        change_set = snapshot.evidence_change_set
    except EvidenceChangeSet.DoesNotExist:
        change_set = None
    change_payload = None
    if change_set:
        actionable = list(
            change_set.changes.exclude(kind=EvidenceChange.Kind.UNCHANGED)
            .select_related("current_revision")
            .prefetch_related("decisions")
        )
        candidate_verdicts = bulk_effective_finding_decisions(
            change.current_revision
            for change in actionable
            if change.current_revision is not None
        )
        resolved = 0
        for change in actionable:
            if change.kind == EvidenceChange.Kind.NOT_REPRODUCED:
                decision_rows = list(change.decisions.all())
                resolution = decision_rows[-1] if decision_rows else None
                resolved += int(
                    resolution is not None
                    and resolution.verdict
                    in {
                        EvidenceChangeDecision.Verdict.RETAIN,
                        EvidenceChangeDecision.Verdict.RETIRE,
                    }
                )
            elif change.current_revision:
                decision = candidate_verdicts.get(
                    (
                        change.current_revision.finding_key,
                        change.current_revision.review_subject_hash,
                    )
                )
                resolved += int(decision is not None)
        change_payload = {
            "id": str(change_set.pk),
            "state": change_set.state,
            "scope": change_set.scope_json,
            "counts": change_set.counts_json,
            "attention": {"resolved": resolved, "total": len(actionable)},
            "created_at": change_set.created_at.isoformat(),
            "published_at": (
                change_set.published_at.isoformat() if change_set.published_at else None
            ),
        }
    return {
        "total": len(entries),
        "current": sum(
            entry.state == EvidenceRegistryEntry.State.CURRENT for entry in entries
        ),
        "not_reproduced": sum(
            entry.state == EvidenceRegistryEntry.State.NOT_REPRODUCED
            for entry in entries
        ),
        "retired": sum(
            entry.state == EvidenceRegistryEntry.State.RETIRED for entry in entries
        ),
        **states,
        "change_set": change_payload,
    }


class SummaryView(APIView):
    def get(self, request):
        snapshot = active_snapshot()
        all_items = list(snapshot.review_items.all())
        revisions = list(snapshot.evidence_revisions.all())
        finding_verdicts = bulk_effective_finding_decisions(revisions)
        revision_by_key = {revision.finding_key: revision for revision in revisions}
        recall_decided = set(
            RecallDecision.objects.filter(
                recall_key__in=[
                    item.stable_key
                    for item in all_items
                    if item.queue == ReviewItem.Queue.RECALL
                ]
            ).values_list("recall_key", flat=True)
        )
        zone_decided = set(
            Zone3Decision.objects.filter(
                score_key__in=[
                    item.stable_key
                    for item in all_items
                    if item.queue == ReviewItem.Queue.ZONE3
                ]
            ).values_list("score_key", flat=True)
        )

        def decided(item):
            if item.queue in (
                ReviewItem.Queue.NEW,
                ReviewItem.Queue.KNOWN,
                ReviewItem.Queue.ABSENCE,
            ):
                revision = revision_by_key.get(item.finding_key)
                if revision is None:
                    return item_is_decided(item)
                return finding_verdicts.get(
                    (revision.finding_key, revision.review_subject_hash)
                ) is not None
            if item.queue == ReviewItem.Queue.RECALL:
                return item.stable_key in recall_decided
            return item.stable_key in zone_decided

        progress = {}
        for queue in ReviewItem.Queue.values:
            items = [item for item in all_items if item.queue == queue]
            progress[queue] = {
                "decided": sum(decided(item) for item in items),
                "total": len(items),
            }
        return Response(
            {
                "snapshot": snapshot_identity(snapshot),
                "counts": snapshot.counts_json,
                "refuter_status": snapshot.refuter_status,
                "champion": snapshot.champion_json,
                "progress": progress,
                "runs": [serialize_run(record) for record in snapshot.run_records.all()],
                "registry": registry_summary(snapshot),
                "reviewer_roles": reviewer_roles(request.user),
            }
        )


def evidence_change_payload(change):
    latest = change.decisions.order_by("-created_at").first()
    revision = change.current_revision
    row = revision.row_json if revision else {}
    queue = None
    if revision:
        if change.identity.finding_type == "absence":
            queue = ReviewItem.Queue.ABSENCE
        elif str(row.get("Discovery Tag") or "").upper() == "NEW":
            queue = ReviewItem.Queue.NEW
        else:
            queue = ReviewItem.Queue.KNOWN
    review = (
        effective_finding_review(
            revision.finding_key, review_subject_hash=revision.review_subject_hash
        )
        if revision
        else None
    )
    return {
        "id": str(change.pk),
        "kind": change.kind,
        "invalidated_stages": change.invalidated_stages_json,
        "identity": {
            "id": str(change.identity_id),
            "identity_hash": change.identity.identity_hash,
            "economy": change.identity.economy,
            "indicator_id": change.identity.indicator_id,
            "law_name": change.identity.law_name,
            "citation": change.identity.citation_key,
            "finding_type": change.identity.finding_type,
        },
        "previous_finding_key": (
            change.previous_revision.finding_key if change.previous_revision else None
        ),
        "current_finding_key": revision.finding_key if revision else None,
        "review_queue": queue,
        "review_state": review,
        "latest_decision": (
            {
                "id": str(latest.pk),
                "verdict": latest.verdict,
                "comment": latest.comment,
                "reviewer_name": latest.reviewer_name,
                "created_at": latest.created_at.isoformat(),
            }
            if latest
            else None
        ),
    }


class EvidenceChangeSetView(APIView):
    def get(self, request):
        snapshot = active_snapshot()
        try:
            change_set = snapshot.evidence_change_set
        except EvidenceChangeSet.DoesNotExist:
            raise APIException(
                "The active engine snapshot has not been reconciled into the evidence registry."
            )
        changes = change_set.changes.select_related(
            "identity", "previous_revision", "current_revision"
        ).prefetch_related("decisions")
        kind = str(request.query_params.get("kind") or "")
        economy = str(request.query_params.get("economy") or "")
        if kind:
            if kind not in EvidenceChange.Kind.values:
                raise ValidationError({"kind": "Unknown evidence-change kind."})
            changes = changes.filter(kind=kind)
        if economy:
            changes = changes.filter(identity__economy=economy)
        return Response(
            {
                "snapshot": snapshot_identity(snapshot),
                "change_set": registry_summary(snapshot)["change_set"],
                "results": [evidence_change_payload(change) for change in changes],
            }
        )


class EvidenceChangeDecisionView(APIView):
    def post(self, request, change_id):
        if not any(
            has_review_role(request.user, role)
            for role in ("citation", "mapping", "status")
        ):
            raise PermissionDenied("A reviewer role is required.")
        serializer = EvidenceChangeDecisionWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        change = get_object_or_404(
            EvidenceChange.objects.select_related("change_set"), pk=change_id
        )
        if change.change_set.snapshot_id != active_snapshot().pk:
            raise ValidationError({"change": "This change is not in the active update."})
        if change.change_set.state != EvidenceChangeSet.State.DRAFT:
            raise ValidationError({"change": "This update has already been published."})
        if change.kind != EvidenceChange.Kind.NOT_REPRODUCED:
            raise ValidationError(
                {"change": "New and revised evidence is decided in legal review."}
            )
        allowed = {
            EvidenceChangeDecision.Verdict.RETAIN,
            EvidenceChangeDecision.Verdict.RETIRE,
            EvidenceChangeDecision.Verdict.INVESTIGATE,
        }
        if data["verdict"] not in allowed:
            raise ValidationError({"verdict": "Choose retain, retire, or investigate."})
        latest = change.decisions.order_by("-created_at").first()
        concurrency_check(latest, data.pop("expected_latest_decision_id"))
        reviewer_name, _ = reviewer_identity(request.user)
        row = EvidenceChangeDecision.objects.create(
            change=change,
            reviewer_name=reviewer_name,
            created_by=request.user,
            supersedes=latest,
            **data,
        )
        return Response(evidence_change_payload(change), status=status.HTTP_201_CREATED)


class EvidenceChangeSetPublishView(APIView):
    permission_classes = [IsSuperuserPermission]

    def post(self, request):
        snapshot = active_snapshot()
        try:
            change_set = snapshot.evidence_change_set
        except EvidenceChangeSet.DoesNotExist:
            raise ValidationError({"snapshot": "No reconciliation is available."})
        try:
            publish_change_set(change_set, request.user)
        except DjangoValidationError as exc:
            payload = exc.message_dict if hasattr(exc, "message_dict") else exc.messages
            raise ValidationError(payload) from exc
        return Response({"registry": registry_summary(snapshot)})


def artifact_payload(artifact, *, include_content=False):
    payload = {
        "key": artifact.key,
        "category": artifact.category,
        "source_path": artifact.source_path,
        "media_type": artifact.media_type,
        "byte_size": artifact.byte_size,
        "sha256": artifact.sha256,
        "generated_at": artifact.generated_at.isoformat() if artifact.generated_at else None,
        "imported_at": artifact.imported_at.isoformat(),
    }
    if include_content:
        payload.update(raw_text=artifact.raw_text, parsed=artifact.parsed_json)
    return payload


class OpsStatsView(APIView):
    def get(self, request):
        snapshot = active_snapshot()
        artifact = get_object_or_404(snapshot.artifacts, key="ops-stats")
        return Response({"snapshot": snapshot_identity(snapshot), "ops_stats": artifact.parsed_json, "artifact": artifact_payload(artifact)})


class WorkspaceConfigView(APIView):
    def get(self, request):
        snapshot = active_snapshot()
        jurisdictions = []
        for code in ("sg", "my", "au"):
            artifact = get_object_or_404(snapshot.artifacts, key=f"jurisdiction-{code}")
            jurisdictions.append({**artifact_payload(artifact, include_content=True), "code": code.upper()})
        seeds = get_object_or_404(snapshot.artifacts, key="seeds")
        return Response({"snapshot": snapshot_identity(snapshot), "jurisdictions": jurisdictions, "seeds": artifact_payload(seeds, include_content=True)})


class RawArtifactListView(APIView):
    def get(self, request):
        snapshot = active_snapshot()
        return Response({"snapshot": snapshot_identity(snapshot), "results": [artifact_payload(row) for row in snapshot.artifacts.all()]})


class RawArtifactDetailView(APIView):
    def get(self, request, artifact_key):
        snapshot = active_snapshot()
        artifact = get_object_or_404(snapshot.artifacts, key=artifact_key)
        return Response({"snapshot": snapshot_identity(snapshot), "artifact": artifact_payload(artifact, include_content=True)})


class RawArtifactDownloadView(APIView):
    def get(self, request, artifact_key):
        snapshot = active_snapshot()
        artifact = get_object_or_404(snapshot.artifacts, key=artifact_key)
        suffix = ".yaml" if artifact.media_type == "application/yaml" else ".json"
        response = HttpResponse(artifact.raw_text.encode("utf-8"), content_type=f"{artifact.media_type}; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{artifact.key}{suffix}"'
        response["X-Content-SHA256"] = artifact.sha256
        response["X-Content-Type-Options"] = "nosniff"
        return response


def serialize_ledger_event(row):
    if isinstance(row, FindingDecision):
        return {"id": str(row.pk), "event_type": "finding_decision", "domain": "findings", "key": row.finding_key, "action": row.decision, "stage": row.review_stage, "reviewer_name": row.reviewer_name, "reviewer_role": row.reviewer_role, "occurred_at": row.reviewed_at.isoformat(), "authoritative_file_hash": row.authoritative_file_hash, "writer_receipt": row.writer_receipt_json, "supersedes_id": str(row.supersedes_id) if row.supersedes_id else None}
    if isinstance(row, RecallDecision):
        return {"id": str(row.pk), "event_type": "recall_decision", "domain": "recall", "key": row.recall_key, "action": row.verdict, "reviewer_name": row.reviewer_name, "reviewer_role": row.reviewer_role, "occurred_at": row.reviewed_at.isoformat(), "authoritative_file_hash": row.authoritative_file_hash, "writer_receipt": row.writer_receipt_json, "supersedes_id": str(row.supersedes_id) if row.supersedes_id else None}
    if isinstance(row, Zone3Decision):
        return {"id": str(row.pk), "event_type": "zone3_decision", "domain": "zone3", "key": row.score_key, "action": row.verdict, "score": str(row.score), "reviewer_name": row.reviewer_name, "reviewer_role": row.reviewer_role, "occurred_at": row.reviewed_at.isoformat(), "authoritative_file_hash": row.authoritative_file_hash, "writer_receipt": row.writer_receipt_json, "supersedes_id": str(row.supersedes_id) if row.supersedes_id else None}
    if isinstance(row, CorrectionRequest):
        return {"id": str(row.pk), "event_type": "correction_request", "domain": "findings", "key": row.finding_key, "action": "correction_requested", "reviewer_name": row.requested_by.full_name, "reviewer_role": "requester", "occurred_at": row.requested_at.isoformat(), "authoritative_file_hash": row.authoritative_file_hash, "writer_receipt": row.writer_receipt_json, "supersedes_id": str(row.supersedes_id) if row.supersedes_id else None}
    return {"id": str(row.pk), "event_type": "release", "domain": "release", "key": str(row.pk), "action": row.state, "reviewer_name": row.created_by.full_name, "reviewer_role": "release_owner", "occurred_at": row.created_at.isoformat(), "authoritative_file_hash": row.bundle_hash, "writer_receipt": {}, "bundle_manifest": row.engine_manifest_json, "final_artifact_hashes": row.final_artifact_hashes_json, "snapshot_id": str(row.snapshot_id) if row.snapshot_id else None, "supersedes_id": str(row.supersedes_id) if row.supersedes_id else None}


class LedgerView(APIView):
    pagination_class = WorkspacePagination

    def get(self, request):
        mode = current_mode()
        rows = [*FindingDecision.objects.filter(mode=mode), *RecallDecision.objects.filter(mode=mode), *Zone3Decision.objects.filter(mode=mode), *CorrectionRequest.objects.filter(mode=mode), *Release.objects.filter(snapshot__mode=mode)]
        rows.sort(key=lambda row: getattr(row, "reviewed_at", None) or getattr(row, "requested_at", None) or row.created_at, reverse=True)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(rows, request, view=self)
        return Response(paginator.response_payload([serialize_ledger_event(row) for row in page]))


def graph_artifact(snapshot):
    return get_object_or_404(snapshot.artifacts, key="neo4j-graph-snapshot")


class KnowledgeGraphView(APIView):
    def get(self, request):
        snapshot = active_snapshot()
        artifact = graph_artifact(snapshot)
        graph = artifact.parsed_json or {}
        return Response({"snapshot": snapshot_identity(snapshot), "artifact": artifact_payload(artifact), "status": graph.get("status", "unavailable"), "origin": graph.get("origin", "neo4j"), "extracted_at": graph.get("extracted_at"), "schema_version": graph.get("schema_version"), "checks": graph.get("checks") or {}, "counts": graph.get("counts") or {}, "expected": graph.get("expected") or {}, "reason": graph.get("reason"), "node_count": len(graph.get("nodes") or []), "edge_count": len(graph.get("edges") or []), "lenses": ["sg-pdpa-p6-i4", "p7-i5", "new-baseline", "cross-references"]})


class KnowledgeGraphSubgraphView(APIView):
    def get(self, request):
        snapshot = active_snapshot()
        graph = graph_artifact(snapshot).parsed_json or {}
        nodes = list(graph.get("nodes") or [])[:500]
        edges = list(graph.get("edges") or [])[:1000]
        economy = str(request.query_params.get("economy") or "").casefold()
        indicator = str(request.query_params.get("indicator") or "").casefold()
        law = str(request.query_params.get("law") or "").casefold()
        finding_key = str(request.query_params.get("finding_key") or "")
        relationship = str(request.query_params.get("relationship") or "").upper()
        lens = str(request.query_params.get("lens") or "")
        if relationship and relationship not in {"HAS_SECTION", "HAS_PROVISION", "MAPS_TO", "EVIDENCED_BY", "KNOWN_AS", "NEW_RELATIVE_TO", "CROSS_REFERENCES", "AMENDS", "REPEALS", "SUPERSEDES", "EXCEPTION_TO", "QUALIFIES"}:
            raise ValidationError({"relationship": "Unknown relationship type."})
        if lens == "sg-pdpa-p6-i4":
            economy, law = "singapore", "personal data protection"
        elif lens == "p7-i5":
            indicator = "p7-i5"
        elif lens == "new-baseline":
            relationship = "NEW_RELATIVE_TO"
        elif lens == "cross-references":
            relationship = "CROSS_REFERENCES"
        elif lens:
            raise ValidationError({"lens": "Unknown graph lens."})
        if relationship:
            edges = [edge for edge in edges if edge.get("type") == relationship]
            connected = {value for edge in edges for value in (edge.get("source"), edge.get("target"))}
            nodes = [node for node in nodes if node.get("id") in connected]
        if any((economy, indicator, law, finding_key)):
            seeds = set()
            for node in nodes:
                props = node.get("properties") or {}
                haystack = {key: str(value).casefold() for key, value in props.items()}
                if economy and economy not in haystack.get("economy", ""): continue
                if law and law not in (haystack.get("law_name", "") + " " + haystack.get("law", "")): continue
                if indicator and indicator not in haystack.get("indicator", ""): continue
                if finding_key and finding_key != str(props.get("finding_key") or ""): continue
                seeds.add(node.get("id"))
            for _ in range(2):
                seeds.update(value for edge in edges if edge.get("source") in seeds or edge.get("target") in seeds for value in (edge.get("source"), edge.get("target")))
            nodes = [node for node in nodes if node.get("id") in seeds]
            node_ids = {node.get("id") for node in nodes}
            edges = [edge for edge in edges if edge.get("source") in node_ids and edge.get("target") in node_ids]

        # A capped or filtered graph must be closed over its relationships.
        # D3's forceLink throws when even one edge references a node omitted by
        # the payload, so deduplicate nodes first and always remove orphan edges.
        closed_nodes = []
        node_ids = set()
        for node in nodes[:500]:
            node_id = node.get("id")
            if not isinstance(node_id, str) or not node_id or node_id in node_ids:
                continue
            node_ids.add(node_id)
            closed_nodes.append(node)
        closed_edges = []
        edge_ids = set()
        for edge in edges:
            source = edge.get("source")
            target = edge.get("target")
            edge_id = edge.get("id")
            if source not in node_ids or target not in node_ids:
                continue
            if isinstance(edge_id, str) and edge_id in edge_ids:
                continue
            if isinstance(edge_id, str):
                edge_ids.add(edge_id)
            closed_edges.append(edge)
            if len(closed_edges) == 1000:
                break
        return Response({"snapshot": snapshot_identity(snapshot), "status": graph.get("status", "unavailable"), "nodes": closed_nodes, "edges": closed_edges, "caps": {"nodes": 500, "edges": 1000}})


class ReviewQueueView(APIView):
    pagination_class = WorkspacePagination

    def get(self, request, queue):
        if queue not in ReviewItem.Queue.values:
            raise ValidationError({"queue": "Unknown review queue."})
        snapshot = active_snapshot()
        items = list(snapshot.review_items.filter(queue=queue))
        if request.query_params.get("undecided") == "1":
            items = [item for item in items if not item_is_decided(item)]

        if queue == ReviewItem.Queue.NEW:
            headers = snapshot.headers_json.get(queue, [])
            try:
                verdict_index = headers.index("Refuter verdict")
            except ValueError:
                verdict_index = None
            if verdict_index is not None:
                rank = {"SPLIT": 0, "KEEP": 1, "REJECT": 2}
                items.sort(
                    key=lambda item: (
                        rank.get(
                            (
                                str(item.row_json[verdict_index]).upper()
                                if verdict_index < len(item.row_json)
                                else ""
                            ),
                            3,
                        ),
                        item.position,
                    )
                )

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(items, request, view=self)
        return Response(
            paginator.response_payload(
                [review_item_payload(item) for item in page],
                queue=queue,
                headers=snapshot.headers_json.get(queue, []),
                snapshot_id=str(snapshot.pk),
                snapshot_hash=snapshot.source_hash,
            )
        )


class EvidenceListView(APIView):
    pagination_class = WorkspacePagination

    def get(self, request):
        rows = filtered_evidence_rows(active_snapshot(), request.query_params)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(rows, request, view=self)
        return Response(
            paginator.response_payload(
                [
                    {
                        "finding_key": row.finding_key,
                        "row": row.row_json,
                        "blocked": technically_blocked(row.blocked, row.row_json),
                        "proof_asset_url": proof_url(row.proof_asset),
                        "source_hash": row.source_hash,
                    }
                    for row in page
                ]
            )
        )


def proof_url(proof_asset):
    if not proof_asset:
        return None
    filename = proof_asset.removeprefix("assets/")
    if not PROOF_ASSET_PATTERN.fullmatch(filename):
        return None
    return f"/api/workspace/proof/{filename}/"


PROOF_ASSET_PATTERN = re.compile(r"[0-9a-f]{64}\.png", re.IGNORECASE)
EVIDENCE_FILTERS = {
    "economy": "Economy",
    "indicator": "Indicator ID",
    "tag": "Discovery Tag",
    "status": "Status",
}


def filtered_evidence_rows(snapshot, params):
    """Apply the shared evidence filter grammar used by list and match navigation."""
    rows = list(snapshot.evidence_rows.all())
    queue = params.get("queue")
    if queue:
        if queue not in ReviewItem.Queue.values:
            raise ValidationError({"queue": "Unknown review queue."})
        queue_keys = set(
            snapshot.review_items.filter(queue=queue)
            .exclude(finding_key="")
            .values_list("finding_key", flat=True)
        )
        rows = [row for row in rows if row.finding_key in queue_keys]
    for query_name, field_name in EVIDENCE_FILTERS.items():
        value = params.get(query_name)
        if value:
            accepted = {
                item.strip().casefold() for item in str(value).split(",") if item.strip()
            }
            rows = [
                row
                for row in rows
                if str(row.row_json.get(field_name) or "").casefold() in accepted
            ]
    pillar = params.get("pillar")
    if pillar:
        accepted_pillars = {
            item.strip().casefold() for item in str(pillar).split(",") if item.strip()
        }
        rows = [
            row
            for row in rows
            if any(
                str(row.row_json.get("Indicator ID") or "").casefold().startswith(
                    f"p{value}-"
                )
                for value in accepted_pillars
            )
        ]
    return rows


def source_sha256(row, fallback):
    proof = row.get("citation_proof") or {}
    value = str(
        proof.get("source_sha256")
        or row.get("source_artifact_id")
        or fallback
        or ""
    )
    return value.removeprefix("sha256:")


def source_match_mode(evidence):
    proof = evidence.row_json.get("citation_proof") or {}
    alignment = str(proof.get("alignment_status") or "").casefold()
    if evidence.blocked or alignment in {"unaligned", "ambiguous", "review"}:
        return "blocked"
    if alignment == "anchor":
        return "anchor"
    if alignment == "exact":
        return "exact"
    return "blocked"


def source_match_block_reason(evidence):
    review_item = (
        ReviewItem.objects.filter(
            snapshot=evidence.snapshot, finding_key=evidence.finding_key
        )
        .exclude(block_reason="")
        .first()
    )
    if review_item:
        return review_item.block_reason
    proof = evidence.row_json.get("citation_proof") or {}
    alignment = proof.get("alignment_status")
    if alignment in {"unaligned", "ambiguous", "review"}:
        return f"Citation alignment is {alignment}; technical review is required."
    return "A complete citation proof is not available for this evidence row."


def serialize_source_match(evidence, *, navigation, review_item):
    row = evidence.row_json
    proof = row.get("citation_proof") or {}
    mode = source_match_mode(evidence)
    asset_url = proof_url(evidence.proof_asset) if mode == "exact" else None
    return {
        "finding_key": evidence.finding_key,
        "row": row,
        "blocked": mode == "blocked",
        "block_reason": source_match_block_reason(evidence) if mode == "blocked" else "",
        "proof_asset_url": asset_url,
        "proof_asset_available": bool(
            asset_url
            and (bundle_dir() / evidence.proof_asset).is_file()
        ),
        "source_hash": evidence.source_hash,
        "source_sha256": source_sha256(row, evidence.source_hash),
        "match": {
            "mode": mode,
            "label": {
                "exact": "VERBATIM · exact",
                "anchor": "VERBATIM · anchor",
                "blocked": "blocked",
            }[mode],
            "alignment_status": proof.get("alignment_status"),
            "alignment_score": proof.get("alignment_score"),
            "page_number": proof.get("page_number"),
            "anchor": proof.get("anchor"),
            "article_path": proof.get("article_path") or [],
            "span_ids": proof.get("span_ids") or [],
            "bboxes": proof.get("bboxes") or [],
            "verified_at": proof.get("verified_at"),
        },
        "source": {
            "official_url": row.get("Source URL"),
            "archived_copy": row.get("archived_copy"),
            "access_date": row.get("access_date"),
            "status": row.get("Status"),
            "status_evidence": row.get("status_evidence"),
            "status_evidence_record": row.get("status_evidence_record"),
            "citation_tier": row.get("citation_tier"),
            "source_artifact_id": row.get("source_artifact_id"),
        },
        "review_state": effective_finding_review(
            evidence.finding_key, review_subject_hash=evidence.review_subject_hash
        ),
        "review_queue": review_item.queue,
        "stable_key": review_item.stable_key,
        "approval_eligibility": {
            "eligible": not bool(finding_ineligibility(review_item, evidence.snapshot)),
            "reason": finding_ineligibility(review_item, evidence.snapshot),
        },
        "latest_correction": (
            {
                "id": str(correction.pk),
                "explanation": correction.explanation,
                "requested_by": correction.requested_by.full_name,
                "requested_at": correction.requested_at.isoformat(),
            }
            if (
                correction := CorrectionRequest.objects.filter(
                    finding_key=evidence.finding_key,
                    review_subject_hash=evidence.review_subject_hash,
                ).order_by("-requested_at").first()
            )
            else None
        ),
        "navigation": navigation,
    }


class EvidenceDetailView(APIView):
    def get(self, request, finding_key):
        row = get_object_or_404(
            EvidenceRow, snapshot=active_snapshot(), finding_key=finding_key
        )
        return Response(
            {
                "finding_key": row.finding_key,
                "row": row.row_json,
                "blocked": technically_blocked(row.blocked, row.row_json),
                "proof_asset_url": proof_url(row.proof_asset),
                "source_hash": row.source_hash,
                "review_state": effective_finding_review(
                    row.finding_key, review_subject_hash=row.review_subject_hash
                ),
            }
        )


class SourceMatchView(APIView):
    def get(self, request, finding_key):
        snapshot = active_snapshot()
        evidence = get_object_or_404(
            EvidenceRow, snapshot=snapshot, finding_key=finding_key
        )
        requested_queue = str(request.query_params.get("queue") or "")
        review_items = ReviewItem.objects.filter(
            snapshot=snapshot,
            finding_key=finding_key,
            queue__in=(ReviewItem.Queue.NEW, ReviewItem.Queue.KNOWN, ReviewItem.Queue.ABSENCE),
        )
        review_item = (
            review_items.filter(queue=requested_queue).first()
            if requested_queue in (ReviewItem.Queue.NEW, ReviewItem.Queue.KNOWN, ReviewItem.Queue.ABSENCE)
            else review_items.first()
        )
        if review_item is None:
            raise Http404
        rows = filtered_evidence_rows(snapshot, request.query_params)
        keys = [row.finding_key for row in rows]
        try:
            index = keys.index(finding_key)
        except ValueError:
            keys = [finding_key]
            index = 0
        navigation = {
            "position": index + 1,
            "total": len(keys),
            "previous_key": keys[index - 1] if index > 0 else None,
            "next_key": keys[index + 1] if index + 1 < len(keys) else None,
        }
        return Response(
            serialize_source_match(
                evidence, navigation=navigation, review_item=review_item
            )
        )


class ProofAssetView(APIView):
    def get(self, request, filename):
        if not PROOF_ASSET_PATTERN.fullmatch(filename):
            raise Http404
        path = bundle_dir() / "assets" / filename
        if not path.is_file():
            raise Http404
        return FileResponse(path.open("rb"), content_type="image/png")


# One engine, two model backends. "hybrid" is the reviewed production path
# (commercial hosted models, data via the imported snapshot); "local" runs the
# same pipeline on the self-hosted open-weights model and is read straight from
# the worker's captured run envelopes. Labels are display-only.
RUN_MODES = {
    "hybrid": {
        "label": "Hybrid",
        "provider_profile": "hybrid_accuracy",
        "out_prefix": "final",
        "models": settings.ENGINE_MODE_LABELS.get("hybrid", ""),
    },
    "local": {
        "label": "Local",
        "provider_profile": "local_openweights",
        "out_prefix": "local",
        "models": settings.ENGINE_MODE_LABELS.get("local", ""),
    },
}


def request_mode(request, source=None):
    value = str((source if source is not None else request.query_params).get("mode") or "hybrid")
    if value not in RUN_MODES:
        raise ValidationError({"mode": f"Choose one of: {', '.join(RUN_MODES)}."})
    return value


def action_mode(request):
    """Mode of an engine action: the body's "mode", else ?mode=, else hybrid."""
    return request_mode(request, {"mode": request.data.get("mode") or request.query_params.get("mode")})


def actions_for_mode(mode):
    """A mode's actions; source downloads (corpus) serve both models, so both tabs show them."""
    queryset = EngineAction.objects.all()
    if mode == "hybrid":
        # A missing "mode" key (source downloads, older actions) must not read as
        # "local": in SQL the comparison is NULL, and exclude() would drop the row.
        return queryset.filter(~Q(arguments_json__mode="local") | Q(arguments_json__mode__isnull=True))
    return queryset.filter(Q(arguments_json__mode=mode) | Q(kind=EngineAction.Kind.CORPUS))


def serialize_modes():
    return [
        {"id": key, "label": value["label"], "models": value["models"]}
        for key, value in RUN_MODES.items()
    ]


class RunsView(APIView):
    def get(self, request):
        mode = request_mode(request)
        if mode == "hybrid":
            snapshot = active_snapshot()
            results = [serialize_run(record) for record in RunRecord.objects.filter(snapshot=snapshot)]
            champion = snapshot.champion_json
        else:
            results = [serialize_action_run(action) for action in local_run_actions(mode)]
            champion = {}
        return Response(
            {
                "mode": mode,
                "modes": serialize_modes(),
                "results": results,
                "champion": champion,
                "actions": [
                    serialize_engine_action(action)
                    for action in actions_for_mode(mode).filter(cleared_at__isnull=True)[:20]
                ],
                "worker": worker_status(),
                "can_launch": is_admin(request.user),
            }
        )


def local_run_actions(mode):
    """Succeeded run actions of a mode that captured an envelope, newest first."""
    return [
        action
        for action in actions_for_mode(mode).filter(
            kind=EngineAction.Kind.RUN, status=EngineAction.Status.SUCCEEDED
        )
        if action.result_json.get("findings") is not None
    ]


def serialize_action_run(action):
    envelope = action.result_json
    output = next(
        (value for key, value in (action.result_hashes_json or {}).items()
         if key.endswith("output.json")),
        {},
    )
    arguments = action.arguments_json
    return serialize_envelope(
        f"{arguments.get('out_prefix', 'local')}_{arguments.get('cc')}_p{arguments.get('pillar')}"
        f"@{action.finished_at.isoformat() if action.finished_at else action.pk}",
        envelope,
        {},
        output.get("sha256") or "",
    )


def serialize_run(record):
    return serialize_envelope(
        record.run_name, record.envelope_json, record.cost_json, record.source_hash
    )


def serialize_envelope(run_name, envelope, cost_json, source_hash):
    findings = envelope.get("findings") or []
    warnings = envelope.get("warnings") or []
    metadata = envelope.get("metadata") or {}
    cost = cost_json or metadata.get("cost_report") or {}
    discovery = {"NEW": 0, "KNOWN": 0}
    for finding in findings:
        tag = str(finding.get("Discovery Tag") or "").upper()
        if tag in discovery:
            discovery[tag] += 1
    model_versions = sorted(
        {
            str(finding.get("model_version"))
            for finding in findings
            if finding.get("model_version")
        }
    )
    return {
        "run_name": run_name,
        "run_id": envelope.get("run_id") or cost.get("run_id"),
        "provider_profile": envelope.get("provider_profile"),
        "country": envelope.get("country"),
        "pillar": envelope.get("pillar"),
        "generated_at": envelope.get("generated_at") or cost.get("at"),
        "rows_produced": len(findings),
        "discovery_counts": discovery,
        "warnings": warnings,
        "warning_count": len(warnings),
        "model_version": " + ".join(model_versions),
        "elapsed_seconds": metadata.get("elapsed_seconds") or cost.get("elapsed_seconds"),
        "total_usd": cost.get("total_usd"),
        "models": cost.get("models") or {},
        "pipeline_stats": metadata.get("pipeline_stats") or {},
        "source_hash": source_hash,
    }


TEMPLATE_COLUMNS = (
    "Economy",
    "Law Name",
    "Law Number / Ref",
    "Last Amended",
    "Indicator ID",
    "Article / Section",
    "Discovery Tag",
    "Location Reference",
    "Verbatim Snippet",
    "Mapping Rationale",
    "Source URL",
    "Confidence",
    "Notes",
)


def serialize_submission_row(evidence):
    row = evidence.row_json
    proof = row.get("citation_proof") or {}
    gates = proof.get("gate_results") or []
    return {
        "finding_key": evidence.finding_key,
        "template": {name: row.get(name) for name in TEMPLATE_COLUMNS},
        "row": row,
        "verification": {
            "source_domain": urlparse(str(row.get("Source URL") or "")).hostname,
            "citation_tier": row.get("citation_tier"),
            "match_mode": source_match_mode(evidence),
            "match_label": {
                "exact": "VERBATIM · exact",
                "anchor": "VERBATIM · anchor",
                "blocked": "blocked",
            }[source_match_mode(evidence)],
            "page_or_anchor": proof.get("page_number") or proof.get("anchor"),
            "source_sha256": source_sha256(row, evidence.source_hash),
            "access_date": row.get("access_date"),
            "status": row.get("Status"),
            "gates": gates,
            "gates_pass": bool(gates) and all(gate.get("status") == "PASS" for gate in gates),
            "blocked": source_match_mode(evidence) == "blocked",
        },
        "review_state": effective_finding_review(
            evidence.finding_key, review_subject_hash=evidence.review_subject_hash
        ),
    }


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def final_artifact_summary():
    root = submission_dir()
    csv_path = root / "consolidated_final.csv"
    json_path = root / "consolidated_final.json"
    if not csv_path.is_file() or not json_path.is_file():
        return {"available": False, "rows": 0, "csv_sha256": None, "json_sha256": None}
    try:
        with csv_path.open(encoding="utf-8", newline="") as handle:
            count = sum(1 for _ in csv.DictReader(handle))
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        json_count = len(payload.get("rows") or [])
    except (OSError, csv.Error, json.JSONDecodeError) as exc:
        return {"available": False, "rows": 0, "error": str(exc)}
    return {
        "available": count == json_count,
        "rows": count,
        "csv_sha256": file_sha256(csv_path),
        "json_sha256": file_sha256(json_path),
        "identity_counts_match": count == json_count,
    }


def serialize_release(release):
    if release is None:
        return None
    return {
        "id": str(release.pk),
        "state": release.state,
        "snapshot_id": str(release.snapshot_id) if release.snapshot_id else None,
        "bundle_hash": release.bundle_hash,
        "created_at": release.created_at.isoformat(),
        "frozen_at": release.frozen_at.isoformat() if release.frozen_at else None,
    }


class SubmissionView(APIView):
    pagination_class = WorkspacePagination

    def get(self, request):
        snapshot = active_snapshot()
        rows = filtered_evidence_rows(snapshot, request.query_params)
        query = str(request.query_params.get("q") or "").strip().casefold()
        if query:
            rows = [
                evidence
                for evidence in rows
                if query
                in " ".join(
                    str(evidence.row_json.get(field) or "")
                    for field in (
                        "Law Name", "Article / Section", "Verbatim Snippet",
                        "Indicator ID", "Economy"
                    )
                ).casefold()
            ]
        review_filter = str(request.query_params.get("review") or "").casefold()
        if review_filter:
            rows = [
                evidence
                for evidence in rows
                if str(effective_finding_review(
                    evidence.finding_key,
                    review_subject_hash=evidence.review_subject_hash,
                ).get("decision") or "pending").casefold()
                == review_filter
            ]
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(rows, request, view=self)
        return Response(
            paginator.response_payload(
                [serialize_submission_row(row) for row in page],
                template_columns=list(TEMPLATE_COLUMNS),
                snapshot={
                    "id": str(snapshot.pk),
                    "source_hash": snapshot.source_hash,
                    "stale": snapshot.stale,
                },
                final_artifacts=final_artifact_summary(),
                release=serialize_release(Release.objects.filter(snapshot__mode=current_mode()).first()),
            )
        )


def serialize_engine_action(action):
    return {
        "id": str(action.pk),
        "kind": action.kind,
        "status": action.status,
        "arguments": action.arguments_json,
        "mode": (action.arguments_json or {}).get("mode") or "hybrid",
        "requested_by": action.requested_by.full_name,
        "requested_at": action.requested_at.isoformat(),
        "started_at": action.started_at.isoformat() if action.started_at else None,
        "finished_at": action.finished_at.isoformat() if action.finished_at else None,
        "stdout": action.stdout,
        "result_hashes": action.result_hashes_json,
        "error": action.error,
        "cancel_requested_at": (
            action.cancel_requested_at.isoformat() if action.cancel_requested_at else None
        ),
        "cancelled_by": action.cancelled_by,
    }


class EngineActionsView(APIView):
    def get(self, request):
        return Response(
            {"results": [serialize_engine_action(row) for row in EngineAction.objects.all()[:50]]}
        )


class EngineActionCreateView(APIView):
    permission_classes = [IsSuperuserPermission]
    kind = None

    def action_arguments(self, request):
        raise NotImplementedError

    def post(self, request):
        arguments = self.action_arguments(request)
        with transaction.atomic():
            active = EngineAction.objects.select_for_update().filter(
                kind=self.kind,
                status__in=(EngineAction.Status.QUEUED, EngineAction.Status.RUNNING),
            )
            # The worker runs actions one at a time, in order, so several can wait
            # in the queue. Only a true duplicate is refused: the same run (it would
            # write the same output folder) or a second refresh/replay of one mode.
            if self.kind == EngineAction.Kind.RUN:
                active = active.filter(
                    arguments_json__economy=arguments["economy"],
                    arguments_json__pillar=arguments["pillar"],
                    arguments_json__mode=arguments["mode"],
                )
                conflict = "This economy and pillar is already queued or running in this mode."
            elif self.kind == EngineAction.Kind.CORPUS:
                active = active.filter(
                    arguments_json__economy=arguments["economy"],
                    arguments_json__action=arguments["action"],
                )
                conflict = "This is already queued or running for this economy."
            else:
                active = active.filter(arguments_json__mode=arguments.get("mode", "hybrid"))
                conflict = "This action is already queued or running for this mode."
            if active.exists():
                raise DecisionConflict(conflict)
            action = EngineAction.objects.create(
                kind=self.kind,
                arguments_json=arguments,
                requested_by=request.user,
            )
        # The action is committed and claimable; make sure something will run it.
        try:
            worker = ensure_worker()
        except OSError as exc:
            worker = worker_status() | {"started": False, "error": str(exc)[:300]}
        return Response(
            serialize_engine_action(action) | {"worker": worker},
            status=status.HTTP_202_ACCEPTED,
        )


ACTIVE_STATUSES = (EngineAction.Status.QUEUED, EngineAction.Status.RUNNING)


def worker_is_running(action, status):
    """True only when a live worker reports THIS action as its current one."""
    return bool(status.get("alive")) and status.get("current_action_id") == str(action.pk)


def cancel_action(action, user, *, worker_running_it):
    """Cancel one queued/running action (caller holds the row lock).

    Queued -> cancelled now. Running -> a stop request the worker executing it
    acts on within seconds. If no live worker is executing it (worker restarted
    or crashed mid-run), nothing will ever act on a request, so it is closed
    here instead of waiting for the lease to expire and the action to re-run."""
    now = timezone.now()
    action.cancelled_by = user.full_name or user.email
    if action.status == EngineAction.Status.QUEUED or not worker_running_it:
        action.status = EngineAction.Status.CANCELLED
        action.finished_at = now
        action.lease_expires_at = None
        action.error = f"Cancelled by {action.cancelled_by} before it ran." if not action.started_at \
            else f"Cancelled by {action.cancelled_by}; no worker was running it."
        action.save(update_fields=("status", "finished_at", "lease_expires_at", "error", "cancelled_by"))
    else:
        action.cancel_requested_at = now
        action.save(update_fields=("cancel_requested_at", "cancelled_by"))
    return action


class EngineActionCancelView(APIView):
    permission_classes = [IsSuperuserPermission]

    def post(self, request, action_id):
        status_now = worker_status()
        with transaction.atomic():
            action = get_object_or_404(EngineAction.objects.select_for_update(), pk=action_id)
            if action.status not in ACTIVE_STATUSES:
                raise DecisionConflict(f"This action already {action.status}.")
            cancel_action(action, request.user,
                          worker_running_it=worker_is_running(action, status_now))
        return Response(serialize_engine_action(action))


class EngineActionCancelAllView(APIView):
    """Cancel everything queued/running in one run mode and clear that mode's
    finished actions from the list (rows are kept; results stay visible)."""

    permission_classes = [IsSuperuserPermission]

    def post(self, request):
        mode = request_mode(request, request.data)
        status_now = worker_status()
        now = timezone.now()
        with transaction.atomic():
            active = list(actions_for_mode(mode).select_for_update().filter(status__in=ACTIVE_STATUSES))
            for action in active:
                cancel_action(action, request.user,
                              worker_running_it=worker_is_running(action, status_now))
            cleared = actions_for_mode(mode).filter(cleared_at__isnull=True).exclude(
                status__in=ACTIVE_STATUSES
            ).update(cleared_at=now)
        return Response({
            "mode": mode,
            "cancelled": sum(1 for action in active if action.status == EngineAction.Status.CANCELLED),
            "stopping": sum(1 for action in active if action.status == EngineAction.Status.RUNNING),
            "cleared": cleared,
        })


class EngineActionEventsView(APIView):
    """Live run console: events after ``?after=<seq>`` (max 500 per poll)."""

    def get(self, request, action_id):
        action = get_object_or_404(EngineAction, pk=action_id)
        try:
            after = int(request.query_params.get("after") or 0)
        except ValueError:
            raise ValidationError({"after": "Must be an integer sequence number."})
        rows = list(action.events.filter(seq__gt=after).order_by("seq")[:500])
        return Response({
            "action_id": str(action.pk),
            "status": action.status,
            "cancel_requested_at": action.cancel_requested_at.isoformat() if action.cancel_requested_at else None,
            "events": [
                {"seq": row.seq, "ts": row.ts.isoformat(), "stage": row.stage, "label": row.label,
                 "level": row.level, "message": row.message, "detail": row.detail}
                for row in rows
            ],
            "last_seq": rows[-1].seq if rows else after,
            "more": len(rows) == 500,
        })


SOURCE_PILLARS = ("2", "6", "7")


class EngineSourcesView(EngineActionCreateView):
    """Build sources (download + read + index) or Clear downloads for one economy."""

    kind = EngineAction.Kind.CORPUS

    def action_arguments(self, request):
        economy = str(request.data.get("economy") or "")
        operation = str(request.data.get("operation") or "build")
        if operation not in ("build", "clear"):
            raise ValidationError({"operation": "Choose build or clear."})
        action = "build_r2_corpus" if operation == "build" else "archive_sources"
        try:
            spec = load_allowlist().get(action) or {}
        except EngineWorkerError as exc:
            raise APIException(str(exc), code="engine_allowlist_unavailable") from exc
        economies = {str(value) for value in ((spec.get("params") or {}).get("economy") or {}).get("enum", [])}
        if economy not in economies:
            raise ValidationError({"economy": "Choose an economy configured in the engine action allowlist."})
        arguments = {"action": action, "economy": economy, "operation": operation}
        if operation == "build":
            pillar = str(request.data.get("pillar") or "")
            if pillar not in SOURCE_PILLARS:
                raise ValidationError({"pillar": f"Choose pillar {', '.join(SOURCE_PILLARS)}."})
            arguments["pillars"] = f"P{pillar}"
            arguments["pillar"] = pillar
        return arguments


def fetch_documents(action):
    """Documents an action downloaded: one entry per "fetch" event of kind download."""
    documents = []
    for event in action.events.filter(stage="fetch").order_by("seq"):
        try:
            detail = json.loads(event.detail or "{}")
        except json.JSONDecodeError:
            continue
        if detail.get("kind") != "download":
            continue
        documents.append({
            "url": detail.get("final_url") or detail.get("url"),
            "seed_url": detail.get("url"),
            "act": detail.get("act"),
            "fetched_at": detail.get("fetched_at") or event.ts.isoformat(),
            "size_kb": round((detail.get("bytes") or 0) / 1024, 1),
            "file_type": detail.get("file_type"),
            "sha256": detail.get("sha256"),
        })
    return documents


class EngineActionDocumentsView(APIView):
    """Every document an action downloaded (Run Record: URL, time, size, file type)."""

    def get(self, request, action_id):
        action = get_object_or_404(EngineAction, pk=action_id)
        documents = fetch_documents(action)
        if request.query_params.get("export") == "csv":
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(["#", "Source URL", "Fetched during", "Time (hh:mm)", "Size (KB)",
                             "File type", "Law", "SHA-256"])
            pass_label = f"Sources · {(action.arguments_json or {}).get('economy', '')}"
            for number, doc in enumerate(documents, 1):
                fetched = parse_datetime(str(doc["fetched_at"]))
                writer.writerow([number, doc["url"], pass_label,
                                 timezone.localtime(fetched).strftime("%H:%M") if fetched else "",
                                 doc["size_kb"], doc["file_type"], doc["act"] or "", doc["sha256"] or ""])
            response = HttpResponse(("\ufeff" + buffer.getvalue()).encode("utf-8"),
                                    content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = f'attachment; filename="documents_downloaded_{action.pk}.csv"'
            return response
        return Response({"action_id": str(action.pk), "status": action.status,
                         "count": len(documents), "documents": documents})


class EngineWorkerStatusView(APIView):
    def get(self, request):
        return Response(worker_status())


class EngineReplayView(EngineActionCreateView):
    kind = EngineAction.Kind.REPLAY

    def action_arguments(self, request):
        return {"action": "replay", "mode": action_mode(request)}


class EngineRefreshView(EngineActionCreateView):
    kind = EngineAction.Kind.REFRESH

    def action_arguments(self, request):
        return {"action": "refresh_payload", "mode": action_mode(request)}


class EngineRunView(EngineActionCreateView):
    kind = EngineAction.Kind.RUN

    def action_arguments(self, request):
        economy = str(request.data.get("economy") or "")
        pillar = str(request.data.get("pillar") or "")
        try:
            spec = load_allowlist().get("run_pipeline") or {}
        except EngineWorkerError as exc:
            raise APIException(str(exc), code="engine_allowlist_unavailable") from exc
        params = spec.get("params") or {}
        economies = {str(value) for value in (params.get("economy") or {}).get("enum", [])}
        run_codes = {str(value) for value in (params.get("cc") or {}).get("enum", [])}
        run_code = RUN_CODES.get(economy)
        if economy not in economies or run_code not in run_codes:
            raise ValidationError(
                {"economy": "Choose an economy configured in the engine action allowlist."}
            )
        if pillar not in {"2", "6", "7"}:
            raise ValidationError({"pillar": "Choose pillar 2, 6 or 7."})
        mode = request_mode(request, request.data)
        return {
            "action": "run_pipeline",
            "economy": economy,
            "pillar": pillar,
            "cc": run_code,
            "mode": mode,
            "provider_profile": RUN_MODES[mode]["provider_profile"],
            "out_prefix": run_out_prefix(mode, run_code, pillar),
        }


# Output-folder codes. Not derived from the name: "Indonesia"[:2] == "India"[:2].
RUN_CODES = {
    "Singapore": "si",
    "Malaysia": "ma",
    "Australia": "au",
    "Thailand": "th",
    "India": "in",
    "Indonesia": "id",
    "Russian Federation": "ru",
    "Mongolia": "mn",
    "Lao PDR": "la",
    "Timor-Leste": "tl",
}


def run_out_prefix(mode, run_code, pillar):
    """Hybrid runs write where the snapshot import reads them (final_r2_* for round 2)."""
    prefix = RUN_MODES[mode]["out_prefix"]
    if mode == "hybrid" and f"final_r2_{run_code}_p{pillar}" in ALL_HYBRID_RUN_NAMES:
        return "final_r2"
    return prefix


class DecisionHistoryView(APIView):
    def get(self, request, domain, key):
        if domain == "findings":
            current_evidence = EvidenceRow.objects.filter(
                snapshot=active_snapshot(), finding_key=key
            ).first()
            current_subject = (
                current_evidence.review_subject_hash if current_evidence else None
            )
            rows = FindingDecision.objects.filter(finding_key=key).order_by(
                "created_at"
            )
            results = [
                {
                    "id": str(row.pk),
                    "stage": row.review_stage,
                    "decision": row.decision,
                    "checks": {
                        "citation": row.citation_checked,
                        "mapping": row.mapping_checked,
                        "status": row.status_checked,
                    },
                    "note": row.note,
                    "reviewer_name": row.reviewer_name,
                    "reviewer_role": row.reviewer_role,
                    "reviewed_at": row.reviewed_at.isoformat(),
                    "supersedes_id": (
                        str(row.supersedes_id) if row.supersedes_id else None
                    ),
                    "authoritative_file_hash": row.authoritative_file_hash,
                    "review_subject_hash": row.review_subject_hash,
                    "current_subject": row.review_subject_hash == current_subject,
                }
                for row in rows
            ]
            corrections = [
                {
                    "id": str(row.pk),
                    "explanation": row.explanation,
                    "reviewer_name": row.requested_by.full_name,
                    "reviewed_at": row.requested_at.isoformat(),
                    "supersedes_id": (
                        str(row.supersedes_id) if row.supersedes_id else None
                    ),
                    "authoritative_file_hash": row.authoritative_file_hash,
                    "review_subject_hash": row.review_subject_hash,
                    "current_subject": row.review_subject_hash == current_subject,
                }
                for row in CorrectionRequest.objects.filter(finding_key=key).order_by(
                    "requested_at"
                )
            ]
            return Response(
                {
                    "domain": domain,
                    "key": key,
                    "results": results,
                    "corrections": corrections,
                    "effective_review": effective_finding_review(
                        key, review_subject_hash=current_subject
                    ),
                }
            )
        if domain == "recall":
            rows = RecallDecision.objects.filter(recall_key=key).order_by("created_at")
            value_field = "verdict"
        elif domain == "zone3":
            rows = Zone3Decision.objects.filter(score_key=key).order_by("created_at")
            value_field = "verdict"
        else:
            raise ValidationError({"domain": "Unknown decision domain."})
        return Response(
            {
                "domain": domain,
                "key": key,
                "results": [
                    serialize_decision(row, value_field=value_field) for row in rows
                ],
            }
        )


def require_role(user, role):
    if not has_review_role(user, role):
        raise PermissionDenied(f"The {role} reviewer role is required.")


def concurrency_check(latest, expected):
    latest_id = latest.pk if latest else None
    if latest_id != expected:
        raise DecisionConflict(
            {
                "detail": "This review changed after it was loaded.",
                "latest_decision_id": str(latest_id) if latest_id else None,
            }
        )


def writer_or_503(domain, decisions):
    try:
        return apply_authoritative_decision(
            domain,
            decisions,
            expected_file_hash=current_authoritative_hash(domain),
        )
    except DecisionWriterConflict as exc:
        raise DecisionConflict(
            {
                "detail": "The authoritative decision file changed outside this review session.",
                "current_file_hash": exc.current_sha or None,
            }
        ) from exc
    except DecisionWriterError as exc:
        raise AuthoritativeWriterUnavailable(str(exc)) from exc


def engine_finding_decisions(
    finding_key, review_subject_hash, effective, *, reviewer_name, reviewer_role,
    reviewed_at, note=""
):
    if not effective.get("decision"):
        return []
    return [
        {
            "finding_key": finding_key,
            "review_subject_hash": review_subject_hash,
            "review": {
                "decision": effective["decision"],
                "reviewer_name": reviewer_name,
                "reviewer_role": reviewer_role,
                "reviewed_at": reviewed_at.isoformat(),
                "citation_checked": effective["citation_checked"],
                "mapping_checked": effective["mapping_checked"],
                "status_checked": effective["status_checked"],
                "citation_reviewer_name": effective["citation_reviewer_name"],
                "mapping_reviewer_name": effective["mapping_reviewer_name"],
                "status_reviewer_name": effective["status_reviewer_name"],
                "correction_note": note or None,
            },
        }
    ]


def sheet_cell(snapshot, queue, row, header):
    if isinstance(row, dict):
        return row.get(header) or row.get(header.casefold().replace(" ", "_"))
    headers = snapshot.headers_json.get(queue, [])
    try:
        index = headers.index(header)
    except ValueError:
        return None
    return row[index] if index < len(row) else None


def sheet_record(sheet, row):
    """Return a sheet row as a named record without changing the stored snapshot."""
    if isinstance(row, dict):
        return row
    return dict(zip(sheet.get("headers") or [], row))


def finding_ineligibility(item, snapshot):
    """Mechanical approval gate shared by individual and bulk decisions."""
    if snapshot.stale:
        return "The active snapshot is stale. Refresh before recording a decision."
    if item.blocked:
        return item.block_reason or "The evidence is technically blocked."

    evidence = EvidenceRow.objects.filter(
        snapshot=snapshot, finding_key=item.finding_key
    ).first()
    if not evidence:
        return "The finding has no consolidated evidence row."
    if technically_blocked(evidence.blocked, evidence.row_json):
        return "The consolidated evidence row is technically blocked."
    row = evidence.row_json
    if str(row.get("Status") or "").strip() != "in_force":
        return "The source is not verified as in force."
    if not row.get("status_evidence") or not row.get("status_evidence_record"):
        return "The finding lacks complete currentness evidence."
    status_record = row.get("status_evidence_record") or {}
    if status_record.get("conflicting"):
        return "The currentness evidence is conflicting."

    if item.queue == ReviewItem.Queue.ABSENCE:
        manifest = row.get("search_coverage_manifest")
        if not isinstance(manifest, dict):
            return "The absence conclusion lacks a search-coverage manifest."
        if manifest.get("unresolved_failures"):
            return "The absence search has unresolved acquisition failures."
        if not manifest.get("portals") or not manifest.get("instruments"):
            return "The absence search coverage is incomplete."
        instrument_results = manifest.get("instrument_results") or []
        if any(
            not result.get("evidence_eligible")
            or result.get("legal_status") != "in_force"
            for result in instrument_results
        ):
            return "The absence coverage includes an ineligible or non-current instrument."
    else:
        proof = row.get("citation_proof")
        if not isinstance(proof, dict):
            return "The finding lacks a complete citation proof."
        if proof.get("alignment_status") in ("unaligned", "ambiguous", "review", None):
            return "The source citation is unresolved or ambiguously aligned."
        # Engine gate contract (gates.py / finalization.validate_final_finding):
        # FAIL = the row can never ship; WARN = a signal the named reviewer must
        # weigh individually. Only FAIL blocks approval here — WARN rows stay
        # approvable one-by-one (bulk approval still excludes them).
        failed_gates = [
            gate.get("gate_id")
            for gate in proof.get("gate_results") or []
            if gate.get("status") == "FAIL"
        ]
        if failed_gates:
            return f"Evidence gates are failing: {', '.join(filter(None, failed_gates))}."
    return ""


class ReviewContextView(APIView):
    def get(self, request, queue, stable_key):
        if queue not in ReviewItem.Queue.values:
            raise ValidationError({"queue": "Unknown review queue."})
        snapshot = active_snapshot()
        item = get_object_or_404(
            ReviewItem, snapshot=snapshot, queue=queue, stable_key=stable_key
        )
        item_record = sheet_record(
            {"headers": snapshot.headers_json.get(queue, [])}, item.row_json
        )
        economy = str(item_record.get("Economy") or "")
        indicator = str(item_record.get("Indicator") or item_record.get("Indicator ID") or "")
        law = str(
            item_record.get("Law/instrument")
            or item_record.get("Configured governing instrument")
            or item_record.get("Master act/instrument")
            or ""
        )

        criteria_sheet = snapshot.reference_json.get("indicator_criteria") or {}
        criteria = [
            sheet_record(criteria_sheet, row)
            for row in criteria_sheet.get("rows") or []
            if str(sheet_record(criteria_sheet, row).get("Indicator") or "") == indicator
        ]
        master_sheet = snapshot.reference_json.get("master_known") or {}
        master_known = [
            sheet_record(master_sheet, row)
            for row in master_sheet.get("rows") or []
            if str(sheet_record(master_sheet, row).get("Economy") or "") == economy
            and str(sheet_record(master_sheet, row).get("Indicator") or "") == indicator
        ]

        related = []
        for evidence in snapshot.evidence_rows.all():
            row = evidence.row_json
            same_indicator = (
                str(row.get("Economy") or "") == economy
                and str(row.get("Indicator ID") or "") == indicator
            )
            same_law = bool(law) and str(row.get("Law Name") or "") == law
            if same_indicator or same_law:
                related.append(
                    {
                        "finding_key": evidence.finding_key,
                        "row": row,
                        "blocked": technically_blocked(evidence.blocked, evidence.row_json),
                        "proof_asset_url": proof_url(evidence.proof_asset),
                        "same_law": same_law,
                        "same_indicator": same_indicator,
                    }
                )

        zone_item = None
        for candidate in snapshot.review_items.filter(queue=ReviewItem.Queue.ZONE3):
            record = sheet_record(
                {"headers": snapshot.headers_json.get(ReviewItem.Queue.ZONE3, [])},
                candidate.row_json,
            )
            if record.get("Economy") == economy and record.get("Indicator") == indicator:
                zone_item = candidate
                break
        zone3 = None
        if zone_item:
            zone_record = sheet_record(
                {"headers": snapshot.headers_json.get(ReviewItem.Queue.ZONE3, [])},
                zone_item.row_json,
            )
            latest = latest_for(Zone3Decision, "score_key", zone_item.stable_key)
            zone3 = {
                "score_key": zone_item.stable_key,
                "deterministic_score": zone_record.get("Deterministic score"),
                "effective_score": float(latest.score) if latest else zone_record.get("Deterministic score"),
                "source": "reviewer" if latest else "deterministic",
                "reviewer_name": latest.reviewer_name if latest else None,
                "reviewed_at": latest.reviewed_at.isoformat() if latest else None,
            }

        return Response(
            {
                "queue": queue,
                "stable_key": stable_key,
                "snapshot": {
                    "id": str(snapshot.pk),
                    "source_hash": snapshot.source_hash,
                    "stale": snapshot.stale,
                },
                "indicator_criteria": criteria[0] if criteria else None,
                "master_known": master_known,
                "related_evidence": related,
                "zone3": zone3,
                "approval_eligibility": {
                    "eligible": not bool(finding_ineligibility(item, snapshot))
                    if queue in (ReviewItem.Queue.NEW, ReviewItem.Queue.KNOWN, ReviewItem.Queue.ABSENCE)
                    else not snapshot.stale and not item.blocked,
                    "reason": finding_ineligibility(item, snapshot)
                    if queue in (ReviewItem.Queue.NEW, ReviewItem.Queue.KNOWN, ReviewItem.Queue.ABSENCE)
                    else (item.block_reason if item.blocked else ("The active snapshot is stale." if snapshot.stale else "")),
                },
                "score_semantics": {
                    "level": "indicator",
                    "finding_has_independent_score": False,
                    "allowed_scores": [0, 0.5, 1],
                    "explanation": "A finding is an evidence row. The 0, 0.5, or 1 score is decided once at indicator level, using all approved evidence and the methodology.",
                },
            }
        )


class FindingDecisionView(APIView):
    def post(self, request):
        serializer = FindingDecisionWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        stage = data["review_stage"]
        require_role(request.user, stage)
        snapshot = active_snapshot()
        item = get_object_or_404(
            ReviewItem,
            snapshot=snapshot,
            queue=data["queue"],
            finding_key=data["finding_key"],
        )
        if snapshot.stale:
            raise ValidationError({"snapshot": "The active snapshot is stale."})
        reason = finding_ineligibility(item, snapshot)
        if reason and data["decision"] == FindingDecision.Verdict.APPROVED:
            raise ValidationError(
                {"decision": reason}
            )

        reviewer_name, reviewer_id = reviewer_identity(request.user)
        reviewer_role = decision_reviewer_role(request.user, stage)
        reviewed_at = timezone.now()
        prospective = {
            **data,
            "id": "prospective",
            "review_subject_hash": item.review_subject_hash,
            "reviewer_name": reviewer_name,
            "reviewer_role": reviewer_role,
            "reviewed_at": reviewed_at,
            "created_by_id": request.user.pk,
        }

        with decision_domain_lock("findings"):
            latest_stage = (
                FindingDecision.objects.filter(
                    finding_key=data["finding_key"],
                    review_subject_hash=item.review_subject_hash,
                    review_stage=stage,
                )
                .order_by("-created_at")
                .first()
            )
            concurrency_check(latest_stage, data.pop("expected_latest_decision_id"))
            effective = effective_finding_review(
                data["finding_key"], review_subject_hash=item.review_subject_hash,
                prospective=prospective
            )
            validate_distinct_stage_reviewer(
                data["finding_key"], stage, data["decision"], request.user, effective
            )
            engine_decisions = engine_finding_decisions(
                data["finding_key"],
                item.review_subject_hash,
                effective,
                reviewer_name=reviewer_name,
                reviewer_role=reviewer_role,
                reviewed_at=reviewed_at,
                note=data["note"],
            )
            receipt = writer_or_503(
                "findings",
                engine_decisions,
            )
            row = FindingDecision.objects.create(
                mode=current_mode(),
                **data,
                review_subject_hash=item.review_subject_hash,
                reviewer_name=reviewer_name,
                reviewer_role=reviewer_role,
                reviewed_at=reviewed_at,
                created_by=request.user,
                supersedes=latest_stage,
                authoritative_file_hash=receipt["sha256"],
                writer_receipt_json=receipt,
            )
        return Response(
            {
                "decision_id": str(row.pk),
                "authoritative_file_hash": receipt["sha256"],
                "review_state": effective_finding_review(
                    row.finding_key, review_subject_hash=row.review_subject_hash
                ),
                "reviewer_id": reviewer_id,
                "outcome": (
                    "engine_decision_written" if engine_decisions else "stage_recorded"
                ),
                "engine_exported": bool(engine_decisions),
            },
            status=status.HTTP_201_CREATED,
        )


def validate_distinct_stage_reviewer(finding_key, stage, decision, user, effective):
    if "admin" in reviewer_roles(user):
        return
    if (
        effective["decision"] == "approved"
        and effective["citation_reviewer_name"].strip().casefold()
        == effective["mapping_reviewer_name"].strip().casefold()
    ):
        raise ValidationError(
            {
                "review_stage": "Citation and mapping approval must have different reviewer names."
            }
        )
    if stage not in (FindingDecision.Stage.CITATION, FindingDecision.Stage.MAPPING):
        return
    other_stage = (
        FindingDecision.Stage.MAPPING
        if stage == FindingDecision.Stage.CITATION
        else FindingDecision.Stage.CITATION
    )
    other = effective["stages"].get(other_stage)
    if (
        decision == FindingDecision.Verdict.APPROVED
        and other
        and other["reviewer_user_id"] == str(user.pk)
    ):
        raise ValidationError(
            {"review_stage": "The same user cannot approve citation and mapping."}
        )


def bulk_ineligibility(item, snapshot):
    reason = finding_ineligibility(item, snapshot)
    if reason:
        return reason
    headers = snapshot.headers_json.get(item.queue, [])
    if isinstance(item.row_json, list) and "Gate warnings" in headers:
        index = headers.index("Gate warnings")
        warning = str(
            item.row_json[index] if index < len(item.row_json) else ""
        ).strip()
        if warning and warning.casefold() not in ("none", "—"):
            return "The finding has gate warnings and requires individual review."
    return ""


class FindingBulkDecisionView(APIView):
    def post(self, request):
        serializer = FindingBulkDecisionWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        stage = data["review_stage"]
        require_role(request.user, stage)
        snapshot = active_snapshot()
        items = list(
            ReviewItem.objects.filter(
                snapshot=snapshot,
                queue=ReviewItem.Queue.KNOWN,
                finding_key__in=data["finding_keys"],
            )
        )
        if len(items) != len(data["finding_keys"]):
            found = {item.finding_key for item in items}
            unknown = sorted(set(data["finding_keys"]) - found)
            raise ValidationError(
                {"finding_keys": f"Unknown/non-KNOWN finding keys: {unknown}"}
            )
        failures = {
            item.finding_key: reason
            for item in items
            if (reason := bulk_ineligibility(item, snapshot))
        }
        if failures:
            raise ValidationError({"ineligible": failures})

        reviewer_name, reviewer_id = reviewer_identity(request.user)
        reviewer_role = decision_reviewer_role(request.user, stage)
        reviewed_at = timezone.now()
        expected = data.pop("expected_latest_decision_ids")
        finding_keys = data.pop("finding_keys")
        with decision_domain_lock("findings"):
            engine_decisions = []
            latest_by_key = {}
            items_by_key = {item.finding_key: item for item in items}
            for key in finding_keys:
                latest_stage = (
                    FindingDecision.objects.filter(
                        finding_key=key,
                        review_subject_hash=items_by_key[key].review_subject_hash,
                        review_stage=stage,
                    )
                    .order_by("-created_at")
                    .first()
                )
                concurrency_check(latest_stage, expected[key])
                latest_by_key[key] = latest_stage
                prospective = {
                    **data,
                    "id": "prospective",
                    "finding_key": key,
                    "review_subject_hash": items_by_key[key].review_subject_hash,
                    "queue": ReviewItem.Queue.KNOWN,
                    "decision": FindingDecision.Verdict.APPROVED,
                    "reviewer_name": reviewer_name,
                    "reviewer_role": reviewer_role,
                    "reviewed_at": reviewed_at,
                    "created_by_id": request.user.pk,
                }
                effective = effective_finding_review(
                    key,
                    review_subject_hash=items_by_key[key].review_subject_hash,
                    prospective=prospective,
                )
                validate_distinct_stage_reviewer(
                    key,
                    stage,
                    FindingDecision.Verdict.APPROVED,
                    request.user,
                    effective,
                )
                engine_decisions.extend(
                    engine_finding_decisions(
                        key,
                        items_by_key[key].review_subject_hash,
                        effective,
                        reviewer_name=reviewer_name,
                        reviewer_role=reviewer_role,
                        reviewed_at=reviewed_at,
                        note=data["note"],
                    )
                )
            receipt = writer_or_503(
                "findings",
                engine_decisions,
            )
            rows = [
                FindingDecision.objects.create(
                mode=current_mode(),
                    finding_key=key,
                    review_subject_hash=items_by_key[key].review_subject_hash,
                    queue=ReviewItem.Queue.KNOWN,
                    review_stage=stage,
                    decision=FindingDecision.Verdict.APPROVED,
                    citation_checked=data["citation_checked"],
                    mapping_checked=data["mapping_checked"],
                    status_checked=data["status_checked"],
                    note=data["note"],
                    reviewer_name=reviewer_name,
                    reviewer_role=reviewer_role,
                    reviewed_at=reviewed_at,
                    created_by=request.user,
                    supersedes=latest_by_key[key],
                    authoritative_file_hash=receipt["sha256"],
                    writer_receipt_json=receipt,
                )
                for key in finding_keys
            ]
        return Response(
            {
                "decision_ids": [str(row.pk) for row in rows],
                "authoritative_file_hash": receipt["sha256"],
                "reviewer_id": reviewer_id,
                "outcome": (
                    "engine_decision_written" if engine_decisions else "stage_recorded"
                ),
                "engine_exported": bool(engine_decisions),
                "review_states": {
                    row.finding_key: effective_finding_review(
                        row.finding_key, review_subject_hash=row.review_subject_hash
                    )
                    for row in rows
                },
            },
            status=status.HTTP_201_CREATED,
        )


class RecallDecisionView(APIView):
    def post(self, request):
        require_role(request.user, "recall")
        serializer = RecallDecisionWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        snapshot = active_snapshot()
        if snapshot.stale:
            raise ValidationError({"snapshot": "The active snapshot is stale."})
        item = get_object_or_404(
            ReviewItem,
            snapshot=snapshot,
            queue=ReviewItem.Queue.RECALL,
            stable_key=data["recall_key"],
        )
        if item.blocked:
            raise ValidationError({"verdict": item.block_reason or "The recall item is blocked."})
        reviewer_name, reviewer_id = reviewer_identity(request.user)
        with decision_domain_lock("recall"):
            latest = latest_for(RecallDecision, "recall_key", data["recall_key"])
            concurrency_check(latest, data.pop("expected_latest_decision_id"))
            reviewed_at = timezone.now()
            receipt = writer_or_503(
                "recall",
                [
                    {
                        **{
                            key: str(value) if isinstance(value, Decimal) else value
                            for key, value in data.items()
                        },
                        "reviewer_name": reviewer_name,
                        "reviewer_role": "mapping",
                        "reviewed_at": reviewed_at.isoformat(),
                    }
                ],
            )
            row = RecallDecision.objects.create(
                mode=current_mode(),
                **data,
                reviewer_name=reviewer_name,
                reviewer_role="mapping",
                reviewed_at=reviewed_at,
                created_by=request.user,
                supersedes=latest,
                authoritative_file_hash=receipt["sha256"],
                writer_receipt_json=receipt,
            )
        return Response(
            {
                "decision_id": str(row.pk),
                "authoritative_file_hash": receipt["sha256"],
                "reviewer_id": reviewer_id,
            },
            status=status.HTTP_201_CREATED,
        )


class Zone3DecisionView(APIView):
    def post(self, request):
        require_role(request.user, "zone3")
        serializer = Zone3DecisionWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        snapshot = active_snapshot()
        if snapshot.stale:
            raise ValidationError({"snapshot": "The active snapshot is stale."})
        item = get_object_or_404(
            ReviewItem,
            snapshot=snapshot,
            queue=ReviewItem.Queue.ZONE3,
            stable_key=data["score_key"],
        )
        if item.blocked:
            raise ValidationError({"score": item.block_reason or "The score item is blocked."})
        reviewer_name, reviewer_id = reviewer_identity(request.user)
        with decision_domain_lock("zone3"):
            latest = latest_for(Zone3Decision, "score_key", data["score_key"])
            concurrency_check(latest, data.pop("expected_latest_decision_id"))
            reviewed_at = timezone.now()
            event = {
                "economy": sheet_cell(
                    item.snapshot, ReviewItem.Queue.ZONE3, item.row_json, "Economy"
                ),
                "indicator": sheet_cell(
                    item.snapshot, ReviewItem.Queue.ZONE3, item.row_json, "Indicator"
                ),
                "action": (
                    "approve"
                    if data["verdict"] == Zone3Decision.Verdict.APPROVED
                    else "override"
                ),
                "score": float(data["score"]),
                "reasoning": data["reasoning"],
                "reviewer_name": reviewer_name,
                "reviewer_role": "mapping",
                "reviewed_at": reviewed_at.isoformat(),
            }
            receipt = writer_or_503(
                "zone3",
                [event],
            )
            row = Zone3Decision.objects.create(
                mode=current_mode(),
                **data,
                reviewer_name=reviewer_name,
                reviewer_role="mapping",
                reviewed_at=reviewed_at,
                created_by=request.user,
                supersedes=latest,
                authoritative_file_hash=receipt["sha256"],
                writer_receipt_json=receipt,
            )
        return Response(
            {
                "decision_id": str(row.pk),
                "authoritative_file_hash": receipt["sha256"],
                "reviewer_id": reviewer_id,
            },
            status=status.HTTP_201_CREATED,
        )


MATRIX_ECONOMY_ORDER = ["Singapore", "Malaysia", "Australia", "Thailand", "India", "Indonesia",
                        "Russian Federation", "Mongolia", "Lao PDR", "Timor-Leste"]


def zone3_matrix_payload(snapshot):
    """Indicator-score matrix of one snapshot: engine Zone-3 proposals overlaid with
    the attributable reviewer decisions of the same model backend, plus the
    evidence rows each score rests on."""
    mode = snapshot.mode

    latest_decisions = {}
    for decision in Zone3Decision.objects.filter(mode=mode).order_by("created_at"):
        latest_decisions[decision.score_key] = decision

    evidence_index = {}
    evidence_queues = (ReviewItem.Queue.NEW, ReviewItem.Queue.KNOWN, ReviewItem.Queue.ABSENCE)
    for item in ReviewItem.objects.filter(snapshot=snapshot, queue__in=evidence_queues).order_by("position"):
        record = sheet_record({"headers": snapshot.headers_json.get(item.queue) or []}, item.row_json)
        economy = str(record.get("Economy") or "").strip()
        indicator = str(record.get("Indicator") or record.get("Indicator ID") or "").strip()
        if not economy or not indicator:
            continue
        evidence_index.setdefault((economy.casefold(), indicator.casefold()), []).append({
            "finding_key": item.finding_key,
            "stable_key": item.stable_key,
            "queue": item.queue,
            "law": str(record.get("Law/instrument") or record.get("Law Name")
                       or record.get("Configured governing instrument") or ""),
            "article": str(record.get("Article/section") or record.get("Article / Section")
                           or record.get("Master citation") or ""),
            "tag": str(record.get("Discovery Tag") or ("ABSENCE" if item.queue == ReviewItem.Queue.ABSENCE else "")),
            "blocked": item.blocked,
        })

    cells = []
    economies, indicators = [], []
    decided = 0
    for item in ReviewItem.objects.filter(snapshot=snapshot, queue=ReviewItem.Queue.ZONE3).order_by("position"):
        record = sheet_record({"headers": snapshot.headers_json.get(ReviewItem.Queue.ZONE3) or []}, item.row_json)
        economy = str(record.get("Economy") or "").strip()
        indicator = str(record.get("Indicator") or "").strip()
        if economy not in economies:
            economies.append(economy)
        if indicator not in indicators:
            indicators.append(indicator)
        deterministic = record.get("Deterministic score")
        decision = latest_decisions.get(item.stable_key)
        state = "pending"
        effective = None
        if decision is not None:
            # The engine ledger stores writer-style actions (approve/override);
            # app-written rows store the model verdicts (approved/overridden).
            state = "overridden" if str(decision.verdict) in ("override", "overridden") else "approved"
            effective = float(decision.score) if decision.score is not None else deterministic
            decided += 1
        cells.append({
            "economy": economy,
            "indicator": indicator,
            "score_key": item.stable_key,
            "question": record.get("Indicator question"),
            "deterministic": deterministic,
            "deterministic_reason": record.get("Deterministic reason"),
            "master_gold": record.get("Master gold score"),
            "gold_divergence": (lambda value: value if value and value.casefold() not in ("agrees", "none", "n/a", "—") else None)(str(record.get("Gold divergence") or "").strip()),
            "judge_scores": record.get("Judge scores"),
            "judge_reasoning": record.get("Judge reasoning"),
            "agreement_alpha": record.get("Agreement alpha"),
            "score_band": record.get("Score band"),
            "flagged": bool(record.get("Flagged for review")),
            "state": state,
            "effective": effective,
            "reviewer_name": decision.reviewer_name if decision else "",
            "reviewed_at": decision.reviewed_at.isoformat() if decision else None,
            "reasoning": (decision.reasoning if decision and hasattr(decision, "reasoning") else "") or "",
            "latest_decision_id": str(decision.pk) if decision else None,
            "blocked": item.blocked,
            "evidence": evidence_index.get((economy.casefold(), indicator.casefold()), []),
        })

    economies.sort(key=lambda name: (MATRIX_ECONOMY_ORDER.index(name) if name in MATRIX_ECONOMY_ORDER else 99, name))
    indicators.sort()
    return {
        "mode": mode,
        "modes": serialize_modes(),
        "snapshot": snapshot_identity(snapshot),
        "economies": economies,
        "indicators": indicators,
        "counts": {"total": len(cells), "decided": decided, "pending": len(cells) - decided},
        "score_semantics": {
            "explanation": "A cell is an indicator-level decision. The engine proposes a deterministic score with judge-panel context; only a named reviewer approval or override makes it effective.",
            "allowed_scores": [0, 0.5, 1],
        },
        "cells": cells,
    }


class Zone3MatrixView(APIView):
    def get(self, request):
        mode = request_mode(request)
        snapshot = EngineSnapshot.objects.filter(active=True, mode=mode).first()
        if snapshot is None:
            return Response({
                "mode": mode, "modes": serialize_modes(), "snapshot": None, "economies": [],
                "indicators": [], "counts": {"total": 0, "decided": 0, "pending": 0},
                "score_semantics": {"explanation": "", "allowed_scores": [0, 0.5, 1]}, "cells": [],
            })
        return Response(zone3_matrix_payload(snapshot))


class CorrectionRequestView(APIView):
    def post(self, request):
        serializer = CorrectionRequestWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if not (
            has_review_role(request.user, "citation")
            or has_review_role(request.user, "mapping")
            or has_review_role(request.user, "status")
        ):
            raise PermissionDenied("A reviewer role is required.")
        snapshot = active_snapshot()
        if snapshot.stale:
            raise ValidationError({"snapshot": "The active snapshot is stale."})
        item = get_object_or_404(
            ReviewItem,
            snapshot=snapshot,
            queue=data["queue"],
            finding_key=data["finding_key"],
        )
        with decision_domain_lock("findings"):
            latest = (
                CorrectionRequest.objects.filter(
                    finding_key=data["finding_key"],
                    review_subject_hash=item.review_subject_hash,
                )
                .order_by("-requested_at")
                .first()
            )
            concurrency_check(latest, data.pop("expected_latest_correction_id"))
            reviewed_at = timezone.now()
            receipt = writer_or_503(
                "findings",
                [
                    {
                        "finding_key": data["finding_key"],
                        "review_subject_hash": item.review_subject_hash,
                        "review": {
                            "decision": "rejected",
                            "reviewer_name": request.user.full_name,
                            "reviewer_role": "correction-request",
                            "reviewed_at": reviewed_at.isoformat(),
                            "citation_checked": False,
                            "mapping_checked": False,
                            "status_checked": False,
                            "citation_reviewer_name": "",
                            "mapping_reviewer_name": "",
                            "status_reviewer_name": "",
                            "correction_note": data["explanation"],
                        },
                    }
                ],
            )
            row = CorrectionRequest.objects.create(
                mode=current_mode(),
                **data,
                review_subject_hash=item.review_subject_hash,
                requested_by=request.user,
                supersedes=latest,
                authoritative_file_hash=receipt["sha256"],
                writer_receipt_json=receipt,
            )
        return Response(
            {
                "correction_request_id": str(row.pk),
                "finding_key": row.finding_key,
                "authoritative_file_hash": receipt["sha256"],
            },
            status=status.HTTP_201_CREATED,
        )
