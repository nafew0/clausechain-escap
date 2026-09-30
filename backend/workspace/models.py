import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class ImmutableAuditQuerySet(models.QuerySet):
    def delete(self):
        raise ValidationError("Append-only audit rows cannot be deleted.")


class ImmutableAuditModel(models.Model):
    """Reject in-place mutation of an audit row after its first insert."""

    class Meta:
        abstract = True

    objects = models.Manager.from_queryset(ImmutableAuditQuerySet)()

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError(f"{type(self).__name__} rows are append-only.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(f"{type(self).__name__} rows are append-only.")


class EngineSnapshot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    schema_version = models.CharField(max_length=32, default="1")
    generated_at = models.DateTimeField()
    imported_at = models.DateTimeField(auto_now_add=True)
    source_hash = models.CharField(max_length=64, unique=True)
    bundle_hash = models.CharField(max_length=64, blank=True, default="")
    engine_git_sha = models.CharField(max_length=64, blank=True, default="")
    counts_json = models.JSONField(default=dict)
    headers_json = models.JSONField(default=dict)
    reference_json = models.JSONField(default=dict)
    refuter_status = models.TextField(blank=True, default="")
    champion_status = models.CharField(max_length=16, blank=True, default="")
    champion_json = models.JSONField(default=dict)
    manifest_json = models.JSONField(default=dict)
    stale = models.BooleanField(default=False)
    active = models.BooleanField(default=False)
    # Model backend: "hybrid" (Model A, the signed registry) or "local"
    # (Model B, open weights). The two workspaces never share rows.
    mode = models.CharField(max_length=16, default="hybrid", db_index=True)

    class Meta:
        ordering = ["-imported_at"]
        indexes = [models.Index(fields=["active", "-imported_at"])]
        constraints = [
            models.UniqueConstraint(
                fields=["mode"],
                condition=models.Q(active=True),
                name="workspace_one_active_snapshot_per_mode",
            )
        ]


class SnapshotArtifact(ImmutableAuditModel):
    """Exact immutable input captured for one engine snapshot."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    snapshot = models.ForeignKey(
        EngineSnapshot, on_delete=models.CASCADE, related_name="artifacts"
    )
    key = models.SlugField(max_length=160)
    category = models.CharField(max_length=32)
    source_path = models.CharField(max_length=1000, blank=True, default="")
    media_type = models.CharField(max_length=100, default="application/json")
    byte_size = models.PositiveBigIntegerField(default=0)
    sha256 = models.CharField(max_length=64)
    raw_text = models.TextField(blank=True, default="")
    parsed_json = models.JSONField(default=dict)
    generated_at = models.DateTimeField(null=True, blank=True)
    imported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["category", "key"]
        constraints = [
            models.UniqueConstraint(
                fields=["snapshot", "key"], name="workspace_snapshot_artifact_key_uniq"
            )
        ]
        indexes = [
            models.Index(
                fields=["snapshot", "category", "key"],
                name="ws_artifact_snapshot_cat_idx",
            )
        ]


class ReviewItem(models.Model):
    class Queue(models.TextChoices):
        NEW = "new", "NEW"
        ABSENCE = "absence", "Absence"
        RECALL = "recall", "Recall"
        ZONE3 = "zone3", "Zone 3"
        KNOWN = "known", "KNOWN"

    snapshot = models.ForeignKey(
        EngineSnapshot, on_delete=models.CASCADE, related_name="review_items"
    )
    queue = models.CharField(max_length=16, choices=Queue.choices)
    position = models.PositiveIntegerField()
    row_json = models.JSONField()
    stable_key = models.CharField(max_length=64, blank=True, default="")
    finding_key = models.CharField(max_length=64, blank=True, default="")
    review_subject_hash = models.CharField(max_length=64, blank=True, default="")
    blocked = models.BooleanField(default=False)
    block_reason = models.TextField(blank=True, default="")
    source_hash = models.CharField(max_length=64)

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(
                fields=["snapshot", "queue", "position"],
                name="workspace_review_item_position_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["snapshot", "queue", "position"]),
            models.Index(fields=["snapshot", "finding_key"]),
            models.Index(fields=["snapshot", "stable_key"]),
        ]


class EvidenceRow(models.Model):
    snapshot = models.ForeignKey(
        EngineSnapshot, on_delete=models.CASCADE, related_name="evidence_rows"
    )
    position = models.PositiveIntegerField()
    row_json = models.JSONField()
    finding_key = models.CharField(max_length=64)
    review_subject_hash = models.CharField(max_length=64, blank=True, default="")
    proof_asset = models.CharField(max_length=500, blank=True, default="")
    blocked = models.BooleanField(default=False)
    source_hash = models.CharField(max_length=64)

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(
                fields=["snapshot", "finding_key"],
                name="workspace_evidence_snapshot_finding_uniq",
            )
        ]
        indexes = [models.Index(fields=["snapshot", "finding_key"])]


class EvidenceIdentity(models.Model):
    """Stable legal identity shared by every immutable extraction revision."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    identity_hash = models.CharField(max_length=64, unique=True)
    economy = models.CharField(max_length=120)
    indicator_id = models.CharField(max_length=64)
    instrument_key = models.CharField(max_length=500)
    law_name = models.CharField(max_length=500)
    citation_key = models.CharField(max_length=300)
    finding_type = models.CharField(max_length=32, default="provision")
    # Model backend: "hybrid" (Model A, the signed registry) or "local"
    # (Model B, open weights). The two workspaces never share rows.
    mode = models.CharField(max_length=16, default="hybrid", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["economy", "indicator_id", "law_name", "citation_key"]
        indexes = [
            models.Index(fields=["economy", "indicator_id"]),
            models.Index(fields=["instrument_key", "citation_key"]),
        ]


class EvidenceRevision(ImmutableAuditModel):
    """Immutable application-owned interpretation of one engine evidence row."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    identity = models.ForeignKey(
        EvidenceIdentity, on_delete=models.PROTECT, related_name="revisions"
    )
    snapshot = models.ForeignKey(
        EngineSnapshot, on_delete=models.PROTECT, related_name="evidence_revisions"
    )
    finding_key = models.CharField(max_length=64)
    review_subject_hash = models.CharField(max_length=64)
    revision_hash = models.CharField(max_length=64)
    citation_hash = models.CharField(max_length=64)
    mapping_hash = models.CharField(max_length=64)
    status_hash = models.CharField(max_length=64)
    coverage_hash = models.CharField(max_length=64, blank=True, default="")
    row_json = models.JSONField()
    proof_asset = models.CharField(max_length=500, blank=True, default="")
    blocked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["identity", "snapshot"],
                name="workspace_identity_snapshot_revision_uniq",
            ),
            models.UniqueConstraint(
                fields=["snapshot", "finding_key"],
                name="workspace_revision_snapshot_finding_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["identity", "-created_at"]),
            models.Index(fields=["finding_key", "review_subject_hash"]),
        ]


class EvidenceRegistryEntry(models.Model):
    """Mutable projection pointing at the latest revision; history stays immutable."""

    class State(models.TextChoices):
        CURRENT = "current", "Current"
        NOT_REPRODUCED = "not_reproduced", "Not reproduced"
        RETIRED = "retired", "Retired"

    identity = models.OneToOneField(
        EvidenceIdentity,
        on_delete=models.PROTECT,
        primary_key=True,
        related_name="registry_entry",
    )
    active_revision = models.ForeignKey(
        EvidenceRevision, on_delete=models.PROTECT, related_name="active_for"
    )
    state = models.CharField(max_length=24, choices=State.choices, default=State.CURRENT)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["identity__economy", "identity__indicator_id"]


class EvidenceChangeSet(models.Model):
    """The reconciliation result produced whenever engine artifacts are imported."""

    class State(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    snapshot = models.OneToOneField(
        EngineSnapshot, on_delete=models.PROTECT, related_name="evidence_change_set"
    )
    previous_snapshot = models.ForeignKey(
        EngineSnapshot,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="successor_change_sets",
    )
    scope_json = models.JSONField(default=list)
    counts_json = models.JSONField(default=dict)
    state = models.CharField(max_length=16, choices=State.choices, default=State.DRAFT)
    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="published_evidence_change_sets",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class EvidenceChange(models.Model):
    class Kind(models.TextChoices):
        UNCHANGED = "unchanged", "Unchanged"
        REVISED = "revised", "Revised"
        NEW = "new", "New"
        NOT_REPRODUCED = "not_reproduced", "Not reproduced"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    change_set = models.ForeignKey(
        EvidenceChangeSet, on_delete=models.PROTECT, related_name="changes"
    )
    identity = models.ForeignKey(
        EvidenceIdentity, on_delete=models.PROTECT, related_name="changes"
    )
    previous_revision = models.ForeignKey(
        EvidenceRevision,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="outgoing_changes",
    )
    current_revision = models.ForeignKey(
        EvidenceRevision,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="incoming_changes",
    )
    kind = models.CharField(max_length=24, choices=Kind.choices)
    invalidated_stages_json = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["identity__economy", "identity__indicator_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["change_set", "identity"],
                name="workspace_change_set_identity_uniq",
            )
        ]


class EvidenceChangeDecision(ImmutableAuditModel):
    class Verdict(models.TextChoices):
        ACCEPT = "accept", "Accept candidate revision"
        RETAIN = "retain", "Retain current revision"
        RETIRE = "retire", "Retire missing evidence"
        INVESTIGATE = "investigate", "Needs investigation"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    change = models.ForeignKey(
        EvidenceChange, on_delete=models.PROTECT, related_name="decisions"
    )
    verdict = models.CharField(max_length=24, choices=Verdict.choices)
    comment = models.TextField()
    reviewer_name = models.CharField(max_length=255)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    supersedes = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="superseded_by",
    )

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["change", "-created_at"])]


class RunRecord(models.Model):
    snapshot = models.ForeignKey(
        EngineSnapshot, on_delete=models.CASCADE, related_name="run_records"
    )
    run_name = models.CharField(max_length=80)
    envelope_json = models.JSONField()
    cost_json = models.JSONField(default=dict)
    source_hash = models.CharField(max_length=64)

    class Meta:
        ordering = ["run_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["snapshot", "run_name"],
                name="workspace_run_snapshot_name_uniq",
            )
        ]


class SupersedingDecision(ImmutableAuditModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reviewer_name = models.CharField(max_length=255)
    reviewer_role = models.CharField(max_length=32)
    reviewed_at = models.DateTimeField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    authoritative_file_hash = models.CharField(max_length=64)
    writer_receipt_json = models.JSONField(default=dict)
    # Model backend: "hybrid" (Model A, the signed registry) or "local"
    # (Model B, open weights). The two workspaces never share rows.
    mode = models.CharField(max_length=16, default="hybrid", db_index=True)

    class Meta:
        abstract = True


class FindingDecision(SupersedingDecision):
    class Stage(models.TextChoices):
        CITATION = "citation", "Citation"
        MAPPING = "mapping", "Mapping"
        STATUS = "status", "Status"

    class Verdict(models.TextChoices):
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    finding_key = models.CharField(max_length=64)
    review_subject_hash = models.CharField(max_length=64, blank=True, default="")
    queue = models.CharField(
        max_length=16,
        choices=(
            (ReviewItem.Queue.NEW, "NEW"),
            (ReviewItem.Queue.KNOWN, "KNOWN"),
            (ReviewItem.Queue.ABSENCE, "Absence"),
        ),
    )
    review_stage = models.CharField(max_length=16, choices=Stage.choices)
    decision = models.CharField(max_length=16, choices=Verdict.choices)
    citation_checked = models.BooleanField(default=False)
    mapping_checked = models.BooleanField(default=False)
    status_checked = models.BooleanField(default=False)
    note = models.TextField(blank=True, default="")
    supersedes = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="superseded_by",
    )

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["finding_key", "review_stage", "-created_at"])]


class RecallDecision(SupersedingDecision):
    class Verdict(models.TextChoices):
        REAL_MISS = "REAL_MISS", "Real miss"
        GOLD_WRONG = "GOLD_WRONG", "Gold wrong"
        GOLD_AMBIGUOUS = "GOLD_AMBIGUOUS", "Gold ambiguous"
        CORRECT_ABSTENTION = "CORRECT_ABSTENTION", "Correct abstention"
        NEEDS_CORRECTION = "NEEDS_CORRECTION", "Needs correction"

    recall_key = models.CharField(max_length=64)
    verdict = models.CharField(max_length=32, choices=Verdict.choices)
    reasoning = models.TextField(blank=True, default="")
    official_source_url = models.URLField(max_length=1000, blank=True, default="")
    supersedes = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="superseded_by",
    )

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["recall_key", "-created_at"])]


class Zone3Decision(SupersedingDecision):
    class Verdict(models.TextChoices):
        APPROVED = "approved", "Approved"
        OVERRIDDEN = "overridden", "Overridden"

    score_key = models.CharField(max_length=64)
    verdict = models.CharField(max_length=16, choices=Verdict.choices)
    score = models.DecimalField(max_digits=2, decimal_places=1)
    reasoning = models.TextField(blank=True, default="")
    supersedes = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="superseded_by",
    )

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["score_key", "-created_at"])]


class CorrectionRequest(ImmutableAuditModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    finding_key = models.CharField(max_length=64)
    review_subject_hash = models.CharField(max_length=64, blank=True, default="")
    queue = models.CharField(max_length=16)
    explanation = models.TextField()
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="correction_requests",
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    authoritative_file_hash = models.CharField(max_length=64, blank=True, default="")
    # Model backend: "hybrid" (Model A, the signed registry) or "local"
    # (Model B, open weights). The two workspaces never share rows.
    mode = models.CharField(max_length=16, default="hybrid", db_index=True)

    writer_receipt_json = models.JSONField(default=dict)
    supersedes = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="superseded_by",
    )

    class Meta:
        ordering = ["requested_at"]
        indexes = [models.Index(fields=["finding_key", "-requested_at"])]


class Release(models.Model):
    class State(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        REVIEWING = "REVIEWING", "Reviewing"
        READY = "READY", "Ready"
        FROZEN = "FROZEN", "Frozen"
        SUPERSEDED = "SUPERSEDED", "Superseded"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    state = models.CharField(max_length=16, choices=State.choices, default=State.DRAFT)
    snapshot = models.ForeignKey(
        EngineSnapshot,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="releases",
    )
    supersedes = models.OneToOneField(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="superseded_by",
    )
    bundle_path = models.CharField(max_length=1000, blank=True, default="")
    bundle_hash = models.CharField(max_length=64, blank=True, default="")
    db_snapshot_hash = models.CharField(max_length=64, blank=True, default="")
    decision_hashes_json = models.JSONField(default=dict)
    engine_manifest_json = models.JSONField(default=dict)
    engine_git_sha = models.CharField(max_length=64, blank=True, default="")
    reviewer_identities_json = models.JSONField(default=list)
    final_artifact_hashes_json = models.JSONField(default=dict)
    transition_reason = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="releases_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    frozen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class EngineActionEvent(models.Model):
    """One live progress line of an engine action (run console), copied by the
    worker from the engine's CLAUSECHAIN_EVENT_LOG while the action runs."""

    action = models.ForeignKey("EngineAction", on_delete=models.CASCADE, related_name="events")
    seq = models.PositiveIntegerField()
    ts = models.DateTimeField()
    stage = models.CharField(max_length=32)
    label = models.CharField(max_length=160, blank=True, default="")
    level = models.CharField(max_length=8, default="info")
    message = models.TextField()
    detail = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["action", "seq"]
        constraints = [
            models.UniqueConstraint(fields=["action", "seq"], name="workspace_action_event_seq_uniq")
        ]


class EngineWorkerHeartbeat(models.Model):
    """Liveness signal written by run_engine_worker every few seconds (also
    while an action executes), read by the API to show worker status and to
    decide whether a queued action needs a worker started."""

    worker_id = models.CharField(max_length=255, unique=True)
    hostname = models.CharField(max_length=255)
    pid = models.IntegerField()
    started_at = models.DateTimeField()
    last_seen = models.DateTimeField()
    current_action_id = models.UUIDField(null=True, blank=True)

    class Meta:
        ordering = ["-last_seen"]


class EngineAction(models.Model):
    class Kind(models.TextChoices):
        REFRESH = "refresh", "Refresh"
        REPLAY = "replay", "Replay"
        RUN = "run", "Run"
        # Download (or clear) an economy's source documents; shared by both models.
        CORPUS = "corpus", "Sources"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.QUEUED
    )
    arguments_json = models.JSONField(default=dict)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    requested_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    lease_owner = models.CharField(max_length=255, blank=True, default="")
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    stdout = models.TextField(blank=True, default="")
    result_hashes_json = models.JSONField(default=dict)
    # Trimmed run envelope captured when a run_pipeline action succeeds, so run
    # modes without an imported snapshot (local open-weights runs) still have
    # something to show and compare. Never feeds the reviewed snapshot.
    result_json = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True, default="")
    # Cancellation: queued actions are cancelled directly; for a running one the
    # worker sees cancel_requested_at and stops the process group.
    cancel_requested_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.CharField(max_length=255, blank=True, default="")
    # "Clear" hides a finished action from the worker-action list; the row is
    # kept as the audit record (and any run results stay visible).
    cleared_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-requested_at"]
        indexes = [models.Index(fields=["status", "requested_at"])]
    class State(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"

