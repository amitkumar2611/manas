"""Shared HTTP helper for integrations. Transport is injectable so every
adapter gets an offline contract test (coding standard: no untested provider)."""
import httpx

from manas.kernel.errors import ProviderError

_transport: httpx.BaseTransport | None = None      # tests inject a mock here


def set_transport(t: httpx.BaseTransport | None) -> None:
    global _transport
    _transport = t


def request(method: str, url: str, *, auth=None, headers=None,
            json_body=None, timeout: int = 30) -> dict | list:
    with httpx.Client(transport=_transport, auth=auth,
                      headers=headers or {}, timeout=timeout) as c:
        r = c.request(method, url, json=json_body)
    if r.status_code >= 400:
        raise ProviderError(f"{method} {url} -> {r.status_code}: {r.text[:200]}")
    return r.json() if r.content else {}
