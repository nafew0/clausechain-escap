import hashlib
import json


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(value):
    if not isinstance(value, (bytes, bytearray)):
        value = canonical_json(value).encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def normalized_part(value):
    return " ".join(str(value or "").split()).casefold()


def _mode_scoped(identity, mode):
    # Local keys are namespaced; hybrid keys are unchanged.
    return identity if mode == "hybrid" else f"{mode}|{identity}"


def recall_key(economy, indicator, act, reference, mode="hybrid"):
    identity = "|".join(
        normalized_part(item) for item in (economy, indicator, act, reference)
    )
    return hashlib.sha256(_mode_scoped(identity, mode).encode("utf-8")).hexdigest()


def zone3_key(economy, indicator, mode="hybrid"):
    identity = "|".join(normalized_part(item) for item in (economy, indicator))
    return hashlib.sha256(_mode_scoped(identity, mode).encode("utf-8")).hexdigest()
