from decimal import Decimal
import csv
import hashlib
import json
import re
from urllib.parse import urlparse

from django.conf import settings
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.permissions import BasePermission
from rest_framework.views import APIView

from .decision_state import effective_finding_review
from .decision_writer import (
    DecisionWriterConflict,
    DecisionWriterError,
    apply_authoritative_decision,
    current_authoritative_hash,
    decision_domain_lock,
)
from .models import (
    CorrectionRequest,
    EngineSnapshot,
    EngineAction,
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
from .roles import has_review_role, reviewer_identity, reviewer_roles
from .serializers import (
    CorrectionRequestWriteSerializer,
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
    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated and request.user.is_superuser
        )


def active_snapshot():
    snapshot = EngineSnapshot.objects.filter(active=True).first()
    if snapshot is None:
        raise APIException(
            "No engine snapshot has been imported.", code="snapshot_unavailable"
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
        eligibility_reason = finding_ineligibility(item, item.snapshot)
        result["approval_eligibility"] = {
            "eligible": not bool(eligibility_reason),
            "reason": eligibility_reason,
        }
        correction = (
            CorrectionRequest.objects.filter(finding_key=item.finding_key)
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


class SummaryView(APIView):
    def get(self, request):
        snapshot = active_snapshot()
        progress = {}
        for queue in ReviewItem.Queue.values:
            items = list(snapshot.review_items.filter(queue=queue))
            progress[queue] = {
                "decided": sum(item_is_decided(item) for item in items),
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
                "reviewer_roles": reviewer_roles(request.user),
            }
        )


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
        rows = [*FindingDecision.objects.all(), *RecallDecision.objects.all(), *Zone3Decision.objects.all(), *CorrectionRequest.objects.all(), *Release.objects.all()]
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
        return Response({"snapshot": snapshot_identity(snapshot), "status": graph.get("status", "unavailable"), "nodes": nodes[:500], "edges": edges[:1000], "caps": {"nodes": 500, "edges": 1000}})


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
                        "blocked": row.blocked,
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
            rows = [
                row
                for row in rows
                if str(row.row_json.get(field_name) or "").casefold()
                == value.casefold()
            ]
    pillar = params.get("pillar")
    if pillar:
        rows = [
            row
            for row in rows
            if str(row.row_json.get("Indicator ID") or "").startswith(f"P{pillar}-")
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


def serialize_source_match(evidence, *, navigation):
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
            and (settings.ENGINE_ROOT / "submission" / "review" / evidence.proof_asset).is_file()
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
                "blocked": row.blocked,
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
        return Response(serialize_source_match(evidence, navigation=navigation))


class ProofAssetView(APIView):
    def get(self, request, filename):
        if not PROOF_ASSET_PATTERN.fullmatch(filename):
            raise Http404
        path = settings.ENGINE_ROOT / "submission" / "review" / "assets" / filename
        if not path.is_file():
            raise Http404
        return FileResponse(path.open("rb"), content_type="image/png")


class RunsView(APIView):
    def get(self, request):
        snapshot = active_snapshot()
        records = RunRecord.objects.filter(snapshot=snapshot)
        return Response(
            {
                "results": [serialize_run(record) for record in records],
                "champion": snapshot.champion_json,
                "actions": [
                    serialize_engine_action(action)
                    for action in EngineAction.objects.all()[:20]
                ],
                "can_launch": request.user.is_superuser,
            }
        )


def serialize_run(record):
    envelope = record.envelope_json
    findings = envelope.get("findings") or []
    warnings = envelope.get("warnings") or []
    metadata = envelope.get("metadata") or {}
    cost = record.cost_json or metadata.get("cost_report") or {}
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
        "run_name": record.run_name,
        "run_id": envelope.get("run_id") or cost.get("run_id"),
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
        "source_hash": record.source_hash,
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
    root = settings.ENGINE_ROOT / "submission"
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
                release=serialize_release(Release.objects.first()),
            )
        )


def serialize_engine_action(action):
    return {
        "id": str(action.pk),
        "kind": action.kind,
        "status": action.status,
        "arguments": action.arguments_json,
        "requested_by": action.requested_by.full_name,
        "requested_at": action.requested_at.isoformat(),
        "started_at": action.started_at.isoformat() if action.started_at else None,
        "finished_at": action.finished_at.isoformat() if action.finished_at else None,
        "stdout": action.stdout,
        "result_hashes": action.result_hashes_json,
        "error": action.error,
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
            if active.exists():
                raise DecisionConflict("An action of this type is already queued or running.")
            action = EngineAction.objects.create(
                kind=self.kind,
                arguments_json=arguments,
                requested_by=request.user,
            )
        return Response(serialize_engine_action(action), status=status.HTTP_202_ACCEPTED)


class EngineReplayView(EngineActionCreateView):
    kind = EngineAction.Kind.REPLAY

    def action_arguments(self, request):
        return {"action": "replay"}


class EngineRefreshView(EngineActionCreateView):
    kind = EngineAction.Kind.REFRESH

    def action_arguments(self, request):
        return {"action": "refresh_payload"}


class EngineRunView(EngineActionCreateView):
    kind = EngineAction.Kind.RUN

    def action_arguments(self, request):
        economy = str(request.data.get("economy") or "")
        pillar = str(request.data.get("pillar") or "")
        aliases = {"Singapore": "si", "Malaysia": "ma", "Australia": "au"}
        if economy not in aliases:
            raise ValidationError({"economy": "Choose Singapore, Malaysia, or Australia."})
        if pillar not in {"6", "7"}:
            raise ValidationError({"pillar": "Choose pillar 6 or 7."})
        return {
            "action": "run_pipeline",
            "economy": economy,
            "pillar": pillar,
            "cc": aliases[economy],
        }


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
    if evidence.blocked:
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
        failed_gates = [
            gate.get("gate_id")
            for gate in proof.get("gate_results") or []
            if gate.get("status") != "PASS"
        ]
        if failed_gates:
            return f"Evidence gates are not passing: {', '.join(filter(None, failed_gates))}."
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
                        "blocked": evidence.blocked,
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
        reviewed_at = timezone.now()
        prospective = {
            **data,
            "id": "prospective",
            "review_subject_hash": item.review_subject_hash,
            "reviewer_name": reviewer_name,
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
                reviewer_role=stage,
                reviewed_at=reviewed_at,
                note=data["note"],
            )
            receipt = writer_or_503(
                "findings",
                engine_decisions,
            )
            row = FindingDecision.objects.create(
                **data,
                review_subject_hash=item.review_subject_hash,
                reviewer_name=reviewer_name,
                reviewer_role=stage,
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
                        reviewer_role=stage,
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
                    reviewer_role=stage,
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
        get_object_or_404(
            ReviewItem,
            snapshot=snapshot,
            queue=data["queue"],
            finding_key=data["finding_key"],
        )
        with decision_domain_lock("findings"):
            latest = (
                CorrectionRequest.objects.filter(finding_key=data["finding_key"])
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
                **data,
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
