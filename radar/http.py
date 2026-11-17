"""Ortak HTTP istemcisi: gerçek Chrome TLS parmak izini taklit eden curl_cffi."""

from __future__ import annotations

import random
import time

from curl_cffi import requests as creq

HEADERS = {
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
}


class FetchError(RuntimeError):
    pass


_session: creq.Session | None = None


def session() -> creq.Session:
    global _session
    if _session is None:
        _session = creq.Session(impersonate="chrome", headers=HEADERS, timeout=25)
    return _session


def get(url: str, *, retries: int = 2, polite: float = float(__import__("os").getenv("HTTP_POLITE", "1.5")), **kw) -> str:
    """Metni döndürür. 429/5xx'te kısa bekleyip tekrar dener, diğer hatalarda FetchError."""
    last = None
    for attempt in range(retries + 1):
        time.sleep(polite + random.random())
        try:
            r = session().get(url, **kw)
        except Exception as e:  # noqa: BLE001  (ağ hatası)
            last = f"{type(e).__name__}: {e}"[:200]
            continue
        if r.status_code == 200:
            return r.text
        last = f"HTTP {r.status_code}"
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(5 * (attempt + 1))
            continue
        break
    raise FetchError(f"{url} -> {last}")
