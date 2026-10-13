"""HTTP-Client-Wrapper für mydealz.de (nur lesen).

Stellt eine dünne Abstraktion bereit, die in Tests mit einem
Fake ersetzt werden kann. Polsterung: MyDealz' Vue3-SSR-HTML
ist groß (≈ 280 KB), aber schlank zu parsen – eine Anfrage pro
Suche reicht.

Höflichkeit:
- Konservativer User-Agent mit Repo-URL.
- 1 Request/s als Default-Rate-Limit (konfigurierbar via
  ``MDZ_MIN_INTERVAL_MS``).
- ``Retry-After`` wird respektiert, falls die Plattform 429
  zurückgibt.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

import requests

UA = "mydealz-cli/0.1.0 (+https://github.com/smlfg/mydealz-cli)"


class HTTPError(Exception):
    """Netzwerk- oder HTTP-Fehler (Exit 3)."""

    def __init__(self, message: str, status: Optional[int] = None, url: Optional[str] = None):
        super().__init__(message)
        self.status = status
        self.url = url


class ParseError(Exception):
    """Antwort konnte nicht wie erwartet geparst werden (Exit 4)."""

    def __init__(self, message: str, url: Optional[str] = None):
        super().__init__(message)
        self.url = url


@dataclass
class Response:
    status: int
    url: str
    text: str
    headers: dict = field(default_factory=dict)
    cookies: dict = field(default_factory=dict)


class _RateLimiter:
    """Thread-safe minimaler Rate-Limiter.

    Stellt sicher, dass zwischen zwei ``get``-Aufrufen mindestens
    ``min_interval_s`` Sekunden liegen.
    """

    def __init__(self, min_interval_s: float):
        self.min_interval_s = min_interval_s
        self._last = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            wait_for = self.min_interval_s - (now - self._last)
            if wait_for > 0:
                time.sleep(wait_for)
            self._last = time.monotonic()


class HttpClient:
    """Einfache Wrapper-Klasse, austauschbar in Tests."""

    def __init__(
        self,
        user_agent: str = UA,
        timeout: float = 30.0,
        session: Optional[requests.Session] = None,
        min_interval_s: Optional[float] = None,
    ):
        self.user_agent = user_agent
        self.timeout = timeout
        self._session = session or requests.Session()
        self._session.headers["User-Agent"] = user_agent
        self._session.headers["Accept"] = "text/html"
        self._session.headers["Accept-Language"] = "de-DE,de;q=0.9,en;q=0.5"
        self._session.headers["Accept-Encoding"] = "gzip, deflate"
        if min_interval_s is None:
            env = os.environ.get("MDZ_MIN_INTERVAL_MS")
            min_interval_s = (int(env) / 1000.0) if env else 1.0
        self._limiter = _RateLimiter(min_interval_s)

    def get(self, url: str, *, allow_redirects: bool = True, _retries: int = 1) -> Response:
        self._limiter.wait()
        try:
            r = self._session.get(url, timeout=self.timeout, allow_redirects=allow_redirects)
        except requests.RequestException as e:
            raise HTTPError(f"GET {url} failed: {e}", url=url) from e
        if r.status_code == 429 and _retries > 0:
            retry_after = r.headers.get("Retry-After")
            try:
                wait_s = float(retry_after) if retry_after else 5.0
            except ValueError:
                wait_s = 5.0
            time.sleep(min(wait_s, 30.0))
            return self.get(url, allow_redirects=allow_redirects, _retries=_retries - 1)
        return Response(
            status=r.status_code,
            url=r.url,
            text=r.text,
            headers=dict(r.headers),
            cookies={c.name: c.value for c in r.cookies},
        )