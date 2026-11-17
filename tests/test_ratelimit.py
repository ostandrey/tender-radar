import asyncio

import httpx
import pytest

from conftest import FakeSleep
from tender_radar.sources.base import ApiClient, RateLimiter


def fake_clock():
    """A clock that only moves when the code sleeps."""
    now = {"t": 0.0}
    sleeper = FakeSleep()

    async def sleep(seconds):
        await sleeper(seconds)
        now["t"] += seconds

    return (lambda: now["t"]), sleep, sleeper


def test_limiter_waits_when_window_is_full():
    clock, sleep, sleeper = fake_clock()
    limiter = RateLimiter(2, window=60.0, clock=clock, sleep=sleep)

    async def go():
        for _ in range(3):
            await limiter.acquire()

    asyncio.run(go())
    assert len(sleeper.calls) == 1 and sleeper.calls[0] >= 60.0  # the 3rd call waits for the window to slide


def test_low_remaining_quota_header_slows_us_down():
    clock, sleep, sleeper = fake_clock()
    limiter = RateLimiter(100, clock=clock, sleep=sleep)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={}, headers={"x-ratelimit-remaining": "0"}))

    async def go():
        async with httpx.AsyncClient(transport=transport) as client:
            api = ApiClient(client, limiter, sleep=sleep)
            await api.get_json("https://example.test/a")
            await api.get_json("https://example.test/b")

    asyncio.run(go())
    assert sleeper.calls and sleeper.calls[0] > 0


def test_404_is_not_retried():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(404)

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            api = ApiClient(client, RateLimiter(100), sleep=FakeSleep())
            await api.get_json("https://example.test/x")

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(go())
    assert calls["n"] == 1
