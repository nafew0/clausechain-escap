from rest_framework import serializers

from .models import FindingDecision, RecallDecision, ReviewItem, Zone3Decision


class ConcurrencySerializer(serializers.Serializer):
    expected_latest_decision_id = serializers.UUIDField(required=True, allow_null=True)


class FindingDecisionWriteSerializer(ConcurrencySerializer):
    finding_key = serializers.RegexField(r"^[0-9a-f]{64}$")
    queue = serializers.ChoiceField(
        choices=(ReviewItem.Queue.NEW, ReviewItem.Queue.KNOWN, ReviewItem.Queue.ABSENCE)
    )
    review_stage = serializers.ChoiceField(choices=FindingDecision.Stage.choices)
    decision = serializers.ChoiceField(choices=FindingDecision.Verdict.choices)
    citation_checked = serializers.BooleanField(default=False)
    mapping_checked = serializers.BooleanField(default=False)
    status_checked = serializers.BooleanField(default=False)
    note = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        stage = attrs["review_stage"]
        required_check = {
            FindingDecision.Stage.CITATION: "citation_checked",
            FindingDecision.Stage.MAPPING: "mapping_checked",
            FindingDecision.Stage.STATUS: "status_checked",
        }[stage]
        if (
            attrs["decision"] == FindingDecision.Verdict.APPROVED
            and not attrs[required_check]
        ):
            raise serializers.ValidationError(
                {
                    required_check: f"{required_check} is required for an approved {stage} review."
                }
            )
        if (
            attrs["decision"] == FindingDecision.Verdict.REJECTED
            and not attrs["note"].strip()
        ):
            raise serializers.ValidationError(
                {"note": "A rejection requires a written reason."}
            )
        return attrs


class FindingBulkDecisionWriteSerializer(serializers.Serializer):
    finding_keys = serializers.ListField(
        child=serializers.RegexField(r"^[0-9a-f]{64}$"), min_length=1, max_length=200
    )
    review_stage = serializers.ChoiceField(choices=FindingDecision.Stage.choices)
    citation_checked = serializers.BooleanField(default=False)
    mapping_checked = serializers.BooleanField(default=False)
    status_checked = serializers.BooleanField(default=False)
    note = serializers.CharField(required=False, allow_blank=True, default="")
    expected_latest_decision_ids = serializers.DictField(required=True)

    def validate(self, attrs):
        keys = attrs["finding_keys"]
        if len(keys) != len(set(keys)):
            raise serializers.ValidationError(
                {"finding_keys": "Duplicate finding keys are not allowed."}
            )
        expected = attrs["expected_latest_decision_ids"]
        if set(expected) != set(keys):
            raise serializers.ValidationError(
                {
                    "expected_latest_decision_ids": (
                        "Provide one concurrency token for every finding key."
                    )
                }
            )
        for key, value in expected.items():
            if value is None:
                continue
            try:
                expected[key] = serializers.UUIDField().to_internal_value(value)
            except serializers.ValidationError as exc:
                raise serializers.ValidationError(
                    {"expected_latest_decision_ids": f"Invalid decision id for {key}."}
                ) from exc
        required_check = {
            FindingDecision.Stage.CITATION: "citation_checked",
            FindingDecision.Stage.MAPPING: "mapping_checked",
            FindingDecision.Stage.STATUS: "status_checked",
        }[attrs["review_stage"]]
        if not attrs[required_check]:
            raise serializers.ValidationError(
                {required_check: f"{required_check} is required for bulk approval."}
            )
        return attrs


class RecallDecisionWriteSerializer(ConcurrencySerializer):
    recall_key = serializers.RegexField(r"^[0-9a-f]{64}$")
    verdict = serializers.ChoiceField(choices=RecallDecision.Verdict.choices)
    reasoning = serializers.CharField(required=False, allow_blank=True, default="")
    official_source_url = serializers.URLField(
        required=False, allow_blank=True, default=""
    )

    def validate(self, attrs):
        if (
            attrs["verdict"] == RecallDecision.Verdict.NEEDS_CORRECTION
            and not attrs["reasoning"].strip()
        ):
            raise serializers.ValidationError(
                {"reasoning": "A correction verdict requires a written reason."}
            )
        return attrs


class Zone3DecisionWriteSerializer(ConcurrencySerializer):
    score_key = serializers.RegexField(r"^[0-9a-f]{64}$")
    verdict = serializers.ChoiceField(choices=Zone3Decision.Verdict.choices)
    score = serializers.DecimalField(max_digits=2, decimal_places=1)
    reasoning = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        if attrs["score"] not in (0, 0.5, 1):
            raise serializers.ValidationError({"score": "Score must be 0, 0.5, or 1."})
        if (
            attrs["verdict"] == Zone3Decision.Verdict.OVERRIDDEN
            and not attrs["reasoning"].strip()
        ):
            raise serializers.ValidationError(
                {"reasoning": "An override requires reasoning."}
            )
        return attrs


class CorrectionRequestWriteSerializer(serializers.Serializer):
    finding_key = serializers.RegexField(r"^[0-9a-f]{64}$")
    queue = serializers.ChoiceField(
        choices=(ReviewItem.Queue.NEW, ReviewItem.Queue.KNOWN, ReviewItem.Queue.ABSENCE)
    )
    explanation = serializers.CharField(min_length=3)
    expected_latest_correction_id = serializers.UUIDField(
        required=True, allow_null=True
    )
