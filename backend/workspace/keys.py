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


def recall_key(economy, indicator, act, reference):
    identity = "|".join(
        normalized_part(item) for item in (economy, indicator, act, reference)
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def zone3_key(economy, indicator):
    identity = "|".join(normalized_part(item) for item in (economy, indicator))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()
