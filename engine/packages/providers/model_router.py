from __future__ import annotations

from pathlib import Path
import os
import re
from typing import Any

import yaml


ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}")


def _expand_env(value: Any) -> Any:
    if isinstance(value, str):
        def replace(match: re.Match[str]) -> str:
            name, default = match.group(1), match.group(2) or ""
            return os.getenv(name, default)

        return ENV_PATTERN.sub(replace, value)
    if isinstance(value, dict):
        return {key: _expand_env(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_expand_env(item) for item in value]
    return value


def load_model_profiles(config_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(config_path) if config_path else Path(__file__).parents[2] / "configs" / "models.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return _expand_env(data)


def get_profile(name: str = "hybrid_accuracy") -> dict[str, Any]:
    profiles = load_model_profiles().get("profiles", {})
    if name not in profiles:
        raise KeyError(f"Unknown provider profile: {name}")
    return profiles[name]


def resolve_llm(profile_name: str = "hybrid_accuracy", tier: str = "bulk"):
    """Return an LLM for bulk, nano-first legal, or mini escalation work."""
    from packages.providers.llm_providers import FallbackLLM, build_llm

    profile = get_profile(profile_name)
    tier_config = profile.get(tier)
    if not tier_config:
        raise KeyError(f"Profile {profile_name!r} has no tier {tier!r}")
    primary = build_llm(tier_config["primary"])
    fallback_spec = tier_config.get("fallback")
    fallback = build_llm(fallback_spec) if fallback_spec else None
    return FallbackLLM(primary, fallback)


def resolve_embedding(profile_name: str = "hybrid_accuracy"):
    """Return the embedding provider configured for a profile."""
    from packages.providers.embedding_provider import build_embedding

    return build_embedding(get_profile(profile_name).get("embedding", {}))


def resolve_ocr(profile_name: str = "hybrid_accuracy"):
    """Return the OCR engine configured for a profile (local placeholder or remote PaddleOCR)."""
    from packages.providers.ocr_provider import build_ocr

    return build_ocr(get_profile(profile_name).get("ocr", {}))
