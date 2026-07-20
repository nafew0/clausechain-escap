from types import SimpleNamespace

from packages.providers import cost
from packages.rdtii.mapper import MapDecision, map_candidates


class QueueLLM:
    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.calls = []

    def complete_many(self, prompts, schema, *, prompt_cache_keys=None):
        self.calls.append((prompts, prompt_cache_keys))
        count = len(prompts)
        result, self.decisions = self.decisions[:count], self.decisions[count:]
        return result


def candidate(text="The operator must keep the records in Singapore."):
    return SimpleNamespace(
        provision_id="p1", text=text,
        props={"law_name": "Example Act", "article_section": "s 1", "heading": "Duty"},
    )


def decision(*, applies=True, snippet="The operator must keep the records in Singapore.",
             confidence=0.95):
    return MapDecision(applies=applies, verbatim_snippet=snippet,
                       rationale="The section requires record keeping.", confidence=confidence,
                       modality="must", action="keep records")


def test_confident_source_exact_nano_mapping_does_not_escalate():
    nano = QueueLLM([decision()])
    mini = QueueLLM([])
    result = map_candidates(nano, "7.3", {"name": "Retention", "question": "Duty?"},
                            [candidate()], set(), mini)
    assert result[0]._model_route == "nano"
    assert not result[0]._escalation_reasons
    assert len(nano.calls) == 1
    assert not mini.calls
    assert nano.calls[0][1] == ["clausechain:map:v3:7.3"]


def test_rejected_known_anchor_is_escalated_to_mini():
    nano = QueueLLM([decision(applies=False, snippet="", confidence=0.9)])
    mini = QueueLLM([decision()])
    result = map_candidates(nano, "7.3", {"name": "Retention", "question": "Duty?"},
                            [candidate()], {"p1"}, mini)
    assert result[0]._model_route == "mini-escalation"
    assert result[0]._escalation_reasons == ["known-anchor-rejected"]
    assert len(mini.calls) == 1
    assert mini.calls[0][1] == ["clausechain:legal-escalation:v1:7.3"]


def test_cost_report_prices_cached_and_batch_tokens_separately():
    cost.reset()
    cost.record("gpt-5.4-nano", 1_000_000, 1_000_000,
                cached_input_tokens=500_000)
    cost.record("gpt-5.4-nano", 1_000_000, 1_000_000, batch=True)
    report = cost.report()
    assert report["models"]["gpt-5.4-nano"]["usd"] == 1.36
    assert report["models"]["gpt-5.4-nano [batch]"]["usd"] == 0.725
    assert report["total_usd"] == 2.085

