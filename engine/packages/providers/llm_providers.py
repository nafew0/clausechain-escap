"""LLM provider implementations behind the `LLMProvider` protocol.

Plain REST via httpx (no vendor SDKs): keeps the dependency surface small and
makes the modular-swap story literal. All providers are constructed cheaply;
API keys are only required at call time.
"""
from __future__ import annotations

import json
import os
import sys

import httpx
from pydantic import BaseModel, ValidationError


def _schema_instruction(schema: type[BaseModel]) -> str:
    return (
        "\n\nReturn ONLY a JSON object (no markdown, no prose) matching this JSON schema:\n"
        + json.dumps(schema.model_json_schema(), ensure_ascii=False)
    )


class OpenAIChatProvider:
    def __init__(self, model: str, api_key_env: str = "OPENAI_API_KEY", timeout: float = 90.0) -> None:
        self.model = model
        self.api_key_env = api_key_env
        self.timeout = timeout
        self.last_usage: dict | None = None
        self._batch_available: bool | None = None

    RETRY_BACKOFFS_S = (5.0, 20.0)   # transient 429/5xx/network retries before giving up

    def _call(self, prompt: str, prompt_cache_key: str | None = None) -> str:
        import time as _time

        api_key = os.getenv(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"{self.api_key_env} is not set")
        last_error: Exception | None = None
        for attempt in range(1 + len(self.RETRY_BACKOFFS_S)):
            try:
                body = {
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                    "temperature": 0,
                }
                if prompt_cache_key:
                    body["prompt_cache_key"] = prompt_cache_key
                response = httpx.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=body,
                    timeout=self.timeout,
                )
                if response.status_code == 429 or response.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"retryable {response.status_code}", request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                payload = response.json()
                self.last_usage = payload.get("usage")
                if self.last_usage:
                    from packages.providers import cost

                    details = self.last_usage.get("prompt_tokens_details") or {}
                    cost.record(
                        self.model,
                        self.last_usage.get("prompt_tokens", 0),
                        self.last_usage.get("completion_tokens", 0),
                        cached_input_tokens=details.get("cached_tokens", 0),
                    )
                return payload["choices"][0]["message"]["content"]
            except (httpx.HTTPStatusError, httpx.TransportError) as error:
                last_error = error
                if attempt < len(self.RETRY_BACKOFFS_S):
                    _time.sleep(self.RETRY_BACKOFFS_S[attempt])
        raise last_error  # type: ignore[misc]

    def complete(self, prompt: str, schema: type[BaseModel], *,
                 prompt_cache_key: str | None = None) -> BaseModel:
        full_prompt = prompt + _schema_instruction(schema)
        text = self._call(full_prompt, prompt_cache_key)
        try:
            return schema.model_validate_json(text)
        except ValidationError as error:
            retry_prompt = (
                f"{full_prompt}\n\nYour previous answer was invalid: {error}\n"
                f"Previous answer: {text}\nFix it and return only valid JSON."
            )
            return schema.model_validate_json(self._call(retry_prompt, prompt_cache_key))

    def complete_many(self, prompts: list[str], schema: type[BaseModel], *,
                      prompt_cache_keys: list[str] | None = None) -> list[BaseModel]:
        """Use OpenAI Batch when explicitly enabled; otherwise preserve live latency."""
        keys = prompt_cache_keys or [None] * len(prompts)
        def synchronous() -> list[BaseModel]:
            # These mapping requests are independent. A bounded worker pool keeps
            # live runs from paying one network round trip at a time while
            # preserving input order and the provider's existing retry policy.
            workers = max(1, int(os.getenv("CLAUSECHAIN_LLM_CONCURRENCY", "6")))
            if workers == 1 or len(prompts) < 2:
                return [self.complete(p, schema, prompt_cache_key=k)
                        for p, k in zip(prompts, keys, strict=True)]
            from concurrent.futures import ThreadPoolExecutor

            def invoke(item):
                prompt, key = item
                return self.complete(prompt, schema, prompt_cache_key=key)

            with ThreadPoolExecutor(max_workers=min(workers, len(prompts))) as pool:
                return list(pool.map(invoke, zip(prompts, keys, strict=True)))

        if (os.getenv("CLAUSECHAIN_OPENAI_BATCH") != "1" or len(prompts) < 2
                or self._batch_available is False):
            return synchronous()

        import time as _time

        api_key = os.getenv(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"{self.api_key_env} is not set")
        headers = {"Authorization": f"Bearer {api_key}"}
        lines = []
        for index, (prompt, key) in enumerate(zip(prompts, keys, strict=True)):
            body = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt + _schema_instruction(schema)}],
                "response_format": {"type": "json_object"},
                "temperature": 0,
            }
            if key:
                body["prompt_cache_key"] = key
            lines.append(json.dumps({"custom_id": f"request-{index}", "method": "POST",
                                     "url": "/v1/chat/completions", "body": body}))
        content = ("\n".join(lines) + "\n").encode()
        upload = httpx.post(
            "https://api.openai.com/v1/files", headers=headers,
            data={"purpose": "batch"},
            files={"file": ("clausechain-batch.jsonl", content, "application/jsonl")},
            timeout=self.timeout,
        )
        if upload.status_code in {401, 403, 404}:
            self._batch_available = False
            print(f"[model-router] OpenAI Batch/Files unavailable ({upload.status_code}); "
                  "using the same model synchronously", file=sys.stderr)
            return synchronous()
        upload.raise_for_status()
        self._batch_available = True
        created = httpx.post(
            "https://api.openai.com/v1/batches", headers=headers,
            json={"input_file_id": upload.json()["id"],
                  "endpoint": "/v1/chat/completions", "completion_window": "24h",
                  "metadata": {"project": "clausechain"}}, timeout=self.timeout,
        )
        if created.status_code in {401, 403, 404}:
            self._batch_available = False
            print(f"[model-router] OpenAI Batch unavailable ({created.status_code}); "
                  "using the same model synchronously", file=sys.stderr)
            return synchronous()
        created.raise_for_status()
        batch_id = created.json()["id"]
        poll_seconds = float(os.getenv("CLAUSECHAIN_BATCH_POLL_SECONDS", "15"))
        while True:
            status = httpx.get(f"https://api.openai.com/v1/batches/{batch_id}",
                               headers=headers, timeout=self.timeout)
            status.raise_for_status()
            payload = status.json()
            if payload["status"] == "completed":
                output_file_id = payload["output_file_id"]
                break
            if payload["status"] in {"failed", "expired", "cancelled"}:
                raise RuntimeError(f"OpenAI batch {batch_id} ended as {payload['status']}: "
                                   f"{payload.get('errors')}")
            _time.sleep(min(max(poll_seconds, 1.0), 60.0))
        output = httpx.get(f"https://api.openai.com/v1/files/{output_file_id}/content",
                           headers=headers, timeout=self.timeout)
        output.raise_for_status()
        by_index: dict[int, BaseModel] = {}
        for line in output.text.splitlines():
            row = json.loads(line)
            index = int(row["custom_id"].removeprefix("request-"))
            if row.get("error"):
                raise RuntimeError(f"Batch item {index} failed: {row['error']}")
            body = row["response"]["body"]
            usage = body.get("usage") or {}
            details = usage.get("prompt_tokens_details") or {}
            from packages.providers import cost
            cost.record(self.model, usage.get("prompt_tokens", 0),
                        usage.get("completion_tokens", 0),
                        cached_input_tokens=details.get("cached_tokens", 0), batch=True)
            by_index[index] = schema.model_validate_json(
                body["choices"][0]["message"]["content"])
        if len(by_index) != len(prompts):
            raise RuntimeError(f"Batch returned {len(by_index)}/{len(prompts)} results")
        return [by_index[i] for i in range(len(prompts))]


class GeminiChatProvider:
    def __init__(self, model: str, api_key_env: str = "GEMINI_API_KEY", timeout: float = 90.0) -> None:
        self.model = model
        self.api_key_env = api_key_env
        self.timeout = timeout
        self.last_usage: dict | None = None

    def _call(self, prompt: str) -> str:
        api_key = os.getenv(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"{self.api_key_env} is not set")
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={api_key}"
        )
        response = httpx.post(
            url,
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json"},
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        self.last_usage = payload.get("usageMetadata")
        return payload["candidates"][0]["content"]["parts"][0]["text"]

    def complete(self, prompt: str, schema: type[BaseModel], *,
                 prompt_cache_key: str | None = None) -> BaseModel:
        full_prompt = prompt + _schema_instruction(schema)
        text = self._call(full_prompt)
        try:
            return schema.model_validate_json(text)
        except ValidationError as error:
            retry_prompt = (
                f"{full_prompt}\n\nYour previous answer was invalid: {error}\n"
                f"Previous answer: {text}\nFix it and return only valid JSON."
            )
            return schema.model_validate_json(self._call(retry_prompt))


class FallbackLLM:
    """Try the primary provider; on any error, use the fallback and log it."""

    def __init__(self, primary, fallback=None) -> None:
        self.primary = primary
        self.fallback = fallback

    def complete(self, prompt: str, schema: type[BaseModel], *,
                 prompt_cache_key: str | None = None) -> BaseModel:
        def call(provider):
            try:
                return provider.complete(prompt, schema, prompt_cache_key=prompt_cache_key)
            except TypeError as error:
                # Keep test/local third-party providers conforming to the older
                # two-argument protocol usable while cache keys remain optional.
                if "prompt_cache_key" not in str(error):
                    raise
                return provider.complete(prompt, schema)

        try:
            return call(self.primary)
        except Exception as error:  # noqa: BLE001 — any primary failure triggers fallback
            if self.fallback is None:
                raise
            print(f"[model-router] primary failed ({error!r}); using fallback", file=sys.stderr)
            try:
                return call(self.fallback)
            except Exception as fallback_error:  # noqa: BLE001
                # an unusable fallback (e.g. no API key) must not mask the real failure
                raise error from fallback_error

    def complete_many(self, prompts: list[str], schema: type[BaseModel], *,
                      prompt_cache_keys: list[str] | None = None) -> list[BaseModel]:
        try:
            if hasattr(self.primary, "complete_many"):
                return self.primary.complete_many(
                    prompts, schema, prompt_cache_keys=prompt_cache_keys)
            return [self.complete(p, schema,
                                  prompt_cache_key=(prompt_cache_keys or [None] * len(prompts))[i])
                    for i, p in enumerate(prompts)]
        except Exception as error:  # noqa: BLE001
            if self.fallback is None:
                raise
            print(f"[model-router] primary batch failed ({error!r}); using fallback",
                  file=sys.stderr)
            return [self.fallback.complete(p, schema) for p in prompts]


class OllamaProvider:
    """Local LLM via Ollama's REST API — key-free (Path A). No network in __init__."""

    def __init__(self, model: str, base_url: str | None = None, timeout: float = 180.0) -> None:
        self.model = model
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.timeout = timeout
        self.last_usage: dict | None = None

    def _call(self, prompt: str) -> str:
        response = httpx.post(
            f"{self.base_url}/api/generate",
            json={"model": self.model, "prompt": prompt, "stream": False, "format": "json"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()["response"]

    def complete(self, prompt: str, schema: type[BaseModel], *,
                 prompt_cache_key: str | None = None) -> BaseModel:
        full_prompt = prompt + _schema_instruction(schema)
        text = self._call(full_prompt)
        try:
            return schema.model_validate_json(text)
        except ValidationError as error:
            retry_prompt = (
                f"{full_prompt}\n\nYour previous answer was invalid: {error}\n"
                f"Previous answer: {text}\nFix it and return only valid JSON."
            )
            return schema.model_validate_json(self._call(retry_prompt))


def build_llm(spec: str):
    """Build a provider from a 'provider:model' spec, e.g. 'openai:gpt-5.4-nano'."""
    provider, _, model = spec.partition(":")
    provider = provider.strip().lower()
    model = model.strip()
    if not model:
        raise ValueError(f"Model spec {spec!r} must look like 'provider:model'")
    if provider == "openai":
        return OpenAIChatProvider(model)
    if provider in {"google", "gemini"}:
        return GeminiChatProvider(model)
    if provider == "ollama":
        return OllamaProvider(model)
    raise ValueError(f"Unknown LLM provider in spec {spec!r}")
