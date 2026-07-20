from .models import CorrectionRequest, FindingDecision


def latest_finding_stages(finding_key, *, prospective=None):
    stages = {}
    correction = (
        CorrectionRequest.objects.filter(finding_key=finding_key)
        .order_by("-requested_at")
        .first()
    )
    for stage in FindingDecision.Stage.values:
        queryset = FindingDecision.objects.filter(
            finding_key=finding_key, review_stage=stage
        )
        if correction:
            queryset = queryset.filter(created_at__gt=correction.requested_at)
        row = queryset.order_by("-created_at").first()
        if row:
            stages[stage] = row
    if prospective is not None:
        stages[prospective["review_stage"]] = prospective
    return stages


def _value(row, name, default=None):
    if isinstance(row, dict):
        return row.get(name, default)
    return getattr(row, name, default)


def effective_finding_review(finding_key, *, prospective=None):
    correction = (
        CorrectionRequest.objects.filter(finding_key=finding_key)
        .order_by("-requested_at")
        .first()
    )
    stages = latest_finding_stages(finding_key, prospective=prospective)
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

    citation_user = _value(citation, "created_by_id")
    mapping_user = _value(mapping, "created_by_id")
    complete = (
        citation
        and mapping
        and _value(citation, "decision") == FindingDecision.Verdict.APPROVED
        and _value(mapping, "decision") == FindingDecision.Verdict.APPROVED
        and citation_user != mapping_user
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
            }
            for stage, row in stages.items()
        },
    }
