from .models import CorrectionRequest, EvidenceRevision, FindingDecision


STAGE_HASH_FIELD = {
    FindingDecision.Stage.CITATION: "citation_hash",
    FindingDecision.Stage.MAPPING: "mapping_hash",
    FindingDecision.Stage.STATUS: "status_hash",
}


def _latest_correction(finding_key, review_subject_hash=None):
    queryset = CorrectionRequest.objects.filter(finding_key=finding_key)
    if review_subject_hash:
        queryset = queryset.filter(review_subject_hash=review_subject_hash)
    return queryset.order_by("-requested_at").first()


def _current_revision(finding_key, review_subject_hash=None):
    queryset = EvidenceRevision.objects.filter(finding_key=finding_key)
    if review_subject_hash:
        queryset = queryset.filter(review_subject_hash=review_subject_hash)
    return queryset.select_related("identity").order_by("-created_at").first()


def _carried_stage(revision, stage):
    if revision is None:
        return None
    field = STAGE_HASH_FIELD[stage]
    candidates = (
        EvidenceRevision.objects.filter(
            identity=revision.identity,
            **{field: getattr(revision, field)},
        )
        .exclude(pk=revision.pk)
        .order_by("-created_at")
    )
    for candidate in candidates:
        correction = _latest_correction(
            candidate.finding_key, candidate.review_subject_hash
        )
        decisions = FindingDecision.objects.filter(
            finding_key=candidate.finding_key,
            review_subject_hash=candidate.review_subject_hash,
            review_stage=stage,
        )
        if correction:
            decisions = decisions.filter(created_at__gt=correction.requested_at)
        row = decisions.order_by("-created_at").first()
        if row:
            return {
                "id": row.id,
                "decision": row.decision,
                "reviewer_name": row.reviewer_name,
                "reviewer_role": row.reviewer_role,
                "reviewed_at": row.reviewed_at,
                "created_by_id": row.created_by_id,
                "citation_checked": row.citation_checked,
                "mapping_checked": row.mapping_checked,
                "status_checked": row.status_checked,
                "carried_forward": True,
                "carried_from_finding_key": candidate.finding_key,
                "carried_from_revision_id": str(candidate.pk),
            }
    return None


def latest_finding_stages(finding_key, *, review_subject_hash=None, prospective=None):
    stages = {}
    correction = _latest_correction(finding_key, review_subject_hash)
    revision = _current_revision(finding_key, review_subject_hash)
    for stage in FindingDecision.Stage.values:
        queryset = FindingDecision.objects.filter(
            finding_key=finding_key, review_stage=stage
        )
        if review_subject_hash:
            queryset = queryset.filter(review_subject_hash=review_subject_hash)
        if correction:
            queryset = queryset.filter(created_at__gt=correction.requested_at)
        row = queryset.order_by("-created_at").first()
        if row is None:
            row = _carried_stage(revision, stage)
        if row:
            stages[stage] = row
    if prospective is not None:
        stages[prospective["review_stage"]] = prospective
    return stages


def _value(row, name, default=None):
    if isinstance(row, dict):
        return row.get(name, default)
    return getattr(row, name, default)


def _reviewer_separation_satisfied(citation, mapping):
    citation_user = _value(citation, "created_by_id")
    mapping_user = _value(mapping, "created_by_id")
    if citation_user != mapping_user:
        return True
    # Ledger-imported decisions: one importer account writes both stages, but the
    # NAMED reviewers differ — that is the engine writer's own separation rule.
    citation_name = str(_value(citation, "reviewer_name", "") or "").strip().casefold()
    mapping_name = str(_value(mapping, "reviewer_name", "") or "").strip().casefold()
    if citation_name and mapping_name and citation_name != mapping_name:
        return True
    return bool(
        citation_user
        and "admin"
        in {
            _value(citation, "reviewer_role", ""),
            _value(mapping, "reviewer_role", ""),
        }
    )


def effective_finding_review(finding_key, *, review_subject_hash=None, prospective=None):
    correction = _latest_correction(finding_key, review_subject_hash)
    stages = latest_finding_stages(
        finding_key, review_subject_hash=review_subject_hash, prospective=prospective
    )
    rejected = next(
        (
            row
            for row in stages.values()
            if _value(row, "decision") == FindingDecision.Verdict.REJECTED
        ),
        None,
    )
    citation = stages.get(FindingDecision.Stage.CITATION)
    mapping = stages.get(FindingDecision.Stage.MAPPING)
    status = stages.get(FindingDecision.Stage.STATUS)

    def checked(name):
        return any(bool(_value(row, name, False)) for row in stages.values())

    complete = (
        citation
        and mapping
        and _value(citation, "decision") == FindingDecision.Verdict.APPROVED
        and _value(mapping, "decision") == FindingDecision.Verdict.APPROVED
        and _reviewer_separation_satisfied(citation, mapping)
        and checked("status_checked")
    )
    decision = "rejected" if rejected else ("approved" if complete else None)
    return {
        "decision": decision,
        "correction_pending": bool(correction) and not complete and not rejected,
        "citation_checked": checked("citation_checked"),
        "mapping_checked": checked("mapping_checked"),
        "status_checked": checked("status_checked"),
        "citation_reviewer_name": _value(citation, "reviewer_name", ""),
        "mapping_reviewer_name": _value(mapping, "reviewer_name", ""),
        "status_reviewer_name": _value(status, "reviewer_name", "")
        or next(
            (
                _value(row, "reviewer_name", "")
                for row in stages.values()
                if _value(row, "status_checked", False)
            ),
            "",
        ),
        "stages": {
            stage: {
                "id": str(_value(row, "id", "")),
                "decision": _value(row, "decision"),
                "reviewer_name": _value(row, "reviewer_name", ""),
                "reviewer_user_id": str(_value(row, "created_by_id", "")),
                "reviewed_at": (
                    _value(row, "reviewed_at").isoformat()
                    if _value(row, "reviewed_at")
                    and not isinstance(_value(row, "reviewed_at"), str)
                    else _value(row, "reviewed_at")
                ),
                "carried_forward": bool(_value(row, "carried_forward", False)),
                "carried_from_finding_key": _value(
                    row, "carried_from_finding_key", ""
                ),
                "carried_from_revision_id": _value(
                    row, "carried_from_revision_id", ""
                ),
            }
            for stage, row in stages.items()
        },
    }


def bulk_finding_stages(revisions):
    """Latest decision per review stage (direct or carried forward) for many registry
    revisions, keyed by (finding_key, review_subject_hash), in bounded queries."""

    revisions = list(revisions)
    if not revisions:
        return {}
    identity_ids = {revision.identity_id for revision in revisions}
    history = list(
        EvidenceRevision.objects.filter(identity_id__in=identity_ids).order_by(
            "-created_at"
        )
    )
    revision_keys = {(row.finding_key, row.review_subject_hash) for row in history}
    finding_keys = {key for key, _ in revision_keys}
    corrections = {}
    for row in CorrectionRequest.objects.filter(finding_key__in=finding_keys).order_by(
        "requested_at"
    ):
        corrections[(row.finding_key, row.review_subject_hash)] = row
    decisions = {}
    for row in FindingDecision.objects.filter(finding_key__in=finding_keys).order_by(
        "created_at"
    ):
        key = (row.finding_key, row.review_subject_hash, row.review_stage)
        correction = corrections.get((row.finding_key, row.review_subject_hash))
        if correction and row.created_at <= correction.requested_at:
            continue
        decisions[key] = row
    by_identity = {}
    for row in history:
        by_identity.setdefault(row.identity_id, []).append(row)

    result = {}
    for current in revisions:
        stages = {}
        for stage, field in STAGE_HASH_FIELD.items():
            direct = decisions.get(
                (current.finding_key, current.review_subject_hash, stage)
            )
            if direct:
                stages[stage] = direct
                continue
            target_hash = getattr(current, field)
            for candidate in by_identity.get(current.identity_id, []):
                if candidate.pk == current.pk or getattr(candidate, field) != target_hash:
                    continue
                carried = decisions.get(
                    (candidate.finding_key, candidate.review_subject_hash, stage)
                )
                if carried:
                    stages[stage] = carried
                    break
        result[(current.finding_key, current.review_subject_hash)] = stages
    return result


def stages_verdict(stages):
    """"rejected", "approved" or None (undecided) from a finding's latest stage decisions."""
    rejected = any(
        row.decision == FindingDecision.Verdict.REJECTED for row in stages.values()
    )
    citation = stages.get(FindingDecision.Stage.CITATION)
    mapping = stages.get(FindingDecision.Stage.MAPPING)
    status_checked = any(row.status_checked for row in stages.values())
    complete = bool(
        citation
        and mapping
        and citation.decision == FindingDecision.Verdict.APPROVED
        and mapping.decision == FindingDecision.Verdict.APPROVED
        and _reviewer_separation_satisfied(citation, mapping)
        and status_checked
    )
    return "rejected" if rejected else ("approved" if complete else None)


def bulk_effective_finding_decisions(revisions):
    """Resolve final verdicts for many registry revisions in bounded queries."""

    return {
        key: stages_verdict(stages)
        for key, stages in bulk_finding_stages(revisions).items()
    }
