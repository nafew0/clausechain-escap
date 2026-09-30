import httpx
import pytest

from packages.providers import http_client
from packages.providers.embedding_provider import OpenAIEmbeddingProvider
from packages.providers.llm_providers import OpenAIChatProvider

REQUEST = httpx.Request("POST", "https://llm.example.test/v1/chat/completions")


class FlakyEndpoint:
    """Refuses new connections `outage` times, then answers."""

    def __init__(self, outage, reply):
        self.outage, self.reply, self.calls = outage, reply, 0

    def post(self, *args, **kwargs):
        self.calls += 1
        if self.calls <= self.outage:
            raise httpx.ConnectTimeout("[Errno 60] Operation timed out", request=REQUEST)
        return httpx.Response(200, request=REQUEST, json=self.reply)


@pytest.fixture
def no_waiting(monkeypatch):
    monkeypatch.setattr(http_client, "CONNECT_BACKOFFS_S", (0.0,) * 6)
    monkeypatch.setattr(OpenAIChatProvider, "RETRY_BACKOFFS_S", (0.0, 0.0))
    monkeypatch.setenv("LOCALAI_API_KEY", "test")


def chat_reply(content):
    return {"choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1}}


def test_a_brief_connection_outage_no_longer_ends_the_run(monkeypatch, no_waiting):
    # Before: three connect timeouts (~75 s each) ended the call and the whole run.
    endpoint = FlakyEndpoint(outage=5, reply=chat_reply('{"ok": true}'))
    monkeypatch.setattr(http_client, "client", lambda base_url, timeout: endpoint)
    provider = OpenAIChatProvider("qwen", api_key_env="LOCALAI_API_KEY", base_url="https://llm.example.test/v1")
    assert provider._call("prompt") == '{"ok": true}'
    assert endpoint.calls == 6


def test_an_endpoint_that_stays_down_still_fails_the_call(monkeypatch, no_waiting):
    endpoint = FlakyEndpoint(outage=100, reply=chat_reply("{}"))
    monkeypatch.setattr(http_client, "client", lambda base_url, timeout: endpoint)
    provider = OpenAIChatProvider("qwen", api_key_env="LOCALAI_API_KEY", base_url="https://llm.example.test/v1")
    with pytest.raises(httpx.ConnectTimeout):
        provider._call("prompt")
    assert endpoint.calls == 1 + len(http_client.CONNECT_BACKOFFS_S)


def test_connect_retries_do_not_use_up_the_server_error_budget(monkeypatch, no_waiting):
    replies = [httpx.ConnectTimeout("t", request=REQUEST)] * 3 + [
        httpx.Response(503, request=REQUEST), httpx.Response(503, request=REQUEST),
        httpx.Response(200, request=REQUEST, json=chat_reply("{}"))]

    class Mixed:
        def post(self, *args, **kwargs):
            reply = replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return reply

    monkeypatch.setattr(http_client, "client", lambda base_url, timeout: Mixed())
    provider = OpenAIChatProvider("qwen", api_key_env="LOCALAI_API_KEY", base_url="https://llm.example.test/v1")
    assert provider._call("prompt") == "{}"


def test_embeddings_ride_out_a_connection_outage(monkeypatch, no_waiting):
    endpoint = FlakyEndpoint(outage=3, reply={"data": [{"index": 0, "embedding": [0.1, 0.2]}]})
    monkeypatch.setattr(http_client, "client", lambda base_url, timeout: endpoint)
    provider = OpenAIEmbeddingProvider("bge-m3", api_key_env="LOCALAI_API_KEY",
                                       base_url="https://embed.example.test/v1")
    assert provider.embed(["text"]) == [[0.1, 0.2]]


def test_one_pooled_client_per_endpoint():
    first = http_client.client("https://llm.example.test/v1", 300)
    assert http_client.client("https://llm.example.test/v1", 300) is first
    assert first.timeout.connect == http_client.CONNECT_TIMEOUT_S
    assert http_client.client("https://other.example.test/v1", 300) is not first
