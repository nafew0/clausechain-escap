import json
from urllib import error, request


class AITestConnectionError(Exception):
    pass


class AITestService:
    OPENAI_URL = "https://api.openai.com/v1/responses"
    ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

    @classmethod
    def test_connection(cls, *, provider, model, api_key):
        normalized_provider = (provider or "").strip().lower()
        normalized_model = (model or "").strip()
        normalized_key = (api_key or "").strip()

        if not normalized_provider:
            raise AITestConnectionError("Select an AI provider first.")
        if not normalized_model:
            raise AITestConnectionError("Provide a model name first.")
        if not normalized_key:
            raise AITestConnectionError("Provide an API key first.")

        if normalized_provider == "openai":
            return cls._test_openai(normalized_model, normalized_key)
        if normalized_provider == "anthropic":
            return cls._test_anthropic(normalized_model, normalized_key)
        raise AITestConnectionError("Unsupported AI provider.")

    @classmethod
    def _read_response(cls, response):
        try:
            return json.loads(response.read().decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise AITestConnectionError("The AI provider returned malformed JSON.") from exc

    @classmethod
    def _request(cls, http_request):
        try:
            with request.urlopen(http_request, timeout=20) as response:
                return cls._read_response(response)
        except error.HTTPError as exc:
            message = exc.reason
            try:
                payload = json.loads(exc.read().decode("utf-8"))
                message = payload.get("error", {}).get("message") or payload.get(
                    "message"
                ) or message
            except Exception:
                pass
            raise AITestConnectionError(str(message)) from exc
        except error.URLError as exc:
            raise AITestConnectionError("Could not reach the AI provider.") from exc

    @classmethod
    def _test_openai(cls, model, api_key):
        payload = {
            "model": model,
            "instructions": "Reply with OK only.",
            "input": "Reply with OK.",
            "max_output_tokens": 160,
        }
        if cls._should_use_openai_reasoning(model):
            payload["reasoning"] = {"effort": "low"}
        http_request = request.Request(
            cls.OPENAI_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        response_payload = cls._request(http_request)
        status = (response_payload.get("status") or "").strip().lower()
        output_text = cls._extract_openai_text(response_payload)
        if output_text and status in {"completed", "incomplete"}:
            return {
                "provider": "openai",
                "model": model,
                "message": "OpenAI connection succeeded.",
            }
        if status == "incomplete":
            incomplete_reason = (
                response_payload.get("incomplete_details", {}).get("reason")
                or "response_incomplete"
            )
            raise AITestConnectionError(
                f"The OpenAI response was incomplete ({incomplete_reason})."
            )
        if status != "completed":
            raise AITestConnectionError("The OpenAI request did not complete.")
        raise AITestConnectionError("The OpenAI response did not contain text.")

    @classmethod
    def _test_anthropic(cls, model, api_key):
        payload = {
            "model": model,
            "max_tokens": 16,
            "messages": [{"role": "user", "content": "Reply with OK."}],
        }
        http_request = request.Request(
            cls.ANTHROPIC_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            method="POST",
        )
        response_payload = cls._request(http_request)
        if not response_payload.get("id"):
            raise AITestConnectionError("The Anthropic request did not complete.")
        return {
            "provider": "anthropic",
            "model": model,
            "message": "Anthropic connection succeeded.",
        }

    @classmethod
    def _should_use_openai_reasoning(cls, model):
        normalized_model = (model or "").strip().lower()
        return normalized_model.startswith(("gpt-5", "o1", "o3", "o4"))

    @classmethod
    def _extract_openai_text(cls, response_payload):
        direct_output_text = (response_payload.get("output_text") or "").strip()
        if direct_output_text:
            return direct_output_text

        collected_parts = []
        for item in response_payload.get("output", []):
            if not isinstance(item, dict):
                continue
            for content_part in item.get("content", []):
                if not isinstance(content_part, dict):
                    continue
                part_type = (content_part.get("type") or "").strip().lower()
                if part_type in {"output_text", "text"} and content_part.get("text"):
                    collected_parts.append(content_part["text"])

        return "\n".join(part.strip() for part in collected_parts if part and part.strip()).strip()
