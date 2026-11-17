"""HTTP plumbing shared by sources: a rate limiter and a client that retries.

``ApiClient`` wraps ``httpx.AsyncClient`` and guarantees three things:

1. we never exceed N requests per sliding minute (``RateLimiter``);
2. when the server says "slow down" (HTTP 429, or ``x-ratelimit-remaining``
   close to zero) we wait instead of hammering it;
3. transient failures (timeouts, 5xx, 429) are retried with exponential backoff.

Time is injected (``sleep``, ``clock``) so tests run instantly.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Awaitable, Callable

import httpx

log = logging.getLogger(__name__)

Sleep = Callable[[float], Awaitable[None]]
RETRY_STATUSES = {429, 500, 502, 503, 504}


class RateLimiter:
    """Allow at most ``per_minute`` calls in any sliding ``window`` seconds."""

    def __init__(self, per_minute: int, window: float = 60.0,
                 clock: Callable[[], float] = time.monotonic, sleep: Sleep = asyncio.sleep) -> None:
        self.per_minute = per_minute
        self.window = window
        self._clock = clock
        self._sleep = sleep
        self._calls: deque[float] = deque()
        self._lock = asyncio.Lock()
        self._blocked_until = 0.0  # set from server hints (429, ratelimit headers)

    def block_for(self, seconds: float) -> None:
        """Pause every caller for ``seconds`` (the server asked us to wait)."""
        self._blocked_until = max(self._blocked_until, self._clock() + seconds)

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = self._clock()
                if now < self._blocked_until:
                    await self._sleep(self._blocked_until - now)
                    continue
                while self._calls and now - self._calls[0] >= self.window:
                    self._calls.popleft()
                if len(self._calls) < self.per_minute:
                    self._calls.append(now)
                    return
                await self._sleep(self.window - (now - self._calls[0]) + 0.05)


class ApiClient:
    """JSON API client with rate limiting, a timeout per request and retries."""

    def __init__(self, client: httpx.AsyncClient, limiter: RateLimiter, *, retries: int = 4,
                 backoff: float = 1.5, sleep: Sleep = asyncio.sleep) -> None:
        self._client = client
        self._limiter = limiter
        self._retries = retries
        self._backoff = backoff
        self._sleep = sleep
        self.request_count = 0

    async def request_json(self, method: str, url: str, **kwargs) -> dict:
        """Send a request and return the decoded JSON body.

        Raises ``httpx.HTTPError`` (or ``ValueError`` for bad JSON) once the
        retries are exhausted or the error is not worth retrying (e.g. 404).
        """
        attempt = 0
        while True:
            await self._limiter.acquire()
            self.request_count += 1
            try:
                resp = await self._client.request(method, url, **kwargs)
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                if attempt >= self._retries:
                    raise
                await self._wait(attempt, f"{type(exc).__name__} on {url}")
                attempt += 1
                continue
            self._respect_headers(resp)
            if resp.status_code in RETRY_STATUSES and attempt < self._retries:
                await self._wait(attempt, f"HTTP {resp.status_code} on {url}", resp)
                attempt += 1
                continue
            resp.raise_for_status()
            return resp.json()

    async def get_json(self, url: str, **kwargs) -> dict:
        return await self.request_json("GET", url, **kwargs)

    async def post_json(self, url: str, **kwargs) -> dict:
        return await self.request_json("POST", url, **kwargs)

    def _respect_headers(self, resp: httpx.Response) -> None:
        """Slow down when the server reports an almost empty quota."""
        remaining = resp.headers.get("x-ratelimit-remaining")
        if remaining is not None and remaining.isdigit() and int(remaining) <= 1:
            self._limiter.block_for(5.0)

    async def _wait(self, attempt: int, reason: str, resp: httpx.Response | None = None) -> None:
        """Sleep before a retry: ``Retry-After`` if given, else exponential backoff."""
        delay = self._backoff * (2 ** attempt)
        retry_after = resp.headers.get("retry-after") if resp is not None else None
        if retry_after and retry_after.replace(".", "", 1).isdigit():
            delay = min(float(retry_after), 65.0)
        log.warning("%s; retry %d/%d in %.1fs", reason, attempt + 1, self._retries, delay)
        await self._sleep(delay)
