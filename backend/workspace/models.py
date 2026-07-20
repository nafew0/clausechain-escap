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

    class Meta:
        ordering = ["-imported_at"]
        indexes = [models.Index(fields=["active", "-imported_at"])]
        constraints = [
            models.UniqueConstraint(
                fields=["active"],
                condition=models.Q(active=True),
                name="workspace_one_active_snapshot",
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
    queue = models.CharField(max_length=16)
    explanation = models.TextField()
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="correction_requests",
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    authoritative_file_hash = models.CharField(max_length=64, blank=True, default="")
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


class EngineAction(models.Model):
    class Kind(models.TextChoices):
        REFRESH = "refresh", "Refresh"
        REPLAY = "replay", "Replay"
        RUN = "run", "Run"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

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
    error = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-requested_at"]
        indexes = [models.Index(fields=["status", "requested_at"])]
