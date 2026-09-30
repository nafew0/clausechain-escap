"""Pooled HTTP clients for model endpoints, and the connection-failure retry policy.

A run calls a model endpoint hundreds of times. Opening a fresh TCP+TLS
connection per call made every run as fragile as its worst minute on the
network: while the self-hosted GPU box stopped answering new connections for a
while (29 Sep: Malaysia P7, Mongolia P7 and Russia P6 local runs), each connect
hung ~75 s until the OS gave up, and three such failures ended the whole run.

Now each endpoint gets one shared keep-alive client (thread-safe), so a run
reuses a handful of connections instead of opening hundreds; a connect gives up
after CONNECT_TIMEOUT_S; and connection failures get their own, longer retry
schedule. A request that never connected never reached the model, so resending
it is always safe.
"""

from __future__ import annotations

import os
import threading

import httpx

CONNECT_TIMEOUT_S = float(os.getenv("CLAUSECHAIN_CONNECT_TIMEOUT_S", "10"))
# ~2 minutes of patience for an endpoint that briefly refuses new connections.
CONNECT_BACKOFFS_S = (2.0, 5.0, 10.0, 20.0, 30.0, 60.0)
CONNECT_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)

_clients: dict[tuple[str, float], httpx.Client] = {}
_lock = threading.Lock()


def client(base_url: str, timeout: float) -> httpx.Client:
    """The shared client for one endpoint (read timeout = the provider's timeout)."""
    key = (base_url, float(timeout))
    with _lock:
        existing = _clients.get(key)
        if existing is None or existing.is_closed:
            existing = httpx.Client(
                timeout=httpx.Timeout(float(timeout), connect=CONNECT_TIMEOUT_S),
                limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
            )
            _clients[key] = existing
        return existing
