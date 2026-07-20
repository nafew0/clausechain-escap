"""AI-2 P0 spike: prove real model routing through the provider interfaces.

Checks (needs OPENAI_API_KEY; GEMINI_API_KEY optional for the fallback leg):
1. bulk-tier chat completion returns schema-valid JSON
2. embeddings on 5 legal clauses return vectors with the configured dimensions
3. (if GEMINI_API_KEY) the Gemini fallback path works

Usage (from engine/):  uv run python scripts/spike_providers.py [--profile hybrid_accuracy]
"""
from __future__ import annotations

import argparse

from packages.core.envfile import load_env_file

load_env_file()
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import BaseModel  # noqa: E402

from packages.providers.llm_providers import GeminiChatProvider  # noqa: E402
from packages.providers.model_router import resolve_embedding, resolve_llm  # noqa: E402

CLAUSES = [
    "An organisation shall not transfer any personal data to a country or territory outside Singapore except in accordance with requirements prescribed under this Act.",
    "Personal data shall be stored in a database located in the territory of the Republic of Kazakhstan.",
    "The licensee must maintain at least one server within the territory to provide the service.",
    "Records of every transaction shall be retained for a period of not less than six years.",
    "A police officer may, at any time, access, inspect and check the operation of a computer and use it to search any data contained in it.",
]


class Ping(BaseModel):
    ok: bool
    note: str


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default=os.getenv("CLAUSECHAIN_PROVIDER_PROFILE", "hybrid_accuracy"))
    args = parser.parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        print("FAIL: OPENAI_API_KEY is not set (copy .env.example to .env and fill it, "
              "then run: set -a; source .env; set +a)", file=sys.stderr)
        return 1

    failures = 0

    # 1) bulk chat
    llm = resolve_llm(args.profile, tier="bulk")
    try:
        result = llm.complete('Reply with {"ok": true, "note": "routing works"}', Ping)
        usage = getattr(llm.primary, "last_usage", None)
        print(f"PASS bulk LLM ({llm.primary.__class__.__name__}:{llm.primary.model}) -> {result!r} usage={usage}")
    except Exception as error:  # noqa: BLE001
        failures += 1
        print(f"FAIL bulk LLM: {error!r}", file=sys.stderr)

    # 2) embeddings
    embedder = resolve_embedding(args.profile)
    try:
        vectors = embedder.embed(CLAUSES)
        dims = {len(v) for v in vectors}
        print(f"PASS embeddings ({embedder.__class__.__name__}:{getattr(embedder, 'model', 'stub')}) "
              f"-> {len(vectors)} vectors, dims={dims}, usage={getattr(embedder, 'last_usage', None)}")
        expected = getattr(embedder, "dimensions", None)
        if expected and dims != {expected}:
            failures += 1
            print(f"FAIL embeddings: expected dims {expected}, got {dims}", file=sys.stderr)
    except Exception as error:  # noqa: BLE001
        failures += 1
        print(f"FAIL embeddings: {error!r}", file=sys.stderr)

    # 3) gemini fallback leg (optional)
    if os.getenv("GEMINI_API_KEY"):
        model = os.getenv("GEMINI_BULK_MODEL", "gemini-3-flash-preview")
        try:
            gemini = GeminiChatProvider(model)
            result = gemini.complete('Reply with {"ok": true, "note": "fallback works"}', Ping)
            print(f"PASS gemini fallback ({model}) -> {result!r}")
        except Exception as error:  # noqa: BLE001
            failures += 1
            print(f"FAIL gemini fallback: {error!r}", file=sys.stderr)
    else:
        print("SKIP gemini fallback (GEMINI_API_KEY not set)")

    print("SPIKE RESULT:", "PASS" if failures == 0 else f"{failures} FAILURE(S)")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
