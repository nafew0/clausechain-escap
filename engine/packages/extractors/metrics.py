from __future__ import annotations

import re


def _distance(reference: list[str], hypothesis: list[str]) -> int:
    previous = list(range(len(hypothesis) + 1))
    for i, left in enumerate(reference, 1):
        current = [i]
        for j, right in enumerate(hypothesis, 1):
            current.append(min(current[-1] + 1, previous[j] + 1,
                               previous[j - 1] + (left != right)))
        previous = current
    return previous[-1]


def cer(reference: str, hypothesis: str) -> float:
    return _distance(list(reference), list(hypothesis)) / max(len(reference), 1)


def wer(reference: str, hypothesis: str) -> float:
    return _distance(reference.split(), hypothesis.split()) / max(len(reference.split()), 1)


_CITATION = re.compile(r"\b\d+(?:\.\d+)?[A-Z]{0,3}\b|\([a-z0-9ivxlcdm]+\)", re.I)


def citation_token_accuracy(reference: str, hypothesis: str) -> float:
    expected = _CITATION.findall(reference)
    actual = _CITATION.findall(hypothesis)
    return 1.0 - _distance(expected, actual) / max(len(expected), 1)


def section_structure_accuracy(reference_paths: list[list[str]],
                               hypothesis_paths: list[list[str]]) -> float:
    expected = {tuple(p) for p in reference_paths}
    actual = {tuple(p) for p in hypothesis_paths}
    return len(expected & actual) / max(len(expected), 1)


def citation_tokens_disagree(first: str, second: str) -> bool:
    return _CITATION.findall(first) != _CITATION.findall(second)
